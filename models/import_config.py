import base64
import csv
import io
import xlrd
from odoo import models, fields, api, exceptions, _

class ImportFormatConfig(models.Model):
    _name = 'import.format.config'
    _description = 'Import Format Configuration'

    name = fields.Char(string='Configuration Name', required=True)
    combination_rule_ids = fields.One2many('import.combination.rule', 'config_id', string='Combination Rules')
    file_type = fields.Selection([
        ('csv', 'CSV'),
        ('excel', 'Excel')
    ], string='File Type', required=True)
    column_mapping = fields.One2many('import.column.mapping', 'config_id', string='Column Mappings')
    supplier_id = fields.Many2one('res.partner', string='Supplier', domain=[('supplier_rank', '>', 0)], required=True)
    sample_file = fields.Binary(string='Sample File')
    sample_file_name = fields.Char(string='Sample File Name')
    product_code = fields.Char(string='Product Code')

    @api.model
    def get_incoming_product_info_fields(self):
        return [(field, self.env['incoming.product.info']._fields[field].string) 
                for field in self.env['incoming.product.info']._fields]
    
    def action_load_sample_file(self):
        self.ensure_one()
        if not self.sample_file:
            raise exceptions.UserError(_('Please upload a sample file first.'))

        file_content = base64.b64decode(self.sample_file)
        
        if self.file_type == 'csv':
            columns = self._read_csv_columns(file_content)
        elif self.file_type == 'excel':
            columns = self._read_excel_columns(file_content)
        else:
            raise exceptions.UserError(_('Unsupported file type.'))

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
            for mapping in record.column_mapping:
                if not mapping.destination_field_name:
                    raise ValidationError(_("All column mappings must have a destination field."))
                if mapping.destination_field_name == 'custom' and not mapping.custom_label:
                    raise ValidationError(_("Custom fields must have a label."))
                
    def _create_column_mappings(self, columns):
        ColumnMapping = self.env['import.column.mapping']
        existing_mappings = {m.source_column: m for m in self.column_mapping}
        
        for column in columns:
            if column not in existing_mappings:
                matching_field = self._find_matching_field(column)
                ColumnMapping.create({
                    'config_id': self.id,
                    'source_column': column,
                    'destination_field_name': matching_field if matching_field else 'custom',
                    'custom_label': column if not matching_field else '',
                })

    def _find_matching_field(self, column):
        fields = dict(self.env['import.column.mapping']._get_destination_field_selection())
        column_lower = column.lower().replace(' ', '_')
        
        # Direct matching
        if column_lower in fields:
            return column_lower
        
        # Fuzzy matching
        for field in fields:
            if column_lower in field or field in column_lower:
                return field
        
        # Special cases
        if 'product' in column_lower and 'code' in column_lower:
            return 'supplier_product_code'
        if 'serial' in column_lower or 'sn' in column_lower:
            return 'sn'
        
        return False
    
    @api.model_create_multi
    def create(self, vals_list):
        records = super(ImportFormatConfig, self).create(vals_list)
        for record in records:
            if record.sample_file:
                record.action_load_sample_file()
        return records

    def write(self, vals):
        res = super(ImportFormatConfig, self).write(vals)
        if 'sample_file' in vals:
            self.action_load_sample_file()
        return res
    
class ImportCombinationRule(models.Model):
    _name = 'import.combination.rule'
    _description = 'Import Combination Rule'

    config_id = fields.Many2one('import.format.config', string='Import Configuration')
    name = fields.Char(string='Rule Name', required=True)
    field_1 = fields.Many2one('import.column.mapping', string='Field 1', domain="[('config_id', '=', config_id)]")
    field_2 = fields.Many2one('import.column.mapping', string='Field 2', domain="[('config_id', '=', config_id)]")
    combination_pattern = fields.Char(string='Combination Pattern', required=True, 
                                      help="Use {1} and {2} to represent fields. E.g., '{1}-{2}'")
    regex_pattern = fields.Char(string='Regex Pattern', 
                                help="Optional regex pattern to extract information from combined fields")
    # New field for product code
    product_code = fields.Char(string='Product Code')

    @api.constrains('field_1', 'field_2')
    def _check_fields(self):
        for rule in self:
            if rule.field_1 == rule.field_2:
                raise exceptions.ValidationError(_("Field 1 and Field 2 must be different"))

    @api.constrains('combination_pattern')
    def _check_combination_pattern(self):
        for rule in self:
            if '{1}' not in rule.combination_pattern or '{2}' not in rule.combination_pattern:
                raise exceptions.ValidationError(_("Combination Pattern must contain both {1} and {2}"))



class ImportColumnMapping(models.Model):
    _name = 'import.column.mapping'
    _description = 'Import Column Mapping'

    config_id = fields.Many2one('import.format.config', string='Import Configuration')
    source_column = fields.Char(string='Source Column Name', required=True)
    destination_field_name = fields.Selection(
        selection='_get_destination_field_selection',
        string='Destination Field Name',
        required=True
    )
    custom_label = fields.Char(string='Custom Label', translate=True)
    is_required = fields.Boolean(string='Required')

    rule_field_1_ids = fields.One2many('import.combination.rule', 'field_1', string='Rules using as Field 1')
    rule_field_2_ids = fields.One2many('import.combination.rule', 'field_2', string='Rules using as Field 2')

    @api.model
    def _get_destination_field_selection(self):
        fields = self.env['incoming.product.info'].fields_get()
        selection = [(name, field['string']) for name, field in fields.items()]
        selection.append(('custom', 'Custom Field'))
        return selection

    @api.onchange('destination_field_name')
    def _onchange_destination_field_name(self):
        if self.destination_field_name:
            if self.destination_field_name == 'custom':
                self.custom_label = self.source_column
            else:
                fields = dict(self._get_destination_field_selection())
                self.custom_label = fields.get(self.destination_field_name, self.destination_field_name)

    @api.constrains('destination_field_name', 'custom_label')
    def _check_custom_field(self):
        for record in self:
            if record.destination_field_name == 'custom' and not record.custom_label:
                raise ValidationError(_("Custom fields must have a label."))