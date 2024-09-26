from odoo import models, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class StockPicking(models.Model):
    _name = 'stock.picking'
    _inherit = ['stock.picking', 'product.selection.mixin','product.info.report.mixin']

    def action_set_quantities_from_pending(self):
        IncomingProductInfo = self.env['incoming.product.info']
        StockMoveLine = self.env['stock.move.line']
        
        for picking in self:
            if picking.picking_type_code != 'incoming':
                raise UserError(_("This action is only available for incoming transfers."))

            pending_products = IncomingProductInfo.search([
                ('state', '=', 'pending'),
                ('stock_picking_id', '=', False),
                ('supplier_id', '=', picking.partner_id.id)
            ])

            products_added = []
            for move in picking.move_ids:
                pending = pending_products.filtered(lambda p: p.product_id.id == move.product_id.id)
                
                for p in pending:
                    # Check if there's a matching lot (serial number) for this product
                    matching_lot = self.env['stock.production.lot'].search([
                        ('name', '=', p.sn),
                        ('product_id', '=', p.product_id.id)
                    ], limit=1)

                    if matching_lot:
                        move_line = StockMoveLine.create({
                            'move_id': move.id,
                            'product_id': p.product_id.id,
                            'product_uom_id': p.product_id.uom_id.id,
                            'location_id': move.location_id.id,
                            'location_dest_id': move.location_dest_id.id,
                            'picking_id': picking.id,
                            'lot_id': matching_lot.id,
                            'qty_done': 1,
                        })

                        p.write({
                            'state': 'received',
                            'stock_picking_id': picking.id
                        })
                        
                        products_added.append(p.product_id.name)
                    else:
                        _logger.warning(f"No matching lot found for product {p.product_id.name} with SN {p.sn}")

            if products_added:
                message = _("Added quantities for the following products: %s") % ", ".join(products_added)
            else:
                message = _("No pending products found matching the transfer lines.")
            
            picking.message_post(body=message)
            picking.action_assign()

        return True

    def action_generate_and_send_excel(self):
        return super(StockPicking, self).action_generate_and_send_excel()

    def _get_report_lines(self):
        self.ensure_one()
        lines = []
        for move_line in self.move_line_ids.filtered(lambda ml: ml.product_id.tracking == 'serial'):
            sale_line = move_line.move_id.sale_line_id
            lines.append((sale_line or move_line, move_line))
        return lines

    @api.model
    def _update_incoming_product_info(self):
        _logger.info("Starting _update_incoming_product_info")
        IncomingProductInfo = self.env['incoming.product.info']
        for move_line in self.move_line_ids:
            if move_line.lot_id:
                _logger.info(f"Processing move_line with lot: {move_line.lot_id.name}")
                incoming_info = IncomingProductInfo.search([
                    ('sn', '=', move_line.lot_id.name),
                    ('product_id', '=', move_line.product_id.id),
                    ('state', '=', 'pending')
                ])
                if incoming_info:
                    _logger.info(f"Updating incoming_info: {incoming_info.id}")
                    incoming_info.write({
                        'state': 'received',
                        'stock_picking_id': self.id
                    })
                else:
                    _logger.info(f"No matching incoming_info found for SN: {move_line.lot_id.name}")
        _logger.info("Finished _update_incoming_product_info")

    def button_validate(self):
        res = super(StockPicking, self).button_validate()
        if self.picking_type_code == 'incoming':
            _logger.info("Calling _update_incoming_product_info")
            self._update_incoming_product_info()
        return res

    @api.model
    def _run_postprocess_hook(self):
        super(StockPicking, self)._run_postprocess_hook()
        if self.picking_type_code == 'incoming':
            self._update_incoming_product_info()