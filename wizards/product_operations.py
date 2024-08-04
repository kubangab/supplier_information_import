import base64
import csv
import io
import xlrd
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class ImportProductInfo(models.TransientModel):
    _name = 'import.product.info'
    _description = 'Import Product Information'

    file = fields.Binary(string='File', required=True)
    file_name = fields.Char(string='File Name')
    import_config_id = fields.Many2one('import.format.config', string='Import Configuration', required=True)

    def import_file(self):
        if not self.file:
            raise UserError(_('Please select a file to import.'))
    
        config = self.import_config_id
        if not config:
            raise UserError(_('Please select an import configuration.'))
    
        file_content = base64.b64decode(self.file)
        
        try:
            if config.file_type == 'csv':
                data = self.process_csv(file_content)
            elif config.file_type == 'excel':
                data = self.process_excel(file_content)
            else:
                raise UserError(_('Unsupported file format. Please use CSV or Excel files.'))
    
            if not data:
                raise UserError(_('No data found in the file.'))
    
            _logger.info(f"Processed {len(data)} rows from the file")
    
            unmatched_models = self.process_rows(data, config)
    
            return {'type': 'ir.actions.act_window_close'}
        except Exception as e:
            _logger.error(f"Error during file import: {str(e)}")
            raise UserError(_(f"Error during file import: {str(e)}"))

    def process_csv(self, file_content):
        try:
            csv_data = io.StringIO(file_content.decode('utf-8', errors='replace'))
            reader = csv.DictReader(csv_data, delimiter=';')  # Using semicolon as delimiter
            data = list(reader)
            _logger.info(f"Processed {len(data)} rows from CSV file")
            return data
        except Exception as e:
            _logger.error(f"Error processing CSV file: {str(e)}")
            raise UserError(_(f'Error processing CSV file: {str(e)}'))

    def process_excel(self, file_content):
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
            
            _logger.info(f"Processed {len(data)} rows from Excel file")
            return data
        except Exception as e:
            _logger.error(f"Error processing Excel file: {str(e)}")
            raise UserError(_(f'Error processing Excel file: {str(e)}'))

    def _process_row_values(self, row, config):
        values = {}
        for mapping in config.column_mapping:
            source_value = row.get(mapping.source_column, '').strip()
            if mapping.destination_field_name and source_value:
                values[mapping.destination_field_name] = source_value
        
        combined_code = self.env['incoming.product.info']._get_combined_code(values, config)
        if combined_code:
            values['supplier_product_code'] = combined_code
        elif 'model_no' in values:
            # Use model_no as supplier_product_code if no combined code is generated
            values['supplier_product_code'] = values['model_no']
        
        return values

    def process_rows(self, data, config):
        IncomingProductInfo = self.env['incoming.product.info']
        UnmatchedModelNo = self.env['unmatched.model.no']
        
        _logger.info(f"Starting to process {len(data)} rows")
        _logger.info(f"Config supplier_id: {config.supplier_id.id}")
        
        unmatched_models = {}
        failed_rows = []
    
        for index, row in enumerate(data, start=1):
            try:
                with self.env.cr.savepoint():
                    _logger.info(f"Processing row {index}: {row}")
            
                    values = self._process_row_values(row, config)
                    _logger.info(f"Row {index}: Processed values: {values}")
            
                    if 'model_no' not in values or 'sn' not in values:
                        _logger.warning(f"Row {index}: Missing Model No. or Serial Number. Skipping.")
                        continue
            
                    product = IncomingProductInfo._search_product(values, config)
                    if product:
                        values['product_id'] = product.id
                        values['supplier_id'] = config.supplier_id.id
                        if 'supplier_product_code' not in values:
                            values['supplier_product_code'] = values.get('model_no', '')  # Fallback to model_no if available
                    
                        existing_info = IncomingProductInfo.search([
                            ('supplier_id', '=', config.supplier_id.id),
                            ('model_no', '=', values['model_no']),
                            ('sn', '=', values['sn'])
                        ], limit=1)
                    
                        if existing_info:
                            _logger.info(f"Row {index}: Updating existing IncomingProductInfo {existing_info.id}")
                            existing_info.write(values)
                        else:
                            _logger.info(f"Row {index}: Creating new IncomingProductInfo")
                            IncomingProductInfo.create(values)
                    else:
                        _logger.warning(f"Row {index}: No matching product found for values: {values}. Adding to unmatched models.")
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
                _logger.error(f"Error processing row {index}: {str(e)}")
                failed_rows.append((index, row, str(e)))
                continue
    
        # Create or update UnmatchedModelNo records
        for model_no, model_data in unmatched_models.items():
            existing_unmatched = UnmatchedModelNo.search([
                ('config_id', '=', config.id),
                ('model_no', '=', model_no)
            ], limit=1)
            if existing_unmatched:
                existing_unmatched.write({
                    'count': existing_unmatched.count + model_data['count'],
                    'raw_data': model_data['raw_data']  # Update with latest data
                })
            else:
                UnmatchedModelNo.create(model_data)
    
        _logger.info("Finished processing all rows")
        
        if failed_rows:
            _logger.warning(f"Failed to process {len(failed_rows)} rows")
    
        return list(unmatched_models.keys())