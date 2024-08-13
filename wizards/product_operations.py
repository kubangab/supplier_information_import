import base64
import csv
import io
import xlrd
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from ..models.utils import process_csv, process_excel, log_and_notify, collect_errors

_logger = logging.getLogger(__name__)

class ImportProductInfo(models.TransientModel):
    _name = 'import.product.info'
    _description = 'Import Product Information'

    file = fields.Binary(string='File', required=True)
    file_name = fields.Char(string='File Name')
    import_config_id = fields.Many2one('import.format.config', string='Import Configuration', required=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Done')
    ], default='draft', string='Status')

    def import_file(self):
        """
        Import and process the uploaded file.
        
        This method reads the uploaded file, processes its contents, and creates or updates
        incoming product info records based on the file contents and import configuration.
        
        :return: A client action to display a notification with the import results
        :raises UserError: If there's an error during the import process
        """
        self.ensure_one()
        if not self.file or not self.import_config_id:
            raise UserError(_('Please select a file and import configuration.'))
    
        file_content = base64.b64decode(self.file)
        config = self.import_config_id
    
        try:
            data_generator = process_csv(file_content) if config.file_type == 'csv' else process_excel(file_content)
    
            IncomingProductInfo = self.env['incoming.product.info']
            UnmatchedModelNo = self.env['unmatched.model.no']
            
            total_created = 0
            total_updated = 0
            total_unmatched = 0
            all_errors = []
    
            for chunk in data_generator:
                to_create = []
                to_update = []
                unmatched_models = []
                chunk_errors = []
    
                # Process chunk
                values_list = [self._process_row_values(row, config) for row in chunk]
                products = IncomingProductInfo._search_product(values_list, config)
    
                for index, (values, product) in enumerate(zip(values_list, products)):
                    try:
                        # Check for required fields
                        if not values.get('sn'):
                            raise ValidationError(_("Serial Number (SN) is required and cannot be empty."))
                        if not values.get('model_no'):
                            raise ValidationError(_("Model Number is required and cannot be empty."))
    
                        values['supplier_id'] = config.supplier_id.id
                        if product:
                            values['product_id'] = product.id
                        
                        existing_info = IncomingProductInfo.search([
                            ('supplier_id', '=', config.supplier_id.id),
                            ('sn', '=', values['sn'])
                        ], limit=1)
                        
                        if existing_info:
                            to_update.append((existing_info, values))
                        else:
                            to_create.append(values)
                        
                        if not product:
                            unmatched_models.append(values)
                    except ValidationError as e:
                        chunk_errors.append((index, values, str(e)))
                    except Exception as e:
                        chunk_errors.append((index, values, f"Unexpected error: {str(e)}"))
    
                # Batch create and update
                try:
                    if to_create:
                        IncomingProductInfo.create(to_create)
                        total_created += len(to_create)
                    if to_update:
                        for record, values in to_update:
                            record.write(values)
                        total_updated += len(to_update)
    
                    # Handle unmatched models
                    if unmatched_models:
                        for values in unmatched_models:
                            UnmatchedModelNo._add_to_unmatched_models(values, config)
                        total_unmatched += len(unmatched_models)
                except Exception as e:
                    chunk_errors.append((-1, {}, f"Error in batch processing: {str(e)}"))
    
                all_errors.extend(chunk_errors)
    
            self.env.cr.commit()  # Commit the changes to the database
    
            message = _('Successfully imported {} new records, updated {} existing records, and found {} unmatched models.').format(
                total_created, total_updated, total_unmatched)
            
            if all_errors:
                error_message = collect_errors(all_errors)
                message += _("\n\nThe following errors occurred during import:\n%s") % error_message
                log_level = "warning"
            else:
                log_level = "info"
    
            log_and_notify(self.env, message, error_type=log_level)
    
            self.write({'state': 'done'})
    
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Import Completed'),
                    'message': message,
                    'type': 'warning' if all_errors else 'success',
                    'sticky': bool(all_errors),
                    'next': {
                        'type': 'ir.actions.act_window',
                        'res_model': 'import.product.info',
                        'view_mode': 'form',
                        'res_id': self.id,
                        'views': [(False, 'form')],
                        'target': 'new',
                        'context': {'form_view_initial_mode': 'edit'}
                    }
                }
            }
    
        except Exception as e:
            log_and_notify(self.env, _("Error during file import: %s") % str(e), error_type="error")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Import Error'),
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }

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

    def _process_row_values(self, row, config):
        """
        Process a single row of data from the imported file.

        :param row: A dictionary representing a single row of data
        :param config: The import configuration record
        :return: A dictionary of processed values
        """
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
