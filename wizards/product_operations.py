import base64
import csv
import io
import xlrd
from odoo import models, fields, api, _
from odoo.exceptions import UserError

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
                data = self.process_csv(file_content)
            elif config.file_type == 'excel':
                data = self.process_excel(file_content)
            else:
                raise UserError(_('Unsupported file format. Please use CSV or Excel files.'))
    
            if not data:
                raise UserError(_('No data found in the file.'))
    
            self.process_rows(data, config)
    
            return {'type': 'ir.actions.act_window_close'}
        except Exception as e:
            raise UserError(_(f"Error during file import: {str(e)}"))

    def process_csv(self, file_content):
        try:
            csv_data = io.StringIO(file_content.decode('utf-8', errors='replace'))
            reader = csv.DictReader(csv_data, delimiter=';')
            return list(reader)
        except Exception as e:
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
            
            return data
        except Exception as e:
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
            values['supplier_product_code'] = values['model_no']
        
        return values

    @api.model
    def _search_product(self, values, config):
        try:
            if config.combination_rule_ids:
                matching_rule = self._check_combination_rules(values, config)
                if matching_rule:
                    return matching_rule
    
            model_no = values.get('model_no')
            if model_no:
                unmatched_model = self._check_unmatched_model(model_no, config)
                if unmatched_model:
                    return unmatched_model.product_id
    
            if model_no:
                product = self._check_model_no_against_product_code(model_no, config)
                if product:
                    return product
    
        except Exception as e:
            pass
    
        return False
    
    def process_rows(self, data, config):
        IncomingProductInfo = self.env['incoming.product.info']
        UnmatchedModelNo = self.env['unmatched.model.no']
        
        unmatched_models = {}
        failed_rows = []
    
        for index, row in enumerate(data, start=1):
            try:
                with self.env.cr.savepoint():
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
                            existing_info.write(values)
                        else:
                            IncomingProductInfo.create(values)
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
                failed_rows.append((index, row, str(e)))
                continue
    
        for model_no, model_data in unmatched_models.items():
            try:
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
    
            except Exception as e:
                pass
    
        return list(unmatched_models.keys())