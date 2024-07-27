from odoo import models, fields, api

class SendProductInfoWizard(models.TransientModel):
    _name = 'send.product.info.wizard'
    _description = 'Send Product Info Wizard'

    partner_ids = fields.Many2many('res.partner', string='Additional Recipients')
    subject = fields.Char('Subject', required=True)
    body = fields.Html('Body', required=True)
    attachment_id = fields.Many2one('ir.attachment', string='Attachment')

    @api.model
    def default_get(self, fields):
        res = super(SendProductInfoWizard, self).default_get(fields)
        active_model = self._context.get('active_model')
        active_id = self._context.get('active_id')
    
        if active_model and active_id:
            record = self.env[active_model].browse(active_id)
            template = self.env.ref('supplier_information_import.email_template_product_info')
    
            # Generate Excel file
            excel_data = record.generate_excel_report()
            attachment = self.env['ir.attachment'].create({
                'name': f'Product_Info_{record.name}.xlsx',
                'datas': excel_data,
                'res_model': active_model,
                'res_id': active_id,
            })
    
            res.update({
                'subject': template._render_field('subject', [record.id])[record.id],
                'body': template._render_field('body_html', [record.id])[record.id],
                'attachment_id': attachment.id,
            })
        return res

    def action_send_mail(self):
        self.ensure_one()
        active_model = self._context.get('active_model')
        active_id = self._context.get('active_id')

        if active_model and active_id:
            record = self.env[active_model].browse(active_id)
            email_values = {
                'subject': self.subject,
                'body_html': self.body,
                'email_to': record.partner_id.email,
                'email_cc': ','.join(self.partner_ids.mapped('email')),
                'attachment_ids': [(4, self.attachment_id.id)] if self.attachment_id else [],
            }
            record.message_post(
                body=self.body,
                subject=self.subject,
                partner_ids=self.partner_ids.ids + [record.partner_id.id],
                attachment_ids=[self.attachment_id.id] if self.attachment_id else [],
                message_type='email',
                subtype_id=self.env.ref('mail.mt_comment').id,
            )
            self.env['mail.mail'].create(email_values).send()

        return {'type': 'ir.actions.act_window_close'}