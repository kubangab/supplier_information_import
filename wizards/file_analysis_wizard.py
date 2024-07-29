from odoo import models, fields, api, _
import base64
import csv
import io
import xlrd
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

    @api.depends('import_config_id.column_mapping')
    def _compute_field_names(self):
        for record in self:
            field_names = [field.custom_label or field.source_column for field in record.import_config_id.column_mapping]
            record.field_names = ', '.join(field_names)

    @api.onchange('import_config_id')
    def _onchange_import_config(self):
        self.ensure_one()
        if self.import_config_id:
            self.field_ids = False  # Clear previous selection
            _logger.info(f"Loaded {len(self.import_config_id.column_mapping)} fields for config {self.import_config_id.name}")
            for field in self.import_config_id.column_mapping:
                _logger.info(f"Field: {field.custom_label or field.source_column} (ID: {field.id})")

    def action_analyze_file(self):
        self.ensure_one()
        if not self.file:
            return {'warning': {'title': _("Error"), 'message': _("Please upload a file.")}}
        if len(self.field_ids) != 2:
            return {'warning': {'title': _("Error"), 'message': _("Please select exactly two fields for analysis.")}}

        file_content = base64.b64decode(self.file)
        
        if self.file_type == 'csv':
            data = self._process_csv(file_content)
        elif self.file_type == 'excel':
            data = self._process_excel(file_content)
        else:
            return {'warning': {'title': _("Error"), 'message': _("Unsupported file type.")}}

        analysis_result = self._analyze_data(data)
        self.write({'analysis_result': analysis_result})

        return {
            'name': _('File Analysis Result'),
            'type': 'ir.actions.act_window',
            'res_model': 'file.analysis.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    def _process_csv(self, file_content):
        csv_data = io.StringIO(file_content.decode('utf-8'))
        reader = csv.DictReader(csv_data)
        return list(reader)

    def _process_excel(self, file_content):
        book = xlrd.open_workbook(file_contents=file_content)
        sheet = book.sheet_by_index(0)
        headers = [cell.value for cell in sheet.row(0)]
        return [dict(zip(headers, [cell.value for cell in sheet.row(i)])) for i in range(1, sheet.nrows)]

    def _analyze_data(self, data):
        field1, field2 = self.field_ids
        field1_name = field1.custom_label or field1.source_column
        field2_name = field2.custom_label or field2.source_column

        combinations = {}
        for row in data:
            key = (row.get(field1.source_column, ''), row.get(field2.source_column, ''))
            combinations[key] = combinations.get(key, 0) + 1

        result = [f"Analysis of {field1_name} and {field2_name}:"]
        for (val1, val2), count in combinations.items():
            result.append(f"{field1_name}: {val1}, {field2_name}: {val2} - Count: {count}")

        return "\n".join(result)

class ImportColumnMapping(models.Model):
    _inherit = 'import.column.mapping'

    def name_get(self):
        return [(record.id, record.custom_label or record.source_column) for record in self]