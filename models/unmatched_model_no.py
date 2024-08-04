from odoo import models, fields, api

class UnmatchedModelNo(models.Model):
    _name = 'unmatched.model.no'
    _description = 'Unmatched Model Number'

    config_id = fields.Many2one('import.format.config', string='Import Configuration')
    supplier_id = fields.Many2one(related='config_id.supplier_id', string='Supplier', store=True, readonly=True)
    model_no = fields.Char(string='Model Number', required=True)
    pn = fields.Char(string='PN')
    product_code = fields.Char(string='Product Code')
    product_id = fields.Many2one('product.product', string='Product')
    supplier_product_code = fields.Char(string='Supplier Product Code')
    raw_data = fields.Text(string='Raw Data')
    count = fields.Integer(string='Count', default=1)

    @api.model
    def _get_product_codes(self):
        products = self.env['product.product'].search([('seller_ids.partner_id', '=', self.supplier_id.id)])
        return [(p.id, f"{p.default_code} - {p.name}") for p in products if p.default_code]

    product_selection = fields.Selection(_get_product_codes, string='Product Selection')

    @api.onchange('product_selection')
    def _onchange_product_selection(self):
        if self.product_selection:
            self.product_id = self.product_selection

    def action_link_product(self):
        self.ensure_one()
        if self.product_id:
            IncomingProductInfo = self.env['incoming.product.info']
            for _ in range(self.count):
                # Create incoming.product.info
                incoming_product = IncomingProductInfo.create({
                    'supplier_id': self.supplier_id.id,
                    'product_id': self.product_id.id,
                    'model_no': self.model_no,
                    'sn': self.pn,
                    'supplier_product_code': self.supplier_product_code or self.product_code,
                    # Add other fields from raw_data as needed
                })

                # Update or create product.supplierinfo
                supplierinfo = self.env['product.supplierinfo'].search([
                    ('partner_id', '=', self.supplier_id.id),
                    ('product_id', '=', self.product_id.id)
                ], limit=1)
                
                if not supplierinfo:
                    self.env['product.supplierinfo'].create({
                        'partner_id': self.supplier_id.id,
                        'product_id': self.product_id.id,
                        'product_code': self.supplier_product_code or self.product_code,
                    })
                else:
                    supplierinfo.write({
                        'product_code': self.supplier_product_code or self.product_code,
                    })

            # Remove this unmatched record
            self.unlink()

            return {
                'type': 'ir.actions.act_window',
                'name': 'Linked Product Info',
                'res_model': 'incoming.product.info',
                'res_id': incoming_product.id,
                'view_mode': 'form',
                'view_type': 'form',
                'target': 'current',
            }
        return {'type': 'ir.actions.do_nothing'}