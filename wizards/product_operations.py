import logging
from odoo import models, fields, api, exceptions, _
import base64
import csv
import io
import xlrd

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
            raise exceptions.UserError(_('Unsupported file format.'))

        self.process_rows(rows, config)

        return {'type': 'ir.actions.act_window_close'}

    def process_csv(self, file_content):
        csv_data = io.StringIO(file_content.decode('utf-8', errors='replace'))
        reader = csv.DictReader(csv_data)
        return list(reader)

    def process_excel(self, file_content):
        workbook = xlrd.open_workbook(file_contents=file_content)
        sheet = workbook.sheet_by_index(0)
        headers = [sheet.cell_value(0, col) for col in range(sheet.ncols)]
        return [
            dict(zip(headers, [sheet.cell_value(row, col) for col in range(sheet.ncols)]))
            for row in range(1, sheet.nrows)
        ]

    def process_rows(self, rows, config):
        IncomingProductInfo = self.env['incoming.product.info']
        SupplierInfo = self.env['product.supplierinfo']
        Product = self.env['product.product']

        _logger.info(f"Config supplier_id: {config.supplier_id.id}")
        
        supplier = self.env['res.partner'].browse(config.supplier_id.id)
        _logger.info(f"Supplier {supplier.name} (ID: {supplier.id}) has supplier_rank: {supplier.supplier_rank}")
        
        if supplier.supplier_rank == 0:
            supplier.write({'supplier_rank': 1})
            _logger.info(f"Updated supplier_rank for {supplier.name} to 1")

        for row in rows:
            values = {}
            missing_required_fields = []

            for mapping in config.column_mapping:
                source_value = row.get(mapping.source_column)
                if mapping.destination_field:
                    if mapping.is_required and not source_value:
                        missing_required_fields.append(mapping.custom_label or mapping.destination_field.field_description)
                    if source_value:
                        values[mapping.destination_field.name] = source_value

            if missing_required_fields:
                raise exceptions.UserError(_('Missing required fields: %s for row: %s') % (", ".join(missing_required_fields), row))

            if 'sn' not in values or 'model_no' not in values:
                raise exceptions.UserError(_('Missing required fields: Serial Number or Model No. for row: %s') % row)

            existing_info = IncomingProductInfo.search([
                ('supplier_id', '=', config.supplier_id.id),
                ('model_no', '=', values['model_no']),
                ('sn', '=', values['sn'])
            ], limit=1)

            _logger.info(f"Searching for Product with default_code={values['model_no']}")
            product = Product.search([('default_code', '=', values['model_no'])], limit=1)

            if not product:
                _logger.info(f"Creating new product with default_code={values['model_no']}")
                product = Product.create({
                    'name': values.get('model_no', 'New Product'),
                    'default_code': values['model_no'],
                    'type': 'product',
                })

            _logger.info(f"Searching for SupplierInfo with partner_id={config.supplier_id.id} and product_tmpl_id={product.product_tmpl_id.id}")
            supplier_info = SupplierInfo.search([
                ('partner_id', '=', config.supplier_id.id),
                ('product_tmpl_id', '=', product.product_tmpl_id.id)
            ], limit=1)

            if not supplier_info:
                _logger.info(f"Creating new SupplierInfo for product {product.id} and supplier {config.supplier_id.id}")
                supplier_info = SupplierInfo.create({
                    'partner_id': config.supplier_id.id,
                    'product_tmpl_id': product.product_tmpl_id.id,
                    'product_code': values['model_no'],
                })

            values['supplier_id'] = config.supplier_id.id
            values['product_id'] = product.id
            values['supplier_product_code'] = supplier_info.product_code

            if existing_info:
                _logger.info(f"Updating existing IncomingProductInfo {existing_info.id}")
                existing_info.write(values)
            else:
                _logger.info(f"Creating new IncomingProductInfo")
                IncomingProductInfo.create(values)

        self.env.cr.commit()
        
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