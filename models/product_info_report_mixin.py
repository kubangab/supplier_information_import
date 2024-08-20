from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import xlsxwriter
from io import BytesIO
import logging

_logger = logging.getLogger(__name__)

class ProductInfoReportMixin(models.AbstractModel):
    _name = 'product.info.report.mixin'
    _description = 'Product Info Report Mixin'

    def _get_partner_lang(self):
        partner = self.partner_id if hasattr(self, 'partner_id') else self.env.user.partner_id
        return partner.lang or self.env.user.lang

    def _get_report_worksheet_name(self):
        return _('Product Info')

    def _get_report_headers(self, lang):
        config = self.env['import.format.config'].search([], limit=1)
        return [field.with_context(lang=lang).name for field in config.report_field_ids.sorted(key=lambda r: r.sequence)]

    def _get_report_fields(self):
        config = self.env['import.format.config'].search([], limit=1)
        return config.report_field_ids.sorted(key=lambda r: r.sequence).mapped('field_id')

    def _get_report_lines(self):
        # This method should be implemented in the inheriting model
        raise NotImplementedError(_("This method must be implemented in the inheriting model"))

    def action_generate_and_send_excel(self):
        self.ensure_one()
        user_lang = self.env.user.lang
        partner = self.partner_id
        partner_lang = partner.lang or user_lang

        # Generate the Excel report
        excel_data = self.generate_excel_report()
        
        # Create attachment
        attachment = self.env['ir.attachment'].create({
            'name': f'Product_Info_{self.name}.xlsx',
            'datas': excel_data,
            'res_model': self._name,
            'res_id': self.id,
        })

        # Determine the correct email template based on the model
        if self._name == 'sale.order':
            template = self.env.ref('supplier_information_import.email_template_product_info_sale_order')
        elif self._name == 'stock.picking':
            template = self.env.ref('supplier_information_import.email_template_product_info_delivery')
        else:
            raise UserError(_("No email template found for this model."))

        # Render the email template
        template = template.with_context(lang=partner_lang)
        email_values = template.generate_email(self.id, ['subject', 'body_html'])

        ctx = {
            'default_model': self._name,
            'default_res_id': self.id,
            'default_use_template': True,
            'default_template_id': template.id,
            'default_composition_mode': 'comment',
            'mark_so_as_sent': True,
            'custom_layout': "mail.mail_notification_paynow",
            'force_email': True,
            'model_description': self.with_context(lang=partner_lang).type_name,
            'default_attachment_ids': [(4, attachment.id)],
            'default_partner_ids': [partner.id],
            'default_subject': email_values['subject'],
            'default_body': email_values['body_html'],
            'lang': user_lang,  # Set the language in the context
        }

        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(False, 'form')],
            'view_id': False,
            'target': 'new',
            'context': ctx,
        }

    def generate_excel_report(self):
        self.ensure_one()
        partner_lang = self._get_partner_lang()
        
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        
        worksheet = workbook.add_worksheet(self._get_report_worksheet_name())

        # Define headers based on configuration
        headers = self._get_report_headers(lang=partner_lang)
        for col, header in enumerate(headers):
            worksheet.write(0, col, header)

        # Collect and write data
        row = 1
        for line, move_line in self._get_report_lines():
            col = 0
            for field in self._get_report_fields():
                value = self._get_field_value(line, move_line, field, lang=partner_lang)
                worksheet.write(row, col, value if value else '')
                col += 1
            row += 1

        workbook.close()
        excel_data = output.getvalue()
        return base64.b64encode(excel_data)

    def _get_field_value(self, line, move_line, field_config, lang):
        self = self.with_context(lang=lang)
        
        if field_config.model == 'incoming.product.info':
            product = line.product_id
            sn = move_line.lot_id.name if move_line and move_line.lot_id else False
            _logger.info(f"Searching for incoming info: product={product.name} (ID: {product.id}, Default Code: {product.default_code}), SN={sn}")
            
            incoming_info = self.env['incoming.product.info'].search([
                ('sn', '=', sn),
                '|',
                ('product_id', '=', product.id),
                ('product_id.product_tmpl_id', '=', product.product_tmpl_id.id)
            ], limit=1)
            
            if incoming_info:
                if incoming_info.product_id.id != product.id:
                    _logger.info(f"Product variant mismatch, but template matches. IncomingProductInfo Product ID: {incoming_info.product_id.id}, Template ID: {incoming_info.product_id.product_tmpl_id.id}")
                _logger.info(f"Found incoming info: {incoming_info.name}")
                field_name = field_config.name.lower()
                value = getattr(incoming_info, field_name, '')
                _logger.info(f"Field: {field_config.name}, Value: {value}")
                return value if value not in [False, 'False'] else ''
            else:
                _logger.warning(f"No incoming info found for SN={sn} and Product Template ID={product.product_tmpl_id.id}")
                return ''
        
        # Handle other field types here
        if field_config.model == 'product.product':
            value = getattr(line.product_id, field_config.name, '')
        elif field_config.model == 'product.template':
            value = getattr(line.product_id.product_tmpl_id, field_config.name, '')
        elif field_config.model == 'sale.order.line':
            value = getattr(line, field_config.name, '')
        elif field_config.model == 'stock.move.line':
            if field_config.name == 'lot_id':
                value = move_line.lot_id.name if move_line and move_line.lot_id else ''
            else:
                value = getattr(move_line, field_config.name, '') if move_line else ''
        else:
            _logger.warning(f"No handler for field model: {field_config.model}")
            value = ''
        
        # Format dates and datetimes according to the partner's language
        if field_config.ttype == 'date':
            return fields.Date.from_string(value) if value else ''
        elif field_config.ttype == 'datetime':
            return fields.Datetime.from_string(value) if value else ''
        elif field_config.ttype in ['float', 'monetary']:
            return float(value) if value not in [False, 'False', ''] else 0.0
        elif field_config.ttype == 'integer':
            return int(value) if value not in [False, 'False', ''] else 0
        
        return value if value not in [False, 'False'] else ''

    def _get_report_field_names(self):
        config = self.env['import.format.config'].search([], limit=1)
        if config:
            field_names = {}
            for report_field in config.report_field_ids.sorted(key=lambda r: r.sequence):
                field_key = report_field.field_id.name.lower().replace('_', '')
                field_names[field_key] = _(report_field.name)
            
            # Ensure we have defaults for essential fields
            if 'sku' not in field_names:
                field_names['sku'] = _('SKU')
            if 'name' not in field_names:
                field_names['name'] = _('Product')
            if 'productuomqty' not in field_names:
                field_names['productuomqty'] = _('Quantity')
            if 'lotid' not in field_names:
                field_names['lotid'] = _('Serial Number')
            
            field_names['worksheet_name'] = _(config.report_worksheet_name or 'Product Info')
            return field_names
        else:
            return {
                'sku': _('SKU'),
                'name': _('Product'),
                'productuomqty': _('Quantity'),
                'lotid': _('Serial Number'),
                'worksheet_name': _('Product Info'),
            }

    def send_excel_report_email(self, template, attachment):
        # Send email in the partner's language
        partner = self.partner_id if hasattr(self, 'partner_id') else self.env.user.partner_id
        
        # Use Odoo's built-in mail composer
        composer = self.env['mail.compose.message'].with_context({
            'default_model': self._name,
            'default_res_id': self.id,
            'default_use_template': bool(template),
            'default_template_id': template.id,
            'default_composition_mode': 'comment',
            'mark_so_as_sent': True,
            'custom_layout': "mail.mail_notification_paynow",
            'force_email': True,
            'default_attachment_ids': [(4, attachment.id)]
        }).create({})
        
        # Prepare the email values
        email_values = composer.onchange_template_id(template.id, 'comment', self._name, self.id)['value']
        email_values['attachment_ids'] = [(4, attachment.id)]
        
        # Send the email
        composer.with_context(lang=partner.lang).write(email_values)
        composer.send_mail()
    
        return True

class ProductInfoReportConfig(models.Model):
    _name = 'product.info.report.config'
    _description = 'Product Info Report Configuration'

    name = fields.Char(string='Configuration Name', required=True)
    sku_field_name = fields.Char(string='SKU Field Name', default='SKU')
    product_field_name = fields.Char(string='Product Field Name', default='Product')
    quantity_field_name = fields.Char(string='Quantity Field Name', default='Quantity')
    serial_number_field_name = fields.Char(string='Serial Number Field Name', default='Serial Number')
    worksheet_name = fields.Char(string='Worksheet Name', default='Product Info')