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
            _logger.info(f"Processing order line: {line}, Product: {line.product_id.name} (ID: {line.product_id.id}, Default Code: {line.product_id.default_code})")
            pickings = self.picking_ids.filtered(lambda p: p.state == 'done')
            move_lines = pickings.mapped('move_line_ids').filtered(
                lambda ml: ml.product_id == line.product_id and ml.state == 'done'
            )
            if move_lines:
                for move_line in move_lines:
                    _logger.info(f"Move line: {move_line}, Lot: {move_line.lot_id.name if move_line.lot_id else 'N/A'}")
                    lines.append((line, move_line))
            else:
                _logger.info("No move lines found for this order line")
                lines.append((line, False))
        _logger.info(f"Report lines for sale order {self.name}: {lines}")
        return lines

    def send_excel_report_email(self, excel_data):
        attachment = self.env['ir.attachment'].create({
            'name': f'Product_Info_{self.name}.xlsx',
            'datas': base64.b64encode(excel_data),
            'res_model': 'sale.order',
            'res_id': self.id,
        })

        template = self.env.ref('supplier_information_import.email_template_product_info_sale_order')
        template.send_mail(
            self.id,
            force_send=True,
            email_values={'attachment_ids': [attachment.id]}
        )