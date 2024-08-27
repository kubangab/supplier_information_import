from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import logging
from ..models.utils import process_csv, process_excel, log_and_notify, collect_errors, preprocess_field_value

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
    new_combination_rules = fields.Text(string='New Combination Rules', readonly=True)

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
                'added {unmatched} to unmatched models, '
                '{rule_without_product} rows with rule but no product.'
            ).format(
                total=result['total'],
                created=result['created'],
                updated=result['updated'],
                unmatched=result['unmatched'],
                rule_without_product=result['rule_without_product']
            )
    
            if result.get('new_combination_rules'):
                new_rules = list(set(result['new_combination_rules']))  # Remove duplicates
                self.new_combination_rules = "\n".join(new_rules)
                message += _('\n\nNew Combination Rules created:\n{}').format(self.new_combination_rules)
    
            if result['errors']:
                error_message = collect_errors(result['errors'])
                message += _('\n\nErrors occurred during import. Check the logs for details.')
                log_level = "warning"
            else:
                log_level = "info"
    
            log_and_notify(message, error_type=log_level)
    
            # Update the state to 'done' and set the result message
            self.write({
                'state': 'done',
                'result_message': message
            })
            
            return self._reopen_view()
    
        except Exception as e:
            error_message = _("Error during file import: {}").format(str(e))
            _logger.error(error_message, exc_info=True)
            log_and_notify(error_message, error_type="error")
            
            raise UserError(error_message)

    def process_rows(self, data, config):
        IncomingProductInfo = self.env['incoming.product.info']
        UnmatchedModelNo = self.env['unmatched.model.no']
        
        total_processed = 0
        total_created = 0
        total_updated = 0
        total_unmatched = 0
        total_rule_without_product = 0
        errors = []
        new_combination_rules = set()
        unmatched_models = {}

        for chunk in data:
            create_vals = []
            update_vals = []

            for index, row in enumerate(chunk, start=total_processed + 1):
                try:
                    values = self._process_row_values(row, config)
                    
                    product, new_rule = IncomingProductInfo._search_product(values, config)
                    if product == 'rule_without_product':
                        total_rule_without_product += 1
                        _logger.info(f"Rule found but no product assigned for row {index}")
                    elif product:
                        values['product_id'] = product.id
                        values['supplier_id'] = config.supplier_id.id
                        existing_info = IncomingProductInfo.search([
                            ('supplier_id', '=', config.supplier_id.id),
                            ('sn', '=', values['sn'])
                        ], limit=1)

                        if existing_info:
                            update_vals.append((existing_info.id, values))
                        else:
                            create_vals.append(values)
                    else:
                        total_unmatched += 1
                        model_no = values.get('model_no', '')
                        if model_no in unmatched_models:
                            unmatched_models[model_no]['count'] += 1
                        else:
                            unmatched_models[model_no] = {'values': values, 'count': 1}
                        _logger.info(f"Added to unmatched models: {model_no}")

                    # Check if a new combination rule was created
                    if new_rule:
                        new_combination_rules.add(f"{new_rule.value_1} - {new_rule.value_2}")

                except Exception as e:
                    errors.append((index, row, str(e)))
                    _logger.error(f"Error processing row {index}: {str(e)}", exc_info=True)
            
            # Batch create
            if create_vals:
                created_records = IncomingProductInfo.create(create_vals)
                total_created += len(created_records)
                _logger.info(f"Created {len(created_records)} new records in this batch")
            
            # Batch update
            if update_vals:
                for record_id, values in update_vals:
                    IncomingProductInfo.browse(record_id).write(values)
                total_updated += len(update_vals)
                _logger.info(f"Updated {len(update_vals)} existing records in this batch")

            total_processed += len(chunk)

        # Process unmatched models
        for model_no, data in unmatched_models.items():
            UnmatchedModelNo._add_to_unmatched_models(data['values'], config)

        # Get the final count of unmatched models
        unmatched_count = UnmatchedModelNo.search_count([('config_id', '=', config.id)])
        total_unmatched_rows = sum(UnmatchedModelNo.search([('config_id', '=', config.id)]).mapped('count'))

        _logger.info(f"Final count - Processed {total_processed} rows, created {total_created} new records, "
                     f"updated {total_updated} existing records, {unmatched_count} unique unmatched models "
                     f"(total {total_unmatched_rows} unmatched rows), {total_rule_without_product} rows with rule but no product")

        return {
            'total': total_processed,
            'created': total_created,
            'updated': total_updated,
            'unmatched': unmatched_count,
            'unmatched_rows': total_unmatched_rows,
            'rule_without_product': total_rule_without_product,
            'errors': errors,
            'new_combination_rules': list(new_combination_rules)
        }

    def _process_row_values(self, row, config):
        values = {}
        for mapping in config.column_mapping:
            source_column = mapping.source_column
            dest_field = mapping.destination_field_name
            source_value = row.get(source_column, '').strip()
            
            if dest_field and source_value:
                # Preprocess the value if it's the second field (assuming it's always the second field)
                if mapping == config.column_mapping[1]:
                    source_value = preprocess_field_value(source_value)
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

    def _reopen_view(self):
        return {
            'name': _('File Analysis Result'),
            'type': 'ir.actions.act_window',
            'res_model': 'import.product.info',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': {'form_view_initial_mode': 'edit'},
        }

    @api.model
    def _get_file_content(self):
        return base64.b64decode(self.file)