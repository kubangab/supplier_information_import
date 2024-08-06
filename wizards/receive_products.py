from odoo import models, fields, api, _
from odoo.exceptions import UserError

class ReceiveProducts(models.TransientModel):
    _name = 'receive.products.wizard'
    _description = 'Receive Products Wizard'

    incoming_product_ids = fields.Many2many('incoming.product.info', string='Incoming Products')
    lot_creation_method = fields.Selection([
        ('auto', 'Automatic'),
        ('manual', 'Manual')
    ], string='Lot Creation Method', default='auto', required=True)
    manual_lot_number = fields.Char(string='Manual Lot Number')

    @api.onchange('lot_creation_method')
    def _onchange_lot_creation_method(self):
        if self.lot_creation_method == 'auto':
            self.manual_lot_number = False

    def action_receive_products(self):
        StockMove = self.env['stock.move']
        StockProductionLot = self.env['stock.production.lot']
        
        for incoming_product in self.incoming_product_ids:
            move = StockMove.create({
                'name': f"Receipt of {incoming_product.name}",
                'product_id': incoming_product.product_id.id,
                'product_uom_qty': 1,
                'product_uom': incoming_product.product_id.uom_id.id,
                'location_id': self.env.ref('stock.stock_location_suppliers').id,
                'location_dest_id': self.env.ref('stock.stock_location_stock').id,
            })
            
            lot_name = self._get_lot_name(incoming_product)
            lot = StockProductionLot.create({
                'name': lot_name,
                'product_id': incoming_product.product_id.id,
                'company_id': self.env.company.id,
            })
            
            self._update_lot_info(lot, incoming_product)
            
            move._action_confirm()
            move._action_assign()
            move_line = move.move_line_ids[0]
            move_line.lot_id = lot.id
            move_line.qty_done = 1
            move._action_done()
            
            incoming_product.state = 'received'

        return {'type': 'ir.actions.act_window_close'}

    def _get_lot_name(self, incoming_product):
        if self.lot_creation_method == 'manual':
            return self.manual_lot_number
        return incoming_product.sn or incoming_product.model_no or f"LOT-{fields.Datetime.now().strftime('%Y%m%d%H%M%S')}"

    def _update_lot_info(self, lot, incoming_product):
        lot.write({
            'x_mac1': incoming_product.mac1,
            'x_mac2': incoming_product.mac2,
            'x_imei': incoming_product.imei,
            'x_app_key': incoming_product.app_key,
            'x_dev_eui': incoming_product.dev_eui,
        })