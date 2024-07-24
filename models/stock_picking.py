from odoo import models, fields, api, _
from odoo.exceptions import UserError

class StockPicking(models.Model):
    _inherit = 'stock.picking'

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

            for pending in pending_products:
                move = picking.move_ids.filtered(lambda m: m.product_id.id == pending.product_id.id)
                if not move:
                    raise UserError(_("Product %s is not in the transfer lines.") % pending.product_id.name)

                move_line = StockMoveLine.create({
                    'move_id': move.id,
                    'product_id': pending.product_id.id,
                    'product_uom_id': pending.product_id.uom_id.id,
                    'location_id': move.location_id.id,
                    'location_dest_id': move.location_dest_id.id,
                    'picking_id': picking.id,
                    'lot_name': pending.sn,
                    'qty_done': 1,
                })

                pending.write({
                    'state': 'received',
                    'stock_picking_id': picking.id
                })

            picking.action_assign()

        return True