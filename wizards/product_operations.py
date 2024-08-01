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

            # Create unmatched model records
            UnmatchedModelNo = self.env['unmatched.model.no']
            for model_no in unmatched_models:
                UnmatchedModelNo.create({
                    'config_id': config.id,
                    'model_no': model_no,
                })

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
        SupplierInfo = self.env['product.supplierinfo']
        Product = self.env['product.product']
        ProductTemplate = self.env['product.template']
        UnmatchedModelNo = self.env['unmatched.model.no']
    
        _logger.info(f"Starting to process {len(data)} rows")
        _logger.info(f"Config supplier_id: {config.supplier_id.id}")
        _logger.info(f"Column mapping: {[(m.source_column, m.destination_field_name) for m in config.column_mapping]}")
        
        supplier = self.env['res.partner'].browse(config.supplier_id.id)
        _logger.info(f"Supplier {supplier.name} (ID: {supplier.id}) has supplier_rank: {supplier.supplier_rank}")
        
        if supplier.supplier_rank == 0:
            supplier.write({'supplier_rank': 1})
            _logger.info(f"Updated supplier_rank for {supplier.name} to 1")
    
        unmatched_models = set()  # Use a set to store unique model numbers
        failed_rows = []
    
        for index, row in enumerate(data, start=1):
            try:
                _logger.info(f"Processing row {index}: {row}")
                
                values = {}
                missing_required_fields = []
    
                for mapping in config.column_mapping:
                    source_value = row.get(mapping.source_column, '').strip()
                    _logger.debug(f"Mapping {mapping.source_column} to {mapping.destination_field_name}: '{source_value}'")
                    if mapping.destination_field_name:
                        if mapping.is_required and not source_value:
                            missing_required_fields.append(mapping.custom_label or mapping.destination_field_name)
                        if source_value:
                            values[mapping.destination_field_name] = source_value
    
                if missing_required_fields:
                    _logger.warning(f"Row {index}: Missing required fields: {', '.join(missing_required_fields)}")
                    continue
    
                if 'model_no' not in values:
                    _logger.warning(f"Row {index}: Missing Model No.")
                    continue
    
                if 'sn' not in values:
                    _logger.warning(f"Row {index}: Missing Serial Number")
                    continue
    
                _logger.info(f"Row {index}: Processed values: {values}")
    
                # Apply combination rules
                combined_code = IncomingProductInfo._get_combined_code(values, config)
                if combined_code:
                    values['supplier_product_code'] = combined_code
                    _logger.info(f"Row {index}: Applied combination rule. New supplier_product_code: {combined_code}")
                else:
                    _logger.info(f"Row {index}: No combination rule applied. Using original supplier_product_code.")
    
                # Ensure we have a supplier_product_code
                if 'supplier_product_code' not in values:
                    values['supplier_product_code'] = values.get('model_no', '')
                    _logger.info(f"Row {index}: No supplier_product_code found. Using model_no as fallback.")
    
                # Search for existing supplier info
                supplier_info = SupplierInfo.search([
                    ('partner_id', '=', config.supplier_id.id),
                    ('product_code', '=', values['supplier_product_code'])
                ], limit=1)
    
                if supplier_info:
                    _logger.info(f"Row {index}: Found existing SupplierInfo for product_code={values['supplier_product_code']}")
                    product = supplier_info.product_id
                else:
                    _logger.info(f"Row {index}: No matching product found for supplier_product_code={values['supplier_product_code']}")
                    product = Product.search([('default_code', '=', values['supplier_product_code'])], limit=1)
                    if product:
                        _logger.info(f"Row {index}: Found product by default_code={values['supplier_product_code']}")
                    else:
                        _logger.info(f"Row {index}: No product found. Adding to unmatched models.")
                        unmatched_models.add(values['model_no'])
                        continue  # Skip to next row without creating IncomingProductInfo
                
                values['supplier_id'] = config.supplier_id.id
                values['product_id'] = product.id
    
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
    
        # Create unmatched model records
        for model_no in unmatched_models:
            UnmatchedModelNo.create({
                'config_id': config.id,
                'model_no': model_no,
            })
    
        self.env.cr.commit()
        _logger.info("Finished processing all rows")
        
        if failed_rows:
            _logger.warning(f"Failed to process {len(failed_rows)} rows")
    
        return list(unmatched_models)  # Convert set back to list before returning