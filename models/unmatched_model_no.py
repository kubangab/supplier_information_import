# models/unmatched_model_no.py

from odoo import models, fields, api

class UnmatchedModelNo(models.Model):
    _name = 'unmatched.model.no'
    _description = 'Unmatched Model Number'

    config_id = fields.Many2one('import.format.config', string='Import Configuration')
    model_no = fields.Char(string='Model Number')
    product_code = fields.Char(string='Product Code')
    product_id = fields.Many2one('product.product', string='Product')

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.product_code = self.product_id.default_code