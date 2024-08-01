from odoo import models, fields, api, _
from odoo.exceptions import UserError

class ImportCombinationRule(models.Model):
    _name = 'import.combination.rule'
    _description = 'Import Combination Rule'

    config_id = fields.Many2one('import.format.config', string='Import Configuration')
    name = fields.Char(string='Rule Name', required=True)
    field_1 = fields.Many2one('import.column.mapping', string='Field 1', domain="[('config_id', '=', config_id)]")
    field_2 = fields.Many2one('import.column.mapping', string='Field 2', domain="[('config_id', '=', config_id)]")
    value_1 = fields.Char(string='Value 1', required=True)
    value_2 = fields.Char(string='Value 2', required=True)
    product_id = fields.Many2one('product.product', string='Product')
    combination_pattern = fields.Char(string='Combination Pattern', required=True, default="{0}-{1}")
    regex_pattern = fields.Char(string='Regex Pattern')

    @api.constrains('field_1', 'field_2')
    def _check_fields(self):
        for rule in self:
            if rule.field_1 == rule.field_2:
                raise UserError(_("Field 1 and Field 2 must be different"))

    @api.constrains('combination_pattern')
    def _check_combination_pattern(self):
        for rule in self:
            if '{0}' not in rule.combination_pattern or '{1}' not in rule.combination_pattern:
                raise UserError(_("Combination Pattern must contain both {0} and {1}"))

    @api.onchange('field_1', 'field_2', 'value_1', 'value_2')
    def _onchange_fields_values(self):
        if self.field_1 and self.field_2 and self.value_1 and self.value_2:
            self.name = f"{self.value_1} - {self.value_2}"