from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64

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
        # This method should be implemented in the inheriting models
        raise NotImplementedError(_("This method must be implemented in the inheriting model"))