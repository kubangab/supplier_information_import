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
        for row, move_line in enumerate(self.move_line_ids, start=1):
            product = move_line.product_id
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

        workbook.close()
        return output.getvalue()
    
    def send_excel_report_email(self, excel_data):
        attachment = self.env['ir.attachment'].create({
            'name': f'Product_Info_{self.name}.xlsx',
            'datas': base64.b64encode(excel_data),
            'res_model': 'stock.picking',
            'res_id': self.id,
        })

        template = self.env.ref('supplier_information_import.email_template_product_info')
        template.send_mail(
            self.id,
            force_send=True,
            email_values={'attachment_ids': [attachment.id]}
        )