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

    def process_rows(self, data, config):
        IncomingProductInfo = self.env['incoming.product.info']
        UnmatchedModelNo = self.env['unmatched.model.no']
        
        _logger.info(f"Starting to process {len(data)} rows")
        _logger.info(f"Config supplier_id: {config.supplier_id.id}")
        _logger.info(f"Column mapping: {[(m.source_column, m.destination_field_name) for m in config.column_mapping]}")
    
        supplier = self.env['res.partner'].browse(config.supplier_id.id)
        _logger.info(f"Supplier {supplier.name} (ID: {supplier.id}) has supplier_rank: {supplier.supplier_rank}")
    
        if supplier.supplier_rank == 0:
            supplier.write({'supplier_rank': 1})
            _logger.info(f"Updated supplier_rank for {supplier.name} to 1")
    
        unmatched_models = set()
        failed_rows = []
    
        for index, row in enumerate(data, start=1):
            try:
                _logger.info(f"Processing row {index}: {row}")
    
                values = {}
                for mapping in config.column_mapping:
                    source_value = row.get(mapping.source_column, '').strip()
                    _logger.debug(f"Mapping {mapping.source_column} to {mapping.destination_field_name}: '{source_value}'")
                    if mapping.destination_field_name:
                        if mapping.is_required and not source_value:
                            _logger.warning(f"Row {index}: Missing required field: {mapping.custom_label or mapping.destination_field_name}")
                            continue
                        if source_value:
                            values[mapping.destination_field_name] = source_value
    
                _logger.info(f"Row {index}: Processed values: {values}")
    
                if 'model_no' not in values:
                    _logger.warning(f"Row {index}: Missing Model No.")
                    continue
    
                if 'sn' not in values:
                    _logger.warning(f"Row {index}: Missing Serial Number")
                    continue
    
                combined_code = IncomingProductInfo._get_combined_code(values, config)
                _logger.info(f"Row {index}: Combined code result: {combined_code}")
    
                if combined_code:
                    values['supplier_product_code'] = combined_code
                    _logger.info(f"Row {index}: Applied combination rule. New supplier_product_code: {combined_code}")
    
                # Search for existing product with the new method
                product = IncomingProductInfo._search_product(values, config)
                
                if not product:
                    _logger.warning(f"Row {index}: No matching product found for values: {values}. Adding to unmatched models.")
                    unmatched_key = tuple(values.get(field.destination_field_name) for field in config.column_mapping if field.is_required)
                    if unmatched_key not in unmatched_models:
                        unmatched_models.add(unmatched_key)
                        UnmatchedModelNo.create({
                            'config_id': config.id,
                            **{field.destination_field_name: values.get(field.destination_field_name) 
                                for field in config.column_mapping if field.is_required}
                        })
                    continue
                
                # If a product was found, continue with the rest of the process
                values['product_id'] = product.id
                values['supplier_id'] = config.supplier_id.id
    
                # Create or update IncomingProductInfo
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
    
            except Exception as e:
                _logger.error(f"Error processing row {index}: {str(e)}")
                failed_rows.append((index, row, str(e)))
                continue
    
        _logger.info("Finished processing all rows")
        
        if failed_rows:
            _logger.warning(f"Failed to process {len(failed_rows)} rows")
    
        return list(unmatched_models)