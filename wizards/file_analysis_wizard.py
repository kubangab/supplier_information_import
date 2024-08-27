import base64
from odoo import models, fields, api
from odoo.tools.translate import _
from odoo.exceptions import UserError
from ..models.utils import process_csv, process_excel, preprocess_field_value
import logging

_logger = logging.getLogger(__name__)


class FileAnalysisWizard(models.TransientModel):
    _name = 'file.analysis.wizard'
    _description = 'File Analysis Wizard'

    import_config_id = fields.Many2one('import.format.config', string='Import Configuration', required=True)
    file = fields.Binary(string='File', required=True)
    file_name = fields.Char(string='File Name')
    file_type = fields.Selection(related='import_config_id.file_type', readonly=True)
    field_ids = fields.Many2many('import.column.mapping', string='Fields to Analyze', 
                                 domain="[('config_id', '=', import_config_id)]")
    field_names = fields.Char(compute='_compute_field_names', string='Available Fields')
    analysis_result = fields.Text(string='Analysis Result', readonly=True)
    state = fields.Selection([('draft', 'Draft'), ('warning', 'Warning'), ('done', 'Done')], default='draft')
    warning_message = fields.Char(string='Warning Message')
    product_code = fields.Char(string='Product Code')
    filtered_combinations = fields.Text(string='Filtered Combinations')
    
    @api.depends('import_config_id.column_mapping')
    def _compute_field_names(self):
        for record in self:
            field_names = record.import_config_id.column_mapping.mapped('custom_label')
            record.field_names = ', '.join(field_names)

    @api.onchange('import_config_id')
    def _onchange_import_config(self):
        self.ensure_one()
        if self.import_config_id:
            self.field_ids = False

    def action_analyze_file(self):
        self.ensure_one()
        _logger.info("action_analyze_file method called")
        _logger.info("File name: %s", self.file_name)
        if not self.file:
            self.write({'state': 'warning', 'warning_message': _("Please select a file.")})
            return self._reopen_view()
        if len(self.field_ids) != 2:
            self.write({'state': 'warning', 'warning_message': _("Please select exactly two fields for analysis.")})
            return self._reopen_view()
    
        file_content = base64.b64decode(self.file)
        
        try:
            if self.file_type == 'csv':
                _logger.info("Processing CSV file")
                data = process_csv(file_content)
            elif self.file_type == 'excel':
                _logger.info("Processing Excel file")
                data = process_excel(file_content)
            else:
                raise UserError(_("Unsupported file format."))

            if not data:
                raise UserError(_("No data found in the file."))

            _logger.info("Calling _analyze_data method")
            analysis_result, filtered_combinations = self._analyze_data(data)
    
            self.write({
                'analysis_result': analysis_result,
                'filtered_combinations': repr(filtered_combinations) if filtered_combinations else False,
                'state': 'done'
            })
    
            return self._reopen_view()
    
        except Exception as e:
            _logger.error(f"Error during file analysis: {str(e)}", exc_info=True)
            self.write({'state': 'warning', 'warning_message': _(f"Error during file analysis: {str(e)}")})
            return self._reopen_view()

    def _reopen_view(self):
        return {
            'name': _('File Analysis Result'),
            'type': 'ir.actions.act_window',
            'res_model': 'file.analysis.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': {'form_view_initial_mode': 'edit'},
        }

    def _analyze_data(self, data):
        _logger.info("Inside _analyze_data method")
        field1, field2 = self.field_ids
        field1_name = field1.source_column
        field2_name = field2.source_column
        field1_label = field1.custom_label or field1.source_column
        field2_label = field2.custom_label or field2.source_column

        _logger.info(f"Analyzing fields: {field1_name} and {field2_name}")

        existing_rules = self.env['import.combination.rule'].search([
            ('config_id', '=', self.import_config_id.id)
        ])
        existing_combinations = {(rule.value_1.lower(), rule.value_2.lower()) for rule in existing_rules}

        new_combinations = {}
        for chunk in data:
            for row in chunk:
                val1 = row.get(field1_name, '').strip()
                val2 = preprocess_field_value(row.get(field2_name, '').strip())
                
                _logger.info(f"Processing row: {field1_name}={val1}, {field2_name}={val2}")
                
                if not val1 or val2 == 'Zero':
                    _logger.info(f"Skipping row: {field1_name}={val1}, {field2_name}={val2}")
                    continue
                
                key = val1.lower()
                if key not in new_combinations:
                    new_combinations[key] = {'values': set(), 'original': val1}
                new_combinations[key]['values'].add((val2, val2.lower()))

        result = [f"Analysis of {field1_label} and {field2_label} (Potential New Combination Rules):"]
        filtered_combinations = {}

        for val1_lower, data in new_combinations.items():
            val1 = data['original']
            if len(data['values']) > 1:
                for val2, val2_lower in data['values']:
                    if (val1_lower, val2_lower) not in existing_combinations:
                        key = (val1, val2)
                        if key not in filtered_combinations:
                            filtered_combinations[key] = 1
                            result.append(f"{field1_label}: {val1}, {field2_label}: {val2}")

        _logger.info(f"Analysis result: {result}")
        _logger.info(f"Filtered combinations: {filtered_combinations}")
        return "\n".join(result), filtered_combinations

    def action_create_combination_rules(self):
        self.ensure_one()
        new_combinations = eval(self.filtered_combinations)
        ImportCombinationRule = self.env['import.combination.rule']
        
        created_rules = 0
    
        for (val1, val2), _ in new_combinations.items():
            existing_rule = ImportCombinationRule.search([
                ('config_id', '=', self.import_config_id.id),
                ('value_1', '=ilike', val1),
                ('value_2', '=ilike', val2)
            ], limit=1)
            
            if not existing_rule:
                ImportCombinationRule.create({
                    'config_id': self.import_config_id.id,
                    'field_1': self.field_ids[0].id,
                    'field_2': self.field_ids[1].id,
                    'value_1': val1,
                    'value_2': val2,
                    'name': f"{val1} - {val2}",
                })
                created_rules += 1
    
        message = [f"Created {created_rules} new combination rules."]

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': message,
                'type': 'success',
                'sticky': False,
            }
        }