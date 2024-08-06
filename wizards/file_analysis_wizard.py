import base64
import csv
import io
import xlrd
from odoo import models, fields, api, _
from odoo.exceptions import UserError

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
            field_names = [field.custom_label or field.source_column for field in record.import_config_id.column_mapping]
            record.field_names = ', '.join(field_names)

    @api.onchange('import_config_id')
    def _onchange_import_config(self):
        self.ensure_one()
        if self.import_config_id:
            self.field_ids = False

    def action_analyze_file(self):
        self.ensure_one()
        if not self.file:
            self.write({'state': 'warning', 'warning_message': _("Please select a file.")})
            return self._reopen_view()
        if len(self.field_ids) != 2:
            self.write({'state': 'warning', 'warning_message': _("Please select exactly two fields for analysis.")})
            return self._reopen_view()
    
        file_content = base64.b64decode(self.file)
        
        try:
            if self.file_type == 'csv':
                data = self._process_csv(file_content)
            elif self.file_type == 'excel':
                data = self._process_excel(file_content)
            else:
                raise UserError(_("Unsupported file format."))
    
            if not data:
                raise UserError(_("No data found in the file."))
    
            analysis_result, filtered_combinations = self._analyze_data(data)
    
            self.write({
                'analysis_result': analysis_result,
                'filtered_combinations': repr(filtered_combinations) if filtered_combinations else False,
                'state': 'done'
            })
    
            return self._reopen_view()
    
        except Exception as e:
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

    def _process_csv(self, file_content):
        csv_data = io.StringIO(file_content.decode('utf-8'))
        reader = csv.DictReader(csv_data, delimiter=';')
        return list(reader)
    
    def _process_excel(self, file_content):
        workbook = xlrd.open_workbook(file_contents=file_content)
        sheet = workbook.sheet_by_index(0)
        headers = [str(cell.value).strip() for cell in sheet.row(0)]
        
        data = []
        for i in range(1, sheet.nrows):
            row_data = {}
            for col, header in enumerate(headers):
                cell_value = sheet.cell_value(i, col)
                if isinstance(cell_value, float) and cell_value.is_integer():
                    cell_value = int(cell_value)
                row_data[header] = str(cell_value).strip()
            data.append(row_data)
        
        return data

    def _analyze_data(self, data):
        field1, field2 = self.field_ids
        field1_name = field1.source_column
        field2_name = field2.source_column

        existing_rules = self.env['import.combination.rule'].search([
            ('config_id', '=', self.import_config_id.id)
        ])
        existing_combinations = {(rule.value_1, rule.value_2) for rule in existing_rules}

        new_combinations = {}
        for row in data:
            val1 = row.get(field1_name, '').strip()
            val2 = row.get(field2_name, '').strip()
            
            if not val1 or not val2:
                continue
            
            key = (val1, val2)
            if key not in existing_combinations:
                new_combinations[key] = new_combinations.get(key, 0) + 1

        filtered_combinations = {k: v for k, v in new_combinations.items() 
                                 if len([c for c in new_combinations if c[0] == k[0]]) > 1}

        sorted_combinations = sorted(filtered_combinations.items(), key=lambda x: x[0][0])

        result = [f"Analysis of {field1_name} and {field2_name} (New Combinations):"]
        for (val1, val2), count in sorted_combinations:
            result.append(f"{field1_name}: {val1}, {field2_name}: {val2} - Count: {count}")

        return "\n".join(result), dict(sorted_combinations)

    def action_create_combination_rules(self):
        self.ensure_one()
        filtered_combinations = eval(self.filtered_combinations)
        ImportCombinationRule = self.env['import.combination.rule']
        
        for (val1, val2), _ in filtered_combinations.items():
            existing_rule = ImportCombinationRule.search([
                ('config_id', '=', self.import_config_id.id),
                ('value_1', '=', val1),
                ('value_2', '=', val2)
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

        return {
            'name': 'Combination Rules',
            'type': 'ir.actions.act_window',
            'res_model': 'import.combination.rule',
            'view_mode': 'tree,form',
            'domain': [('config_id', '=', self.import_config_id.id)],
            'context': {'default_config_id': self.import_config_id.id},
        }

class ImportColumnMapping(models.Model):
    _inherit = 'import.column.mapping'

    def name_get(self):
        return [(record.id, record.custom_label or record.source_column) for record in self]