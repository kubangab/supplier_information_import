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
    previous_mappings = fields.Text(string='Previous Mappings')
    temp_column_names = fields.Text(string='Temporary Column Names')

    @api.model
    def get_incoming_product_info_fields(self):
        return [(field, self.env['incoming.product.info']._fields[field].string) 
                for field in self.env['incoming.product.info']._fields]
    
    @api.model
    def action_load_sample_columns(self):
        self.ensure_one()
        if not self.sample_file:
            return {'warning': {'title': _('Error'), 'message': _('Please upload a sample file first.')}}
    
        file_content = base64.b64decode(self.sample_file)
        
        if self.file_type == 'csv':
            columns = self._read_csv_columns(file_content)
        elif self.file_type == 'excel':
            columns = self._read_excel_columns(file_content)
        else:
            return {'warning': {'title': _('Error'), 'message': _('Unsupported file type.')}}
    
        # Store column names temporarily
        self.temp_column_names = ','.join(columns)
    
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'import.format.config',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
            'context': {'show_column_mapping': True}
        }

    @api.model
    def action_load_sample_columns(self):
        active_id = self._context.get('active_id')
        if not active_id:
            return {'warning': {'title': _('Error'), 'message': _('No active record found.')}}
        
        record = self.browse(active_id)
        if not record.sample_file:
            return {'warning': {'title': _('Error'), 'message': _('Please upload a sample file first.')}}
    
        file_content = base64.b64decode(record.sample_file)
        
        if record.file_type == 'csv':
            columns = self._read_csv_columns(file_content)
        elif record.file_type == 'excel':
            columns = self._read_excel_columns(file_content)
        else:
            return {'warning': {'title': _('Error'), 'message': _('Unsupported file type.')}}
    
        # Store column names temporarily
        record.temp_column_names = ','.join(columns)
    
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'import.format.config',
            'view_mode': 'form',
            'res_id': active_id,
            'target': 'current',
            'context': {'show_column_mapping': True}
        }
    
    @api.model
    def _read_csv_columns(self, file_content):
        csv_data = io.StringIO(file_content.decode('utf-8', errors='replace'))
        reader = csv.reader(csv_data)
        return next(reader, [])
    
    @api.model
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
                
    def _create_column_mappings(self):
        self.ensure_one()
        ImportColumnMapping = self.env['import.column.mapping']
        
        # Remove existing mappings
        self.column_mapping.unlink()
        
        # Create new mappings based on temp_column_names
        if self.temp_column_names:
            for column in self.temp_column_names.split(','):
                ImportColumnMapping.create({
                    'config_id': self.id,
                    'source_column': column.strip(),
                    'destination_field_name': 'custom',
                    'custom_label': column.strip(),
                })
        
        # Clear temp_column_names after mappings have been created
        self.temp_column_names = False
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
            if record.temp_column_names:
                record._create_column_mappings()
        return records

    def write(self, vals):
        result = super(ImportFormatConfig, self).write(vals)
        if 'temp_column_names' in vals:
            for record in self:
                record._create_column_mappings()
        return result

    def _create_column_mappings(self):
        self.ensure_one()
        ImportColumnMapping = self.env['import.column.mapping']
        
        # Remove existing mappings
        self.column_mapping.unlink()
        
        # Create new mappings based on temp_column_names
        if self.temp_column_names:
            for column in self.temp_column_names.split(','):
                ImportColumnMapping.create({
                    'config_id': self.id,
                    'source_column': column.strip(),
                    'destination_field_name': 'custom',
                    'custom_label': column.strip(),
                })
        
        # Clear temp_column_names after mappings have been created
        self.temp_column_names = False
    
