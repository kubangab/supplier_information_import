from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json
import logging

_logger = logging.getLogger(__name__)

class ImportCombinationRule(models.Model):
    _name = 'import.combination.rule'
    _inherit = 'product.selection.mixin'
    _description = 'Import Combination Rule'
    _order = 'name'

    config_id = fields.Many2one('import.format.config', string='Import Configuration')
    supplier_id = fields.Many2one(related='config_id.supplier_id', store=True, readonly=True)
    name = fields.Char(string='Rule Name', required=True, index=True)
    field_1 = fields.Many2one('import.column.mapping', string='Field 1', readonly=True)
    field_2 = fields.Many2one('import.column.mapping', string='Field 2', readonly=True)
    value_1 = fields.Char(string='Value 1', required=True)
    value_2 = fields.Char(string='Value 2', required=True)
    combination_pattern = fields.Char(string='Combination Pattern', required=True, default="{0}-{1}")
    regex_pattern = fields.Char(string='Regex Pattern')
    count = fields.Integer(string='Count', default=0)
    applied_serial_numbers = fields.Text(string='Applied Serial Numbers')
    product_id = fields.Many2one('product.product', string='Product Variant')


    @api.model
    def default_get(self, fields_list):
        res = super(ImportCombinationRule, self).default_get(fields_list)
        if self._context.get('default_config_id'):
            config = self.env['import.format.config'].browse(self._context['default_config_id'])
            model_no_field = config._get_model_no_field()
            second_field = config._get_second_analysis_field()
            if model_no_field:
                res['field_1'] = model_no_field.id
                res['value_1'] = _('Model No.')
            if second_field:
                res['field_2'] = second_field.id
                res['value_2'] = second_field.custom_label or second_field.source_column
        return res

    @api.onchange('config_id')
    def _onchange_config_id(self):
        _logger.info(f"_onchange_config_id called with config_id: {self.config_id.id}")
        if self.config_id:
            model_no_field = self.config_id._get_model_no_field()
            second_field = self.config_id._get_second_analysis_field()
            _logger.info(f"model_no_field: {model_no_field.name if model_no_field else 'None'}, second_field: {second_field.name if second_field else 'None'}")
            if model_no_field:
                self.field_1 = model_no_field
                self.value_1 = _('Model No.')
                _logger.info(f"Set field_1 to {self.field_1.name} and value_1 to {self.value_1}")
            if second_field:
                self.field_2 = second_field
                self.value_2 = second_field.custom_label or second_field.source_column
                _logger.info(f"Set field_2 to {self.field_2.name} and value_2 to {self.value_2}")
            else:
                _logger.warning("Second analysis field is not set in the configuration")

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