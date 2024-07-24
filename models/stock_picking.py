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

        # Get fields from incoming.product.info model
        IncomingProductInfo = self.env['incoming.product.info']
        info_fields = IncomingProductInfo._fields

        # Define base headers and get additional headers from incoming.product.info
        base_headers = ['SKU', 'Product', 'Quantity', 'Serial Number']
        additional_headers = [
            field.capitalize() 
            for field in info_fields 
            if field not in ['id', 'create_uid', 'create_date', 'write_uid', 'write_date', 'display_name', 'supplier_id', 'product_id', 'stock_picking_id', 'state']
        ]
        all_headers = base_headers + additional_headers

        # Initialize a dictionary to keep track of which headers are needed
        headers_needed = {header: False for header in all_headers}
        for header in base_headers:
            headers_needed[header] = True

        # Collect data and determine which headers are needed
        data = []
        for move_line in self.move_line_ids:
            product = move_line.product_id
            incoming_info = IncomingProductInfo.search([
                ('product_id', '=', product.id),
                ('sn', '=', move_line.lot_id.name)
            ], limit=1)

            row_data = {
                'SKU': product.default_code or '',
                'Product': product.name,
                'Quantity': move_line.qty_done,
                'Serial Number': move_line.lot_id.name if move_line.lot_id else '',
            }

            if incoming_info:
                for field in additional_headers:
                    value = getattr(incoming_info, field.lower(), False)
                    if value:
                        headers_needed[field] = True
                        row_data[field] = value

            data.append(row_data)

        # Create the list of headers that are actually needed
        headers = [header for header in all_headers if headers_needed[header]]

        # Write headers
        for col, header in enumerate(headers):
            worksheet.write(0, col, header)

        # Write data
        for row, row_data in enumerate(data, start=1):
            for col, header in enumerate(headers):
                worksheet.write(row, col, row_data.get(header, ''))

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