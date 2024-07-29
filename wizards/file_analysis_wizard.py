from odoo import models, fields, api, _
import base64
import csv
import io
import xlrd

class FileAnalysisWizard(models.TransientModel):
    _name = 'file.analysis.wizard'
    _description = 'File Analysis Wizard'

    file = fields.Binary(string='File', required=True)
    file_name = fields.Char(string='File Name')
    file_type = fields.Selection([
        ('csv', 'CSV'),
        ('excel', 'Excel')
    ], string='File Type', required=True)
    field_ids = fields.Many2many('import.column.mapping', string='Fields to Analyze')
    analysis_result = fields.Text(string='Analysis Result', readonly=True)

    @api.onchange('file', 'file_name')
    def _onchange_file(self):
        if self.file_name:
            if self.file_name.endswith('.csv'):
                self.file_type = 'csv'
            elif self.file_name.endswith(('.xls', '.xlsx')):
                self.file_type = 'excel'

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
            unique_values = set(row.get(field.source_column, '') for row in data)
            analysis[field.source_column] = list(unique_values)

        result = []
        for field, values in analysis.items():
            result.append(f"Field: {field}")
            result.append("Unique values:")
            for value in values:
                result.append(f"  - {value}")
            result.append("")

        return "\n".join(result)