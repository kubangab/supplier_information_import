from odoo import models, _
from odoo.exceptions import UserError
import base64

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