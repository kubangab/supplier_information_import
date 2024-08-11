from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import xlsxwriter
from io import BytesIO

class ProductInfoReportMixin(models.AbstractModel):
    _name = 'product.info.report.mixin'
    _description = 'Product Info Report Mixin'

    def action_generate_and_send_excel(self):
        self.ensure_one()
        if self._name == 'sale.order' and self.state not in ['sale', 'done']:
            raise UserError(_("You can only generate the Excel file for confirmed sales orders."))
        elif self._name == 'stock.picking' and self.state != 'done':
            raise UserError(_("You can only generate the Excel file for confirmed transfers."))

        # Generate Excel report
        excel_data = self.generate_excel_report()
        
        # Create attachment
        attachment = self.env['ir.attachment'].create({
            'name': f'Product_Info_{self.name}.xlsx',
            'datas': base64.b64encode(excel_data),
            'res_model': self._name,
            'res_id': self.id,
        })

        # Get the correct email template
        if self._name == 'sale.order':
            template = self.env.ref('supplier_information_import.email_template_product_info_sale_order')
        else:  # stock.picking
            template = self.env.ref('supplier_information_import.email_template_product_info_delivery')
        
        # Use Odoo's built-in mail composer
        compose_form = self.env.ref('mail.email_compose_message_wizard_form', False)
        ctx = dict(
            default_model=self._name,
            default_res_id=self.id,
            default_use_template=bool(template),
            default_template_id=template.id,
            default_composition_mode='comment',
            mark_so_as_sent=True,
            custom_layout="mail.mail_notification_paynow",
            force_email=True,
            default_attachment_ids=[(4, attachment.id)]
        )
        return {
            'name': _('Compose Email'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(compose_form.id, 'form')],
            'view_id': compose_form.id,
            'target': 'new',
            'context': ctx,
        }

    def generate_excel_report(self):
        self.ensure_one()
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output)
        
        config = self.env['import.format.config'].search([], limit=1)
        worksheet = workbook.add_worksheet(config.report_worksheet_name or 'Product Info')

        # Define headers based on configuration
        headers = [field.with_context(lang=self.partner_id.lang).name for field in config.report_field_ids.sorted(key=lambda r: r.sequence)]

        # Write headers
        for col, header in enumerate(headers):
            worksheet.write(0, col, header)

        # Collect and write data
        row = 1
        for line in self._get_report_lines():
            if self._name == 'stock.picking':
                product_lines = line
            else:  # sale.order
                product_lines = self.env['stock.move.line'].search([
                    ('picking_id.sale_id', '=', self.id),
                    ('product_id', '=', line.product_id.id),
                    ('lot_id', '!=', False)
                ])

            for product_line in product_lines:
                col = 0
                for field_config in config.report_field_ids.sorted(key=lambda r: r.sequence):
                    if field_config.field_id.model == 'product.product':
                        if field_config.field_id.name == 'name':
                            # Use product_template_id.name from the sale order line
                            if self._name == 'sale.order':
                                value = line.product_template_id.name
                            else:
                                value = product_line.product_id.product_tmpl_id.name
                        else:
                            value = product_line.product_id[field_config.field_id.name]
                    elif field_config.field_id.model in ['sale.order.line', 'stock.move.line']:
                        value = getattr(product_line, field_config.field_id.name, '')
                    elif field_config.field_id.model == 'incoming.product.info':
                        incoming_info = self.env['incoming.product.info'].search([
                            ('product_id', '=', product_line.product_id.id),
                            ('sn', '=', product_line.lot_id.name if product_line.lot_id else False),
                        ], limit=1)
                        value = getattr(incoming_info, field_config.field_id.name, '') if incoming_info else ''

                    if isinstance(value, models.Model):
                        value = value.with_context(lang=self.partner_id.lang).display_name
                    worksheet.write(row, col, str(value) if value else '')
                    col += 1
                row += 1

        workbook.close()
        return output.getvalue()

    def _get_report_lines(self):
        # This method should be implemented in the inheriting models
        raise NotImplementedError(_("This method must be implemented in the inheriting model"))

    def _get_report_field_names(self):
        config = self.env['import.format.config'].search([], limit=1)
        if config:
            return {
                'sku': _(config.report_sku_field.field_description if config.report_sku_field else 'SKU'),
                'product': _(config.report_product_field.field_description if config.report_product_field else 'Product'),
                'quantity': _(config.report_quantity_field.field_description if config.report_quantity_field else 'Quantity'),
                'serial_number': _(config.report_serial_number_field.field_description if config.report_serial_number_field else 'Serial Number'),
                'worksheet_name': _(config.report_worksheet_name or 'Product Info'),
            }
        else:
            return {
                'sku': _('SKU'),
                'product': _('Product'),
                'quantity': _('Quantity'),
                'serial_number': _('Serial Number'),
                'worksheet_name': _('Product Info'),
            }

class ProductInfoReportConfig(models.Model):
    _name = 'product.info.report.config'
    _description = 'Product Info Report Configuration'

    name = fields.Char(string='Configuration Name', required=True)
    sku_field_name = fields.Char(string='SKU Field Name', default='SKU')
    product_field_name = fields.Char(string='Product Field Name', default='Product')
    quantity_field_name = fields.Char(string='Quantity Field Name', default='Quantity')
    serial_number_field_name = fields.Char(string='Serial Number Field Name', default='Serial Number')
    worksheet_name = fields.Char(string='Worksheet Name', default='Product Info')