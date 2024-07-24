from odoo import models, fields, api, _
import base64
import xlsxwriter
from io import BytesIO
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

            products_added = []
            for move in picking.move_ids:
                pending = pending_products.filtered(lambda p: p.product_id.id == move.product_id.id)
                
                for p in pending:
                    move_line = StockMoveLine.create({
                        'move_id': move.id,
                        'product_id': p.product_id.id,
                        'product_uom_id': p.product_id.uom_id.id,
                        'location_id': move.location_id.id,
                        'location_dest_id': move.location_dest_id.id,
                        'picking_id': picking.id,
                        'lot_name': p.sn,
                        'qty_done': 1,
                    })

                    p.write({
                        'state': 'received',
                        'stock_picking_id': picking.id
                    })
                    
                    products_added.append(p.product_id.name)

            if products_added:
                message = _("Added quantities for the following products: %s") % ", ".join(products_added)
            else:
                message = _("No pending products found matching the transfer lines.")
            
            picking.message_post(body=message)
            picking.action_assign()

        return True
    
    def action_generate_and_send_excel(self):
        self.ensure_one()
        if self.state != 'done':
            raise UserError(_("You can only generate the Excel file for confirmed transfers."))

        excel_data = self.generate_excel_report()
        self.send_excel_report_email(excel_data)

    def generate_excel_report(self):
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet('Product Info')

        # Add headers
        headers = ['Product', 'Quantity', 'Serial Number', 'Supplier', 'Supplier Product Code', 'MAC1', 'MAC2', 'IMEI', 'AppKey', 'DevEUI']
        for col, header in enumerate(headers):
            worksheet.write(0, col, header)

        # Add product data
        for row, move_line in enumerate(self.move_line_ids, start=1):
            product = move_line.product_id
            incoming_info = self.env['incoming.product.info'].search([
                ('product_id', '=', product.id),
                ('sn', '=', move_line.lot_id.name)
            ], limit=1)

            worksheet.write(row, 0, product.name)
            worksheet.write(row, 1, move_line.qty_done)
            worksheet.write(row, 2, move_line.lot_id.name if move_line.lot_id else '')
            worksheet.write(row, 3, self.partner_id.name)
            worksheet.write(row, 4, incoming_info.supplier_product_code if incoming_info else '')
            worksheet.write(row, 5, incoming_info.mac1 if incoming_info else '')
            worksheet.write(row, 6, incoming_info.mac2 if incoming_info else '')
            worksheet.write(row, 7, incoming_info.imei if incoming_info else '')
            worksheet.write(row, 8, incoming_info.app_key if incoming_info else '')
            worksheet.write(row, 9, incoming_info.dev_eui if incoming_info else '')

        workbook.close()
        return output.getvalue()

    def send_excel_report_email(self, excel_data):
        attachment = self.env['ir.attachment'].create({
            'name': f'Product_Info_{self.name}.xlsx',
            'datas': base64.b64encode(excel_data),
            'res_model': 'stock.picking',
            'res_id': self.id,
        })

        template = self.env.ref('product_information_import.email_template_product_info')
        template.send_mail(
            self.id,
            force_send=True,
            email_values={'attachment_ids': [attachment.id]}
        )