class ImportCombinationRule(models.Model):
    _name = 'import.combination.rule'
    _description = 'Import Combination Rule'

    config_id = fields.Many2one('import.format.config', string='Import Configuration')
    name = fields.Char(string='Rule Name', required=True)
    field_1 = fields.Many2one('import.column.mapping', string='Field 1', domain="[('config_id', '=', config_id)]")
    field_2 = fields.Many2one('import.column.mapping', string='Field 2', domain="[('config_id', '=', config_id)]")
    value_1 = fields.Char(string='Value 1', required=True)
    value_2 = fields.Char(string='Value 2', required=True)
    product_id = fields.Many2one('product.product', string='Product')

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

    @api.onchange('field_1', 'field_2', 'value_1', 'value_2')
    def _onchange_fields_values(self):
        if self.field_1 and self.field_2 and self.value_1 and self.value_2:
            self.name = f"{self.value_1} - {self.value_2}"

class ImportColumnMapping(models.Model):
    _name = 'import.column.mapping'
    _description = 'Import Column Mapping'

    config_id = fields.Many2one('import.format.config', string='Import Configuration')
    source_column = fields.Char(string='Source Column Name', readonly=True)
    destination_field_name = fields.Selection(
        selection='_get_destination_field_selection',
        string='Destination Field Name',
        required=True
    )
    custom_label = fields.Char(string='Custom Label', translate=True)
    is_required = fields.Boolean(string='Required', compute='_compute_is_required', store=True)
    is_readonly = fields.Boolean(string='Read Only', compute='_compute_is_readonly', store=True)

    _sql_constraints = [
        ('unique_custom_label_per_config', 
         'UNIQUE(config_id, custom_label)', 
         'Custom label must be unique per configuration.')
    ]

    @api.depends('destination_field_name')
    def _compute_is_required(self):
        for record in self:
            record.is_required = record.destination_field_name in ['sn', 'model_no']

    @api.depends('destination_field_name')
    def _compute_is_readonly(self):
        for record in self:
            record.is_readonly = record.destination_field_name in ['sn', 'model_no']

    @api.depends('destination_field_name', 'source_column')
    def _compute_display_destination_field_name(self):
        for record in self:
            if record.destination_field_name == 'custom':
                record.display_destination_field_name = f"Custom: {record.source_column}"
            else:
                record.display_destination_field_name = dict(self._get_destination_field_selection()).get(record.destination_field_name, '')

    @api.model
    def _get_destination_field_selection(self):
        fields = self.env['incoming.product.info'].fields_get()
        selection = [(name, field['string']) for name, field in fields.items()]
        selection.append(('custom', 'Create New Field'))
        return selection
    
    @api.constrains('custom_label', 'destination_field_name')
    def _check_custom_label(self):
        for record in self:
            if record.id and record.destination_field_name != 'custom' and not record.custom_label:
                raise ValidationError(_("All non-custom fields must have a non-empty custom label."))

    @api.onchange('destination_field_name')
    def _onchange_destination_field_name(self):
        if self.destination_field_name == 'custom':
            self.custom_label = self.source_column
        elif not self.custom_label:
            selection = self._fields['destination_field_name'].selection
            if callable(selection):
                selection = selection(self)
            selection_dict = dict(selection)
            self.custom_label = selection_dict.get(self.destination_field_name, self.destination_field_name)

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get('no_validation'):
            return super(ImportColumnMapping, self.with_context(no_constraints=True)).create(vals_list)
        return super(ImportColumnMapping, self).create(vals_list)

    def write(self, vals):
        if 'destination_field_name' in vals and 'custom_label' not in vals:
            if vals['destination_field_name'] == 'custom':
                vals['custom_label'] = self.source_column
            else:
                selection = self._fields['destination_field_name'].selection
                if callable(selection):
                    selection = selection(self)
                selection_dict = dict(selection)
                vals['custom_label'] = selection_dict.get(vals['destination_field_name'], vals['destination_field_name'])
        return super(ImportColumnMapping, self).write(vals)
    
    @api.model
    def _fill_empty_custom_labels(self):
        empty_labels = self.search([('custom_label', '=', False)])
        for record in empty_labels:
            if record.destination_field_name == 'custom':
                record.custom_label = record.source_column
            else:
                selection = self._fields['destination_field_name'].selection
                if callable(selection):
                    selection = selection(self)
            selection_dict = dict(selection)
            record.custom_label = selection_dict.get(record.destination_field_name, record.destination_field_name)