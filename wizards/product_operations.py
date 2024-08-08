import base64
import csv
import io
import xlrd
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class ImportProductInfo(models.TransientModel):
    _name = 'import.product.info'
    _description = 'Import Product Information'

    file = fields.Binary(string='File', required=True)
    file_name = fields.Char(string='File Name')
    import_config_id = fields.Many2one('import.format.config', string='Import Configuration', required=True)

    @api.model
    def import_file(self, wizard_id):
        wizard = self.browse(wizard_id)
        if not wizard.exists():
            raise UserError(_('Import wizard not found.'))
        
        if not wizard.file:
            raise UserError(_('Please select a file to import.'))
        
        config = wizard.import_config_id
        if not config:
            raise UserError(_('Please select an import configuration.'))
    
        file_content = base64.b64decode(wizard.file)
        
        try:
            if config.file_type == 'csv':
                data = self._process_csv(file_content)
            elif config.file_type == 'excel':
                data = self._process_excel(file_content)
            else:
                raise UserError(_('Unsupported file format. Please use CSV or Excel files.'))
    
            if not data:
                raise UserError(_('No data found in the file.'))
    
            IncomingProductInfo = self.env['incoming.product.info']
            
            to_create = []
            to_update = []
            unmatched_models = {}
            errors = []

            to_create = []
            for index, row in enumerate(data, start=1):
                try:
                    values = self._process_row_values(row, config)
                    
                    # Check for required fields
                    required_fields = ['sn']
                    missing_fields = [field for field in required_fields if field not in values or not values[field]]
                    
                    if missing_fields:
                        errors.append((index, row, _(f"Missing required fields: {', '.join(missing_fields)}")))
                        continue
        
                    if not values.get('model_no') and not values.get('supplier_product_code'):
                        errors.append((index, row, _("Unable to determine Model Number or Supplier Product Code")))
                        continue
        
                    product = IncomingProductInfo._search_product(values, config)
                    if product:
                        values['product_id'] = product.id
                        values['supplier_id'] = config.supplier_id.id
                        values['state'] = 'pending'
        
                        existing_info = IncomingProductInfo.search([
                            ('supplier_id', '=', config.supplier_id.id),
                            ('sn', '=', values['sn'])
                        ], limit=1)
        
                        if existing_info:
                            existing_info.write(values)
                            to_update.append(existing_info)
                            _logger.info(f"Updated existing record for SN: {values['sn']}")
                        else:
                            to_create.append(values)
                            _logger.info(f"Prepared new record for creation, SN: {values['sn']}")
                    else:
                        unmatched_models.setdefault(values.get('model_no') or values.get('supplier_product_code'), []).append(values)
                        _logger.warning(f"No product found for row {index}, model_no: {values.get('model_no')}, supplier_product_code: {values.get('supplier_product_code')}")
        
                except Exception as e:
                    errors.append((index, row, str(e)))
                    _logger.error(f"Error processing row {index}: {str(e)}", exc_info=True)
        
            # Create new records
            if to_create:
                new_records = IncomingProductInfo.create(to_create)
                _logger.info(f"Created {len(new_records)} new records")
                for record in new_records:
                    self._create_or_update_lot(record)
        
            # Update existing records
            for existing in to_update:
                self._create_or_update_lot(existing)
            _logger.info(f"Updated {len(to_update)} existing records")

            # Handle unmatched models
            UnmatchedModelNo = self.env['unmatched.model.no']
            for model_no, model_values in unmatched_models.items():
                UnmatchedModelNo._add_to_unmatched_models(model_values[0], config, len(model_values))

            message = _(f'Successfully imported {len(to_create)} new records, updated {len(to_update)} existing records, and found {len(unmatched_models)} unmatched models.')
            if errors:
                error_message = "\n".join([f"Row {index}: {error}" for index, _, error in errors])
                message += _("\n\nThe following errors occurred during import:\n%s") % error_message
                log_level = "warning"
            else:
                log_level = "info"

            # Log message
            _logger.log(logging.INFO if log_level == "info" else logging.WARNING, message)

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Import Completed'),
                    'message': message,
                    'type': 'warning' if errors else 'success',
                    'sticky': True if errors else False,
                }
            }
    
        except Exception as e:
            _logger.error(f"Error during file import: {str(e)}", exc_info=True)
            raise UserError(_(f"Error during file import: {str(e)}"))

    def _create_or_update_lot(self, record):
        StockLot = self.env['stock.lot']
        try:
            existing_lot = StockLot.search([
                ('name', '=', record.sn),
                ('product_id', '=', record.product_id.id),
                ('company_id', '=', self.env.company.id)
            ], limit=1)

            if existing_lot:
                record.write({'state': 'received'})
                _logger.info(f"Updated existing lot for product {record.product_id.name}, SN {record.sn}")
            else:
                StockLot.create({
                    'name': record.sn,
                    'product_id': record.product_id.id,
                    'company_id': self.env.company.id,
                })
                record.write({'state': 'received'})
                _logger.info(f"Created new lot for product {record.product_id.name}, SN {record.sn}")
        except Exception as e:
            _logger.error(f"Error handling lot for product {record.product_id.name}, SN {record.sn}: {str(e)}")
            record.write({'state': 'pending'})

    def _process_csv(self, file_content):
        try:
            csv_data = io.StringIO(file_content.decode('utf-8', errors='replace'))
            reader = csv.DictReader(csv_data, delimiter=';')
            return list(reader)
        except Exception as e:
            raise UserError(_(f'Error processing CSV file: {str(e)}'))

    def _process_excel(self, file_content):
        try:
            book = xlrd.open_workbook(file_contents=file_content)
            sheet = book.sheet_by_index(0)
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
        except Exception as e:
            raise UserError(_(f'Error processing Excel file: {str(e)}'))

    def _process_row_values(self, row, config):
        values = {}
        for mapping in config.column_mapping:
            source_column = mapping.source_column
            dest_field = mapping.destination_field_name
            source_value = row.get(source_column, '').strip()
            
            if dest_field and source_value:
                values[dest_field] = source_value
                _logger.info(f"Mapped '{source_column}' to '{dest_field}': {source_value}")
            elif dest_field:
                _logger.warning(f"Missing value for '{source_column}' (maps to '{dest_field}')")
        
        # If model_no is missing, try to use supplier_product_code or pn
        if 'model_no' not in values or not values['model_no']:
            values['model_no'] = values.get('supplier_product_code') or values.get('pn') or ''
            if values['model_no']:
                _logger.info(f"Using {values['model_no']} as model_no")
            else:
                _logger.warning("Unable to determine model_no")
    
        # Ensure supplier_product_code is set
        if 'supplier_product_code' not in values or not values['supplier_product_code']:
            values['supplier_product_code'] = values.get('model_no') or values.get('pn') or ''
            if values['supplier_product_code']:
                _logger.info(f"Using {values['supplier_product_code']} as supplier_product_code")
            else:
                _logger.warning("Unable to determine supplier_product_code")
    
        _logger.info(f"Processed values for row: {values}")
        return values

    def _add_to_unmatched_models(self, values, config):
        UnmatchedModelNo = self.env['unmatched.model.no']
        model_no = values.get('model_no')
        existing = UnmatchedModelNo.search([
            ('config_id', '=', config.id),
            ('model_no', '=', model_no)
        ], limit=1)

        if existing:
            existing.write({
                'count': existing.count + 1,
                'raw_data': f"{existing.raw_data}\n{str(values)}"
            })
        else:
            UnmatchedModelNo.create({
                'config_id': config.id,
                'supplier_id': config.supplier_id.id,
                'model_no': model_no,
                'pn': values.get('pn'),
                'product_code': values.get('supplier_product_code') or model_no,
                'raw_data': str(values),
                'count': 1
            })
        _logger.info(f"Added to unmatched models: {model_no}")

    
    @api.model
    def process_rows(self, data, config):
        IncomingProductInfo = self.env['incoming.product.info']
        UnmatchedModelNo = self.env['unmatched.model.no']
        
        to_create = []
        to_update = []
        unmatched_models = {}
        errors = []

        for index, row in enumerate(data, start=1):
            try:
                values = self._process_row_values(row, config)
                
                if 'model_no' not in values or 'sn' not in values:
                    continue

                product = IncomingProductInfo._search_product(values, config)
                if product:
                    values['product_id'] = product.id
                    values['supplier_id'] = config.supplier_id.id
                    if 'supplier_product_code' not in values:
                        values['supplier_product_code'] = values.get('model_no', '')

                    existing_info = IncomingProductInfo.search([
                        ('supplier_id', '=', config.supplier_id.id),
                        ('sn', '=', values['sn'])
                    ], limit=1)

                    if existing_info:
                        to_update.append((existing_info, values))
                    else:
                        to_create.append(values)
                else:
                    model_no = values.get('model_no')
                    if model_no not in unmatched_models:
                        unmatched_models[model_no] = {
                            'config_id': config.id,
                            'supplier_id': config.supplier_id.id,
                            'model_no': model_no,
                            'pn': values.get('pn'),
                            'product_code': values.get('supplier_product_code') or values.get('product_code') or model_no,
                            'supplier_product_code': values.get('supplier_product_code') or model_no,
                            'raw_data': str(values),
                            'count': 1
                        }
                    else:
                        unmatched_models[model_no]['count'] += 1

            except Exception as e:
                errors.append((index, row, str(e)))

        # Batch create new records
        if to_create:
            IncomingProductInfo.create(to_create)

        # Batch update existing records
        for record, values in to_update:
            record.write(values)

        # Batch create or update unmatched models
        for model_no, model_data in unmatched_models.items():
            existing_unmatched = UnmatchedModelNo.search([
                ('config_id', '=', config.id),
                ('model_no', '=', model_no)
            ], limit=1)
            
            if existing_unmatched:
                existing_unmatched.write({
                    'count': existing_unmatched.count + model_data['count'],
                    'raw_data': model_data['raw_data']
                })
            else:
                UnmatchedModelNo.create(model_data)

        if errors:
            error_message = collect_errors(errors)
            log_and_notify(self.env, error_message, "warning")

        return {
            'created': len(to_create),
            'updated': len(to_update),
            'unmatched': len(unmatched_models),
            'errors': errors
        }
