import base64
import csv
import io
import xlrd
import logging
from odoo.exceptions import UserError
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

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
    supplier_name = fields.Char(compute='_compute_supplier_name', string='Supplier Name')
    sample_file = fields.Binary(string='Sample File')
    sample_file_name = fields.Char(string='Sample File Name')
    product_code = fields.Char(string='Product Code')
    previous_mappings = fields.Text(string='Previous Mappings')
    unmatched_model_ids = fields.One2many('unmatched.model.no', 'config_id', string='Unmatched Model Numbers')
    first_save = fields.Boolean(default=True, string="Is First Save")

    @api.model
    def get_incoming_product_info_fields(self):
        return [(field, self.env['incoming.product.info']._fields[field].string) 
                for field in self.env['incoming.product.info']._fields]

    @api.model
    def action_load_sample_columns(self, **kwargs):
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
        
        self.temp_column_names = ','.join(columns)
        return True
    
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
                    raise UserError(_("All column mappings must have a destination field."))
                if mapping.destination_field_name == 'custom' and not mapping.custom_label:
                    raise UserError(_("Custom fields must have a label."))
                
    def _create_column_mappings(self):
        self.ensure_one()
        ImportColumnMapping = self.env['import.column.mapping']
        
        self.column_mapping.unlink()
        
        if self.temp_column_names:
            for column in self.temp_column_names.split(','):
                ImportColumnMapping.create({
                    'config_id': self.id,
                    'source_column': column.strip(),
                    'destination_field_name': 'custom',
                    'custom_label': column.strip(),
                })
        
        self.temp_column_names = False

    def _find_matching_field(self, column):
        column_lower = column.lower().replace(' ', '_')
        
        if column_lower in self.env['incoming.product.info']._fields:
            return column_lower
        
        if column_lower in ['appkey', 'app_key']:
            return 'app_key'
        if column_lower in ['appkeymode', 'app_key_mode']:
            return 'app_key_mode'
        if column_lower in ['deveui', 'dev_eui']:
            return 'dev_eui'
        if column_lower in ['appeui', 'app_eui']:
            return 'app_eui'
        if column_lower in ['wifissid', 'wifi_ssid']:
            return 'wifi_ssid'
        
        for field in self.env['incoming.product.info']._fields:
            if column_lower in field or field in column_lower:
                return field
        
        if 'product' in column_lower and 'code' in column_lower:
            return 'supplier_product_code'
        if 'serial' in column_lower or 'sn' in column_lower:
            return 'sn'
        
        return False
    
    @api.model_create_multi
    def create(self, vals_list):
        _logger.info(f"Create method called with vals_list: {vals_list}")
        records = super(ImportFormatConfig, self).create(vals_list)
        for record in records:
            _logger.info(f"Created record with ID: {record.id}")
            if record.first_save:
                if record.sample_file:
                    _logger.info(f"Create: Processing sample file for record: {record.id}")
                    record._process_sample_file()
                _logger.info(f"Checking required mappings for first save on record: {record.id}")
                record._check_required_mappings()  # Kontrollera mappningar även vid första sparning
            else:
                _logger.info(f"Ensuring required mappings for non-first save on record: {record.id}")
                record._ensure_required_mappings(record)
                record._check_required_mappings()
        return records
    
    def write(self, vals):
        _logger.info(f"Write called for record {self.id}. Current first_save value: {self.first_save}")
        res = super(ImportFormatConfig, self).write(vals)
        if self.first_save:
            _logger.info(f"Write: Processing for first save on record: {self.id}")
            if 'sample_file' in vals:
                _logger.info(f"Processing sample file for record: {self.id}")
                self._process_sample_file()
            self.first_save = False
            _logger.info(f"Set first_save to False for record: {self.id}")
        else:
            _logger.info(f"Ensuring required mappings for non-first save on record: {self.id}")
            self._ensure_required_mappings(self)
        
        _logger.info(f"Checking required mappings for record: {self.id}")
        self._check_required_mappings()  # Explicit anrop här
        return res
    
    def _ensure_required_mappings(self, configs):
        for config in configs:
            if config.first_save:
                continue
            required_fields = ['sn', 'model_no']
            existing_mappings = config.column_mapping.filtered(lambda m: m.destination_field_name in required_fields)
            
            for field in required_fields:
                mapping = existing_mappings.filtered(lambda m: m.destination_field_name == field)
                if not mapping:
                    self.env['import.column.mapping'].create({
                        'config_id': config.id,
                        'source_column': field.upper(),
                        'destination_field_name': field,
                        'custom_label': field.upper(),
                    })

    @api.constrains('column_mapping')
    def _check_required_mappings(self):
        for config in self:
            if config.first_save:
                _logger.info(f"Skipping required mappings check for first save on record: {config.id}")
                continue
            required_fields = ['sn', 'model_no']
            existing_mappings = config.column_mapping.mapped('destination_field_name')
            missing_fields = set(required_fields) - set(existing_mappings)
            if missing_fields:
                raise UserError(_("The following required fields are missing from the mapping: %s") % ', '.join(missing_fields))
    
    @api.depends('supplier_id')
    def _compute_supplier_name(self):
        for record in self:
            if record.supplier_id.parent_id:
                record.supplier_name = f"{record.supplier_id.parent_id.name} / {record.supplier_id.name}"
            else:
                record.supplier_name = record.supplier_id.name

    def _process_sample_file(self):
        _logger.info(f"_process_sample_file called for record: {self.id}")
        self.ensure_one()
        if not self.sample_file:
            return
    
        file_content = base64.b64decode(self.sample_file)
        
        if self.file_type == 'csv':
            columns = self._read_csv_columns(file_content)
        elif self.file_type == 'excel':
            columns = self._read_excel_columns(file_content)
        else:
            raise UserError(_('Unsupported file type.'))
    
        existing_fields = self.env['incoming.product.info'].fields_get().keys()
        ImportColumnMapping = self.env['import.column.mapping']
    
        # Ta bort befintliga mappningar
        self.column_mapping.unlink()
    
        for column in columns:
            if not column.strip():
                continue
            
            matching_field = self._find_matching_field(column)
            mapping_vals = {
                'config_id': self.id,
                'source_column': column,
                'destination_field_name': matching_field if matching_field in existing_fields else 'custom',
                'custom_label': column or _('Unnamed Column'),
            }
            ImportColumnMapping.create(mapping_vals)
    
    @api.depends('supplier_id')
    def _compute_actual_supplier(self):
        for record in self:
            record.actual_supplier = record.supplier_id.parent_id or record.supplier_id