from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import logging
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
    result_message = fields.Text(string='Import Result', readonly=True)

    def import_file(self):
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

            result = self.process_rows(data, config)

            message = _(
                'Processed {total} rows, created {created} new records, '
                'updated {updated} existing records, '
                'added {unmatched} to unmatched models.'
            ).format(
                total=result['total'],
                created=result['created'],
                updated=result['updated'],
                unmatched=result['unmatched']
            )

            if result['errors']:
                error_message = collect_errors(result['errors'])
                message += _("\n\nErrors occurred during import. Check the logs for details.")
                log_level = "warning"
            else:
                log_level = "info"

            log_and_notify(message, error_type=log_level)

            # Update the state to 'done' and set the result message
            self.write({
                'state': 'done',
                'result_message': message
            })
            
            # Return an action to keep the wizard open and display the result
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
            log_and_notify(error_message, error_type="error")
            
            # Send a sticky notification for the error
            self.env['bus.bus']._sendone(self.env.user.partner_id, 'simple_notification', {
                'title': _('Import Error'),
                'message': error_message,
                'type': 'danger',
                'sticky': True,
            })
            
            raise UserError(error_message)

    @api.model
    def process_rows(self, data, config):
        IncomingProductInfo = self.env['incoming.product.info']
        
        to_create = []
        to_update = []
        unmatched_models = {}
        errors = []
        total_processed = 0
    
        for chunk in data:
            for index, row in enumerate(chunk, start=total_processed + 1):
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
                            # If the record exists, keep its current state
                            values['state'] = existing_info.state
                            to_update.append((existing_info, values))
                            _logger.info(f"Updating existing record for SN: {values['sn']}, State: {values['state']}")
                        else:
                            # For new records, set state to 'received' since we're importing existing data
                            values['state'] = 'received'
                            to_create.append(values)
                            _logger.info(f"Preparing to create new record for SN: {values['sn']}, State: received")
                    else:
                        IncomingProductInfo._add_to_unmatched_models(values, config)
                        unmatched_models[values.get('model_no')] = unmatched_models.get(values.get('model_no'), 0) + 1
                        _logger.info(f"Added to unmatched models: {values.get('model_no')}")
    
                except Exception as e:
                    errors.append((index, row, str(e)))
                    _logger.error(f"Error processing row {index}: {str(e)}")
                
                total_processed += 1
    
        _logger.info(f"Preparing to create {len(to_create)} new records and update {len(to_update)} existing records")
    
        # Batch create new records
        created_records = IncomingProductInfo.create(to_create)
        _logger.info(f"Actually created {len(created_records)} new records")
    
        # Batch update existing records
        for record, values in to_update:
            record.write(values)
    
        if errors:
            error_message = collect_errors(errors)
            log_and_notify(self.env, error_message, "warning")
    
        return {
            'total': total_processed,
            'created': len(created_records),
            'updated': len(to_update),
            'unmatched': sum(unmatched_models.values()),
            'errors': errors
        }

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