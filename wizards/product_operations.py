import base64
import csv
import io
import xlrd
import logging
from odoo import models, fields, api, exceptions, _

_logger = logging.getLogger(__name__)

class ImportProductInfo(models.TransientModel):
    _name = 'import.product.info'
    _description = 'Import Product Information'

    file = fields.Binary(string='File', required=True)
    file_name = fields.Char(string='File Name')
    import_config_id = fields.Many2one('import.format.config', string='Import Configuration', required=True)

    def import_file(self):
        if not self.file:
            raise exceptions.UserError(_('Please select a file to import.'))

        config = self.import_config_id
        if not config:
            raise exceptions.UserError(_('Please select an import configuration.'))

        file_content = base64.b64decode(self.file)
        
        if config.file_type == 'csv':
            rows = self.process_csv(file_content)
        elif config.file_type == 'excel':
            rows = self.process_excel(file_content)
        else:
            raise exceptions.UserError(_('Unsupported file format. Please use CSV or Excel files.'))

        self.process_rows(rows, config)

        return {'type': 'ir.actions.act_window_close'}

    def process_csv(self, file_content):
        try:
            csv_data = io.StringIO(file_content.decode('utf-8', errors='replace'))
            reader = csv.DictReader(csv_data, delimiter=';')  # Using semicolon as delimiter
            return [{k.strip(): v.strip() for k, v in row.items()} for row in reader]
        except Exception as e:
            _logger.error(f"Error processing CSV file: {str(e)}")
            raise exceptions.UserError(_('Error processing CSV file: %s') % str(e))

    def process_excel(self, file_content):
        try:
            workbook = xlrd.open_workbook(file_contents=file_content)
            sheet = workbook.sheet_by_index(0)
            
            headers = [str(cell.value).strip() for cell in sheet.row(0)]
            
            data = []
            for row in range(1, sheet.nrows):
                row_data = {}
                for col, header in enumerate(headers):
                    cell_value = sheet.cell_value(row, col)
                    if isinstance(cell_value, float) and cell_value.is_integer():
                        cell_value = int(cell_value)
                    row_data[header] = str(cell_value).strip()
                data.append(row_data)
            
            return data
        except Exception as e:
            _logger.error(f"Error processing Excel file: {str(e)}")
            raise exceptions.UserError(_('Error processing Excel file: %s') % str(e))

    def process_rows(self, rows, config):
        IncomingProductInfo = self.env['incoming.product.info']
        SupplierInfo = self.env['product.supplierinfo']
        Product = self.env['product.product']
        ProductTemplate = self.env['product.template']
    
        _logger.info(f"Starting to process {len(rows)} rows")
        _logger.info(f"Config supplier_id: {config.supplier_id.id}")
        _logger.info(f"Column mapping: {[(m.source_column, m.destination_field_name) for m in config.column_mapping]}")
        
        supplier = self.env['res.partner'].browse(config.supplier_id.id)
        _logger.info(f"Supplier {supplier.name} (ID: {supplier.id}) has supplier_rank: {supplier.supplier_rank}")
        
        if supplier.supplier_rank == 0:
            supplier.write({'supplier_rank': 1})
            _logger.info(f"Updated supplier_rank for {supplier.name} to 1")
    
        for index, row in enumerate(rows, start=1):
            _logger.info(f"Processing row {index}: {row}")
            
            # Skip empty rows
            if all(value.strip() == '' for value in row.values()):
                _logger.info(f"Skipping empty row {index}")
                continue
    
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
    
            # First, search for existing supplier info
            supplier_info = SupplierInfo.search([
                ('partner_id', '=', config.supplier_id.id),
                ('product_code', '=', values['model_no'])
            ], limit=1)
    
            if supplier_info:
                _logger.info(f"Row {index}: Found existing SupplierInfo for product_code={values['model_no']}")
                product_tmpl = supplier_info.product_tmpl_id
                product = Product.search([('product_tmpl_id', '=', product_tmpl.id)], limit=1)
            else:
                _logger.info(f"Row {index}: Searching for Product with default_code={values['model_no']}")
                product = Product.search([('default_code', '=', values['model_no'])], limit=1)
    
            if not product:
                _logger.info(f"Row {index}: Creating new product with default_code={values['model_no']}")
                product_tmpl = ProductTemplate.create({
                    'name': values.get('model_no', 'New Product'),
                    'default_code': values['model_no'],
                    'type': 'product',
                })
                product = Product.create({
                    'product_tmpl_id': product_tmpl.id,
                })
    
            if not supplier_info:
                _logger.info(f"Row {index}: Creating new SupplierInfo for product {product.id} and supplier {config.supplier_id.id}")
                supplier_info = SupplierInfo.create({
                    'partner_id': config.supplier_id.id,
                    'product_tmpl_id': product.product_tmpl_id.id,
                    'product_code': values['model_no'],
                })
    
            values['supplier_id'] = config.supplier_id.id
            values['product_id'] = product.id
            values['supplier_product_code'] = supplier_info.product_code
    
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
    
        self.env.cr.commit()
        _logger.info("Finished processing all rows")
        
class ReceiveProducts(models.TransientModel):
    _name = 'receive.products.wizard'
    _description = 'Receive Products Wizard'

    incoming_product_ids = fields.Many2many('incoming.product.info', string='Incoming Products')
    lot_creation_method = fields.Selection([
        ('auto', 'Automatic'),
        ('manual', 'Manual')
    ], string='Lot Creation Method', default='auto', required=True)
    manual_lot_number = fields.Char(string='Manual Lot Number')

    @api.onchange('lot_creation_method')
    def _onchange_lot_creation_method(self):
        if self.lot_creation_method == 'auto':
            self.manual_lot_number = False

    def action_receive_products(self):
        StockMove = self.env['stock.move']
        StockProductionLot = self.env['stock.production.lot']
        
        for incoming_product in self.incoming_product_ids:
            move = StockMove.create({
                'name': f"Receipt of {incoming_product.name}",
                'product_id': incoming_product.product_id.id,
                'product_uom_qty': 1,
                'product_uom': incoming_product.product_id.uom_id.id,
                'location_id': self.env.ref('stock.stock_location_suppliers').id,
                'location_dest_id': self.env.ref('stock.stock_location_stock').id,
            })
            
            lot_name = self._get_lot_name(incoming_product)
            lot = StockProductionLot.create({
                'name': lot_name,
                'product_id': incoming_product.product_id.id,
                'company_id': self.env.company.id,
            })
            
            self._update_lot_info(lot, incoming_product)
            
            move._action_confirm()
            move._action_assign()
            move_line = move.move_line_ids[0]
            move_line.lot_id = lot.id
            move_line.qty_done = 1
            move._action_done()
            
            incoming_product.state = 'received'

        return {'type': 'ir.actions.act_window_close'}

    def _get_lot_name(self, incoming_product):
        if self.lot_creation_method == 'manual':
            return self.manual_lot_number
        return incoming_product.sn or incoming_product.model_no or f"LOT-{fields.Datetime.now().strftime('%Y%m%d%H%M%S')}"

    def _update_lot_info(self, lot, incoming_product):
        lot.write({
            'x_mac1': incoming_product.mac1,
            'x_mac2': incoming_product.mac2,
            'x_imei': incoming_product.imei,
            'x_app_key': incoming_product.app_key,
            'x_dev_eui': incoming_product.dev_eui,
        })