from odoo import models, fields, api, _
from .product_selection_mixin import ProductSelectionMixin

class UnmatchedModelNo(models.Model, ProductSelectionMixin):
    _name = 'unmatched.model.no'
    _inherit = 'product.selection.mixin'
    _description = 'Unmatched Model Number'
    _order = 'model_no'

    config_id = fields.Many2one('import.format.config', string='Configuration', required=True)
    supplier_id = fields.Many2one('res.partner', string='Supplier', required=True)
    model_no = fields.Char(string='Model Number', required=True, index=True)
    model_no_lower = fields.Char(string='Model Number (Lowercase)', required=True, index=True)
    pn = fields.Char(string='PN')
    product_code = fields.Char(string='Product Code')
    supplier_product_code = fields.Char(string='Supplier Product Code')
    product_id = fields.Many2one('product.product', string='Product Variant')
    count = fields.Integer(string='Count', default=1)
    raw_data = fields.Text(string='Raw Data')
    sequence = fields.Integer(string='Sequence', default=10)

    product_selection = fields.Selection(selection='_get_product_codes', string='Product Selection')

    def name_get(self):
        result = []
        for record in self:
            name = record.model_no
            if " / " in name:
                name = name.split(" / ")[0] + f" (+ variations)"
            result.append((record.id, f"{name} - {record.pn}" if record.pn else name))
        return result

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        args = args or []
        if name:
            args = ['|', '|', '|',
                    ('model_no', operator, name),
                    ('pn', operator, name),
                    ('product_code', operator, name),
                    ('supplier_product_code', operator, name)] + args
        return super(UnmatchedModelNo, self).name_search(name, args, operator, limit)

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

    @api.model
    def sort_records(self, config_id):
        try:
            records = self.search([('config_id', '=', config_id)], order='count desc, model_no')
            for i, record in enumerate(records):
                record.sequence = i
        except Exception as e:
            _logger.error(f"Error sorting unmatched model records: {str(e)}")
            # Don't raise the exception, just log it