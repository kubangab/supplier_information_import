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
    supplier_id = fields.Many2one('res.partner', string='Supplier', domain=[('supplier_rank', '>', 0)])
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

class ImportColumnMapping(models.Model):
    _name = 'import.column.mapping'
    _description = 'Import Column Mapping'

    config_id = fields.Many2one('import.format.config', string='Import Configuration')
    source_column = fields.Char(string='Source Column Name', required=True)
    destination_field = fields.Many2one('ir.model.fields', string='Destination Field', 
                                        domain=[('model', '=', 'incoming.product.info')])
    is_required = fields.Boolean(string='Required', default=False)
    field_type = fields.Char(string='Field Type', compute='_compute_field_type', store=True)

    @api.model
    def _get_field_types(self):
        return self.env['ir.model.fields']._fields['ttype'].selection

    @api.model
    def create(self, vals):
        if 'destination_field_name' in vals:
            vals = self._set_destination_field(vals)
        return super(ImportColumnMapping, self).create(vals)

    def write(self, vals):
        if 'destination_field_name' in vals:
            vals = self._set_destination_field(vals)
        return super(ImportColumnMapping, self).write(vals)

    def _set_destination_field(self, vals):
        if vals.get('destination_field_name'):
            field = self.env['ir.model.fields'].search([
                ('model', '=', 'incoming.product.info'),
                ('field_description', '=like', vals['destination_field_name'] + '%')
            ], limit=1)
            
            if field:
                vals['destination_field'] = field.id
                vals['field_type'] = field.ttype
            else:
                # Create a new field if it doesn't exist
                new_field = self.env['ir.model.fields'].create({
                    'model': 'incoming.product.info',
                    'name': vals['destination_field_name'].lower().replace(' ', '_'),
                    'field_description': vals['destination_field_name'],
                    'ttype': 'char',  # Default to char, can be changed later
                })
                vals['destination_field'] = new_field.id
                vals['field_type'] = 'char'
        
        return vals

    @api.onchange('destination_field_name')
    def _onchange_destination_field_name(self):
        if self.destination_field_name:
            field = self.env['ir.model.fields'].search([
                ('model', '=', 'incoming.product.info'),
                ('field_description', '=like', self.destination_field_name + '%')
            ], limit=1)
            if field:
                self.destination_field = field.id
                self.field_type = field.ttype
            else:
                self.destination_field = False
                self.field_type = False

    @api.depends('destination_field')
    def _compute_field_type(self):
        for record in self:
            record.field_type = record.destination_field.ttype if record.destination_field else False

    def name_get(self):
        return [(record.id, record.destination_field.field_description) for record in self]
    
    @api.onchange('destination_field')
    def _onchange_destination_field(self):
        if self.destination_field:
            self.field_type = self.destination_field.ttype
        else:
            self.field_type = False

    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100, name_get_uid=None):
        args = args or []
        domain = []
        if name:
            domain = [('field_description', operator, name)]
        return self.env['ir.model.fields'].search(domain + [('model', '=', 'incoming.product.info')] + args, limit=limit).name_get()