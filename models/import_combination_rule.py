from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json


class ImportCombinationRule(models.Model):
    _name = 'import.combination.rule'
    _inherit = 'product.selection.mixin'
    _description = 'Import Combination Rule'
    _order = 'name'

    config_id = fields.Many2one('import.format.config', string='Import Configuration')
    supplier_id = fields.Many2one(related='config_id.supplier_id', store=True, readonly=True)
    name = fields.Char(string='Rule Name', required=True, index=True)
    field_1 = fields.Many2one('import.column.mapping', string='Field 1', domain="[('config_id', '=', config_id)]")
    field_2 = fields.Many2one('import.column.mapping', string='Field 2', domain="[('config_id', '=', config_id)]")
    value_1 = fields.Char(string='Value 1', required=True)
    value_2 = fields.Char(string='Value 2', required=True)
    combination_pattern = fields.Char(string='Combination Pattern', required=True, default="{0}-{1}")
    regex_pattern = fields.Char(string='Regex Pattern')
    count = fields.Integer(string='Count', default=0)
    applied_serial_numbers = fields.Text(string='Applied Serial Numbers')
    product_id = fields.Many2one('product.product', string='Product Variant')


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

    @api.onchange('config_id')
    def _onchange_config_id(self):
        return {'domain': {'product_id': self._get_product_domain()}}

    @api.model
    def update_rule_count(self, rule_id, serial_number):
        rule = self.browse(rule_id)
        applied_sns = json.loads(rule.applied_serial_numbers or '{}')
        
        if serial_number not in applied_sns:
            applied_sns[serial_number] = True
            rule.write({
                'count': len(applied_sns),
                'applied_serial_numbers': json.dumps(applied_sns)
            })
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'name' not in vals and 'value_1' in vals and 'value_2' in vals:
                vals['name'] = f"{vals['value_1']} - {vals['value_2']}"
        return super(ImportCombinationRule, self).create(vals_list)

    def write(self, vals):
        if 'value_1' in vals or 'value_2' in vals:
            vals['name'] = f"{vals.get('value_1', self.value_1)} - {vals.get('value_2', self.value_2)}"
        return super(ImportCombinationRule, self).write(vals)