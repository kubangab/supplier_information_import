import base64
import csv
import io
import xlrd
from odoo import models, fields, api, exceptions, _

class ImportFormatConfig(models.Model):
    _name = 'import.format.config'
    _description = 'Import Format Configuration'

    name = fields.Char(string='Configuration Name', required=True)
    file_type = fields.Selection([
        ('csv', 'CSV'),
        ('excel', 'Excel')
    ], string='File Type', required=True)
    column_mapping = fields.One2many('import.column.mapping', 'config_id', string='Column Mappings')
    supplier_id = fields.Many2one('res.partner', string='Supplier', domain=[('supplier_rank', '>', 0)], required=True)
    sample_file = fields.Binary(string='Sample File')
    sample_file_name = fields.Char(string='Sample File Name')

    @api.model
    def get_incoming_product_info_fields(self):
        return self.env['incoming.product.info'].fields_get()
    
    def action_load_sample_file(self):
        self.ensure_one()
        if not self.sample_file:
            raise exceptions.UserError('Please upload a sample file first.')

        file_content = base64.b64decode(self.sample_file)
        
        if self.file_type == 'csv':
            columns = self._read_csv_columns(file_content)
        elif self.file_type == 'excel':
            columns = self._read_excel_columns(file_content)
        else:
            raise exceptions.UserError('Unsupported file type.')

        self._create_column_mappings(columns)

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def _read_csv_columns(self, file_content):
        csv_data = io.StringIO(file_content.decode('utf-8', errors='replace'))
        reader = csv.reader(csv_data)
        return next(reader, [])

    def _read_excel_columns(self, file_content):
        workbook = xlrd.open_workbook(file_contents=file_content)
        sheet = workbook.sheet_by_index(0)
        return [sheet.cell_value(0, col) for col in range(sheet.ncols)]

    @api.constrains('column_mapping')
    def _check_column_mapping(self):
        for record in self:
            if any(not mapping.destination_field for mapping in record.column_mapping):
                raise ValidationError(_("All column mappings must have a destination field."))

    def _create_column_mappings(self, columns):
        ColumnMapping = self.env['import.column.mapping']
        existing_mappings = {m.source_column: m for m in self.column_mapping}
        
        for column in columns:
            if column not in existing_mappings:
                # Try to find a matching field
                matching_field = self._find_matching_field(column)
                ColumnMapping.create({
                    'config_id': self.id,
                    'source_column': column,
                    'destination_field': matching_field.id if matching_field else False,
                })

    def _find_matching_field(self, column):
        fields = self.get_incoming_product_info_fields()
        column_lower = column.lower().replace(' ', '_')
        
        # Direkt matchning
        if column_lower in fields:
            return self.env['ir.model.fields'].search([
                ('model', '=', 'incoming.product.info'),
                ('name', '=', column_lower)
            ], limit=1)
        
        # Fuzzy matchning
        for field in fields:
            if column_lower in field or field in column_lower:
                return self.env['ir.model.fields'].search([
                    ('model', '=', 'incoming.product.info'),
                    ('name', '=', field)
                ], limit=1)
        
        # Speciella fall
        if 'product' in column_lower and 'code' in column_lower:
            return self.env['ir.model.fields'].search([
                ('model', '=', 'incoming.product.info'),
                ('name', '=', 'supplier_product_code')
            ], limit=1)
        if 'serial' in column_lower or 'sn' in column_lower:
            return self.env['ir.model.fields'].search([
                ('model', '=', 'incoming.product.info'),
                ('name', '=', 'sn')
            ], limit=1)
        
        return False
    
    @api.model
    def create(self, vals):
        record = super(ImportFormatConfig, self).create(vals)
        if record.sample_file:
            record.action_load_sample_file()
        return record

    def write(self, vals):
        res = super(ImportFormatConfig, self).write(vals)
        if 'sample_file' in vals:
            self.action_load_sample_file()
        return res

class ImportColumnMapping(models.Model):
    _name = 'import.column.mapping'
    _description = 'Import Column Mapping'

    config_id = fields.Many2one('import.format.config', string='Import Configuration')
    source_column = fields.Char(string='Source Column Name', required=True)
    destination_field = fields.Many2one('ir.model.fields', string='Destination Field', 
                                        domain=[('model', '=', 'incoming.product.info')], 
                                        ondelete='restrict')  # Changed back to 'restrict'
    custom_label = fields.Char(string='Custom Label', translate=True)
    is_required = fields.Boolean(string='Required')

    @api.onchange('destination_field')
    def _onchange_destination_field(self):
        if self.destination_field:
            self.custom_label = self.destination_field.field_description