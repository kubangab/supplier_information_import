from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
from io import BytesIO
import xlsxwriter

class SaleOrder(models.Model):
    _name = 'sale.order'
    _inherit = ['sale.order','product.info.report.mixin']

    def _get_report_lines(self):
        return self.order_line.filtered(lambda line: line.product_id.tracking == 'serial' and not line.is_delivery)

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