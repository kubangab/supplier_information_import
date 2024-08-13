from odoo import models, fields, api, _
from .product_selection_mixin import ProductSelectionMixin

class UnmatchedModelNo(models.Model, ProductSelectionMixin):
    _name = 'unmatched.model.no'
    _inherit = 'product.selection.mixin'
    _description = 'Unmatched Model Number'

    config_id = fields.Many2one('import.format.config', string='Configuration', required=True)
    supplier_id = fields.Many2one('res.partner', string='Supplier', required=True)
    model_no = fields.Char(string='Model Number', required=True)
    pn = fields.Char(string='PN')
    product_code = fields.Char(string='Product Code')
    supplier_product_code = fields.Char(string='Supplier Product Code')
    product_id = fields.Many2one('product.product', string='Product')
    count = fields.Integer(string='Count', default=1)
    raw_data = fields.Text(string='Raw Data')

    product_selection = fields.Selection(selection='_get_product_codes', string='Product Selection')

    @api.onchange('supplier_id')
    def _onchange_supplier_id(self):
        return {'domain': {'product_id': self._get_product_domain()}}

    def _get_product_domain(self):
        self.ensure_one()
        if self.supplier_id:
            main_supplier = self.supplier_id.parent_id or self.supplier_id
            return [('seller_ids.partner_id', 'in', main_supplier.ids + main_supplier.child_ids.ids)]
        return []

    @api.model
    def _get_product_codes(self):
        products = self.env['product.product'].search([('seller_ids.partner_id', '=', self.supplier_id.id)])
        return [(p.id, f"{p.default_code} - {p.name}") for p in products if p.default_code]

    @api.onchange('product_selection')
    def _onchange_product_selection(self):
        if self.product_selection:
            self.product_id = self.product_selection

    @api.model
    def _add_to_unmatched_models(self, values, config):
        model_no = values.get('model_no')
        existing = self.search([
            ('config_id', '=', config.id),
            ('model_no', '=', model_no)
        ], limit=1)
    
        if existing:
            existing.write({
                'count': existing.count + 1,
                'raw_data': f"{existing.raw_data}\n{str(values)}"
            })
        else:
            self.create({
                'config_id': config.id,
                'supplier_id': config.supplier_id.id,
                'model_no': model_no,
                'pn': values.get('pn'),
                'product_code': values.get('supplier_product_code') or values.get('product_code') or model_no,
                'supplier_product_code': values.get('supplier_product_code') or model_no,
                'raw_data': str(values),
                'count': 1
            })