from odoo import models
import base64
import logging

_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _name = 'sale.order'
    _inherit = ['sale.order','product.info.report.mixin']

    def _get_report_lines(self):
        self.ensure_one()
        lines = []
        for line in self.order_line.filtered(lambda l: l.product_id.tracking == 'serial'):
            pickings = self.picking_ids.filtered(lambda p: p.state == 'done')
            move_lines = pickings.mapped('move_line_ids').filtered(
                lambda ml: ml.product_id == line.product_id and ml.state == 'done'
            )
            if move_lines:
                for move_line in move_lines:
                    lines.append((line, move_line))
            else:
                lines.append((line, False))
        return lines
    def action_generate_and_send_excel(self):
        return super(SaleOrder, self).action_generate_and_send_excel()