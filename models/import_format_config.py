import base64
import logging
from odoo.exceptions import UserError
from odoo import models, fields, api, _
from .utils import process_csv, process_excel, log_and_notify

_logger = logging.getLogger(__name__)

class ImportFormatConfig(models.Model):
    _name = 'import.format.config'
    _description = 'Import Format Configuration'

    name = fields.Char(string='Configuration Name', required=True)
    available_field_ids = fields.Many2many('ir.model.fields', compute='_compute_available_field_ids')
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

    # New fields for report configuration
    report_worksheet_name = fields.Char(string='Report Worksheet Name', default='Product Info', translate=False)
    report_field_ids = fields.One2many('report.field.config', 'config_id', string='Report Fields')
    combination_rule_ids = fields.One2many('import.combination.rule', 'config_id', string='Combination Rules')
    second_analysis_field_id = fields.Many2one('import.column.mapping', string='Second Analysis Field')
    second_analysis_field_name = fields.Char(string='Second Analysis Field Name', compute='_compute_second_analysis_field_name')

    @api.model
    def _get_model_no_field(self):
        return self.column_mapping.filtered(lambda m: m.destination_field_name == 'model_no')[:1]

    @api.depends('second_analysis_field_id')
    def _compute_second_analysis_field_name(self):
        for record in self:
            record.second_analysis_field_name = record.second_analysis_field_id.custom_label or record.second_analysis_field_id.source_column

    def _get_second_analysis_field(self):
        self.ensure_one()
        _logger.info(f"_get_second_analysis_field called for config {self.id}")
        result = self.second_analysis_field_id
        _logger.info(f"Returning second analysis field: {result.name if result else 'None'}")
        return result

    @api.depends('column_mapping')
    def _compute_available_field_ids(self):
        for record in self:
            allowed_models = ['product.product', 'sale.order.line', 'stock.move.line', 'incoming.product.info']
            allowed_fields = ['default_code', 'name', 'product_uom_qty', 'lot_id']
            allowed_fields += record.column_mapping.mapped('destination_field_name')

            record.available_field_ids = self.env['ir.model.fields'].search([
                '|',
                '&', ('model', 'in', allowed_models),
                ('name', 'in', allowed_fields),
                ('model', '=', 'incoming.product.info')
            ])

    def get_available_fields(self):
        self.ensure_one()
        IrModelFields = self.env['ir.model.fields']
        allowed_models = ['product.product', 'sale.order.line', 'stock.move.line', 'incoming.product.info']
        allowed_fields = ['default_code', 'product_id', 'product_uom_qty', 'lot_id']
        allowed_fields += self.column_mapping.mapped('destination_field_name')

        return IrModelFields.search([
            ('model', 'in', allowed_models),
            ('name', 'in', allowed_fields)
        ]).ids

    def _get_available_field_ids(self):
        self.ensure_one()
        IrModelFields = self.env['ir.model.fields']
        allowed_models = ['product.product', 'sale.order.line', 'stock.move.line', 'incoming.product.info']
        allowed_fields = ['default_code', 'product_id', 'product_uom_qty', 'lot_id']
        allowed_fields += self.column_mapping.mapped('destination_field_name')

        return IrModelFields.search([
            ('model', 'in', allowed_models),
            ('name', 'in', allowed_fields)
        ]).ids

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
            columns = process_csv(file_content)
        elif self.file_type == 'excel':
            columns = process_excel(file_content)
        else:
            return {'warning': {'title': _('Error'), 'message': _('Unsupported file type.')}}
        
        self.temp_column_names = ','.join(columns)
        return True

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
                record._check_required_mappings()
                record._create_default_report_fields()
            else:
                _logger.info(f"Ensuring required mappings for non-first save on record: {record.id}")
                record._ensure_required_mappings(record)
                record._check_required_mappings()
            
            # Add new fields from column mapping to report fields
            record._update_report_fields_from_mapping()
        
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
        
        try:
            if self.file_type == 'csv':
                data_generator = process_csv(file_content)
            elif self.file_type == 'excel':
                data_generator = process_excel(file_content)
            else:
                raise UserError(_('Unsupported file format.'))
    
            # Get the first chunk of data
            columns = next(data_generator, [])
            if not columns:
                raise UserError(_('No data found in the file.'))
    
            # Use the keys of the first row as column names
            column_names = list(columns[0].keys()) if columns else []
    
            ImportColumnMapping = self.env['import.column.mapping']
    
            # Take bort befintliga mappningar
            self.column_mapping.unlink()
    
            for column in column_names:
                if not column.strip():
                    continue
                
                matching_field = self._find_matching_field(column)
                mapping_vals = {
                    'config_id': self.id,
                    'source_column': column,
                    'destination_field_name': matching_field if matching_field in self.env['incoming.product.info'].fields_get() else 'custom',
                    'custom_label': column or _('Unnamed Column'),
                }
                ImportColumnMapping.create(mapping_vals)
    
        except Exception as e:
            log_and_notify(self,env, _("Error processing sample file: %s") % str(e), error_type="error")
    
    @api.depends('supplier_id')
    def _compute_actual_supplier(self):
        for record in self:
            record.actual_supplier = record.supplier_id.parent_id or record.supplier_id

    def _update_report_fields_from_mapping(self):
        ReportFieldConfig = self.env['report.field.config']
        existing_field_names = self.report_field_ids.mapped('field_id.name')
        
        for mapping in self.column_mapping:
            if mapping.destination_field_name != 'custom' and mapping.destination_field_name not in existing_field_names:
                field = self.env['ir.model.fields'].search([
                    ('model', '=', 'incoming.product.info'),
                    ('name', '=', mapping.destination_field_name),
                ], limit=1)
                if field:
                    ReportFieldConfig.create({
                        'config_id': self.id,
                        'field_id': field.id,
                        'name': mapping.custom_label or field.field_description,
                        'sequence': len(self.report_field_ids) * 10,
                    })
    
    def _create_default_report_fields(self):
        ReportFieldConfig = self.env['report.field.config']
        default_fields = [
            ('product.product', 'default_code', 'SKU'),
            ('sale.order.line', 'name', 'Product'),
            ('sale.order.line', 'product_uom_qty', 'Quantity'),
            ('stock.move.line', 'lot_id', 'Serial Number'),
        ]
        
        for model, field_name, display_name in default_fields:
            field = self.env['ir.model.fields'].search([
                ('model', '=', model),
                ('name', '=', field_name),
            ], limit=1)
            if field and field.name not in self.report_field_ids.mapped('field_id.name'):
                ReportFieldConfig.create({
                    'config_id': self.id,
                    'field_id': field.id,
                    'name': field.field_description or field.name,
                    'sequence': len(self.report_field_ids) * 10,
                })
        
        self._update_report_fields_from_mapping()

    def _get_model_for_field_type(self, field_type):
        
        if field_type == 'sale_order':
            return 'sale.order.line'
        elif field_type == 'stock_picking':
            return 'stock.move.line'
        elif field_type == 'incoming_info':
            return 'incoming.product.info'

    @api.model
    def _get_report_field_domain(self): 
        config_id = self._context.get('config_id')
        if not config_id:
            return []
        
        config = self.browse(config_id)
        return [('id', 'in', config.available_field_ids.ids)]
