from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
from io import BytesIO
import xlsxwriter

class SaleOrder(models.Model):
    _name = 'sale.order'
    _inherit = ['sale.order', 'product.info.report.mixin']

    def generate_excel_report(self):
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet('Product Info')

        # Get fields from incoming.product.info model
        IncomingProductInfo = self.env['incoming.product.info']
        info_fields = IncomingProductInfo._fields

        # Define base headers and get additional headers from incoming.product.info
        base_headers = ['SKU', 'Product', 'Quantity', 'Serial Number']
        excluded_fields = ['id', 'create_uid', 'create_date', 'write_uid', 'write_date', 'display_name', 
                           'supplier_id', 'product_id', 'stock_picking_id', 'state', 'sn', 'name', 
                           'supplier_product_code', 'product_tmpl_id', '__last_update']
        additional_headers = [
            field.capitalize() 
            for field in info_fields 
            if field not in excluded_fields and field not in [h.lower() for h in base_headers]
        ]
        all_headers = base_headers + additional_headers

        # Write headers
        for col, header in enumerate(all_headers):
            worksheet.write(0, col, header)

        # Collect and write data
        row = 1
        for order_line in self.order_line:
            product = order_line.product_id
            delivered_qty = order_line.qty_delivered
            if delivered_qty <= 0:
                continue

            move_lines = self.env['stock.move.line'].search([
                ('move_id.sale_line_id', '=', order_line.id),
                ('state', '=', 'done')
            ])

            for move_line in move_lines:
                incoming_info = IncomingProductInfo.search([
                    ('product_id', '=', product.id),
                    ('sn', '=', move_line.lot_id.name)
                ], limit=1)

                col = 0
                # Write base data
                worksheet.write(row, col, product.default_code or ''); col += 1
                worksheet.write(row, col, product.name or ''); col += 1
                worksheet.write(row, col, move_line.qty_done or 0); col += 1
                worksheet.write(row, col, move_line.lot_id.name if move_line.lot_id else ''); col += 1

                # Write additional data from incoming_info
                if incoming_info:
                    for field in additional_headers:
                        value = getattr(incoming_info, field.lower(), False)
                        if isinstance(value, models.Model):
                            value = value.name if hasattr(value, 'name') else str(value)
                        worksheet.write(row, col, str(value) if value else '')
                        col += 1
                else:
                    # If no incoming_info, write empty cells for additional fields
                    for _ in additional_headers:
                        worksheet.write_blank(row, col, None, None)
                        col += 1

                row += 1

        workbook.close()
        return output.getvalue()

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