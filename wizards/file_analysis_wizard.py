from odoo import models, fields, api, _
import base64
import csv
import io
import xlrd

class FileAnalysisWizard(models.TransientModel):
    _name = 'file.analysis.wizard'
    _description = 'File Analysis Wizard'

    import_config_id = fields.Many2one('import.format.config', string='Import Configuration', required=True)
    file = fields.Binary(string='File', required=True)
    file_name = fields.Char(string='File Name')
    file_type = fields.Selection(related='import_config_id.file_type', readonly=True)
    field_ids = fields.Many2many('import.column.mapping', string='Fields to Analyze', 
                                 domain="[('config_id', '=', import_config_id)]")
    field_selection = fields.Char(compute='_compute_field_selection', store=True)
    analysis_result = fields.Text(string='Analysis Result', readonly=True)

    @api.depends('import_config_id', 'field_ids')
    def _compute_field_selection(self):
        for record in self:
            field_names = record.field_ids.mapped(lambda f: f.custom_label or f.source_column)
            record.field_selection = ','.join(field_names)

    @api.onchange('import_config_id')
    def _onchange_import_config(self):
        self.field_ids = self.import_config_id.column_mapping

    def action_analyze_file(self):
        if not self.file:
            return {'warning': {'title': _("Error"), 'message': _("Please upload a file.")}}

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
        analysis = {}
        for field in self.field_ids:
            field_name = field.custom_label or field.source_column
            unique_values = set(row.get(field.source_column, '') for row in data)
            analysis[field_name] = list(unique_values)

        result = []
        for field, values in analysis.items():
            result.append(f"Field: {field}")
            result.append("Unique values:")
            for value in values:
                result.append(f"  - {value}")
            result.append("")

        return "\n".join(result)