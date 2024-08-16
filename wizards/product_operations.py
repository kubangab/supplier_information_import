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
        if not self.file:
            raise UserError(_('Please select a file to import.'))
        
        config = self.import_config_id
        if not config:
            raise UserError(_('Please select an import configuration.'))
    
        file_content = base64.b64decode(self.file)
        
        try:
            if config.file_type == 'csv':
                data = process_csv(file_content)
            elif config.file_type == 'excel':
                data = process_excel(file_content)
            else:
                raise UserError(_('Unsupported file format. Please use CSV or Excel files.'))
    
            if not data:
                raise UserError(_('No data found in the file.'))
    
            IncomingProductInfo = self.env['incoming.product.info']
            total_processed = 0
            total_created = 0
            total_updated = 0
            errors = []
    
            for chunk in data:
                for index, row in enumerate(chunk, start=total_processed + 1):
                    try:
                        values = self._process_row_values(row, config)
                        
                        product = IncomingProductInfo._search_product(values, config)
                        if product:
                            values['product_id'] = product.id
                            values['supplier_id'] = config.supplier_id.id
                            record, is_new = IncomingProductInfo.find_or_create(values)
                            if is_new:
                                total_created += 1
                            else:
                                total_updated += 1
                        else:
                            IncomingProductInfo._add_to_unmatched_models(values, config)
                    except Exception as e:
                        errors.append((index, row, str(e)))
                    
                    total_processed += 1
    
            message = _(f'Processed {total_processed} rows, created {total_created} new records, updated {total_updated} existing records.')
            if errors:
                error_message = collect_errors(errors)
                message += _("\n\nErrors occurred during import. Check the logs for details.")
                log_level = "warning"
            else:
                log_level = "info"
    
            log_and_notify(self.env, message, error_type=log_level)
    
            # Update the state to 'done'
            self.write({'state': 'done'})
            
            # Send a sticky notification
            self.env['bus.bus']._sendone(self.env.user.partner_id, 'simple_notification', {
                'title': _('Import Completed'),
                'message': message,
                'type': 'warning' if errors else 'success',
                'sticky': True,
            })
            
            # Return an action to keep the wizard open
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'import.product.info',
                'res_id': self.id,
                'view_mode': 'form',
                'view_type': 'form',
                'target': 'new',
                'context': {'form_view_initial_mode': 'edit'},
            }
    
        except Exception as e:
            error_message = _("Error during file import: {}").format(str(e))
            _logger.error(error_message, exc_info=True)
            log_and_notify(self.env, error_message, error_type="error")
            raise UserError(error_message)
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
    
        # Ensure required fields are present
        required_fields = ['sn', 'model_no']
        for field in required_fields:
            if field not in values:
                raise ValueError(f"Required field '{field}' is missing")
    
        # Handle supplier_product_code
        if 'supplier_product_code' not in values or not values['supplier_product_code']:
            values['supplier_product_code'] = values.get('model_no', '')
            _logger.info(f"Using {values['supplier_product_code']} as supplier_product_code")
    
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
