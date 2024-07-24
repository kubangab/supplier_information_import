import base64
import csv
import io
import xlrd
from odoo import models, fields, api, exceptions

class ImportProductInfo(models.TransientModel):
    _name = 'import.product.info'
    _description = 'Import Product Information'

    file = fields.Binary(string='File', required=True)
    file_name = fields.Char(string='File Name')
    import_config_id = fields.Many2one('import.format.config', string='Import Configuration', required=True)

    def import_file(self):
        if not self.file:
            raise exceptions.UserError('Please select a file to import.')

        config = self.import_config_id
        if not config:
            raise exceptions.UserError('Please select an import configuration.')

        file_content = base64.b64decode(self.file)
        
        if config.file_type == 'csv':
            rows = self.process_csv(file_content)
        elif config.file_type == 'excel':
            rows = self.process_excel(file_content)
        else:
            raise exceptions.UserError('Unsupported file format.')

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

        for row in rows:
            values = {}
            missing_required_fields = []

            for mapping in config.column_mapping:
                source_value = row.get(mapping.source_column)
                if mapping.destination_field:
                    if mapping.is_required and not source_value:
                        missing_required_fields.append(mapping.destination_field.field_description)
                    if source_value:
                        values[mapping.destination_field.name] = source_value

            if missing_required_fields:
                raise exceptions.UserError(f'Missing required fields: {", ".join(missing_required_fields)} for row: {row}')

            if 'supplier_product_code' not in values or 'sn' not in values:
                raise exceptions.UserError(f'Missing required fields: Supplier Product Code or Serial Number for row: {row}')

            existing_info = IncomingProductInfo.search([
                ('supplier_id', '=', config.supplier_id.id),
                ('supplier_product_code', '=', values['supplier_product_code']),
                ('sn', '=', values['sn'])
            ], limit=1)

            supplier_info = SupplierInfo.search([
                ('name', '=', config.supplier_id.id),
                ('product_code', '=', values['supplier_product_code'])
            ], limit=1)

            if not supplier_info:
                product_tmpl = self.env['product.template'].create({
                    'name': values.get('model_no', 'New Product'),
                    'default_code': values.get('model_no', 'New Product'),
                })
                supplier_info = SupplierInfo.create({
                    'name': config.supplier_id.id,
                    'product_tmpl_id': product_tmpl.id,
                    'product_code': values['supplier_product_code'],
                })
                product = product_tmpl.product_variant_id
            else:
                product = supplier_info.product_tmpl_id.product_variant_id

            values['supplier_id'] = config.supplier_id.id
            values['product_id'] = product.id

            if existing_info:
                existing_info.write(values)
            else:
                IncomingProductInfo.create(values)

        self.env.cr.commit()
        
class ReceiveProducts(models.TransientModel):
    _name = 'receive.products.wizard'
    _description = 'Receive Products Wizard'

    incoming_product_ids = fields.Many2many('incoming.product.info', string='Incoming Products')

    def action_receive_products(self):
        StockMove = self.env['stock.move']
        for incoming_product in self.incoming_product_ids:
            move = StockMove.create({
                'name': f"Receipt of {incoming_product.name}",
                'product_id': incoming_product.product_id.id,
                'product_uom_qty': 1,
                'product_uom': incoming_product.product_id.uom_id.id,
                'location_id': self.env.ref('stock.stock_location_suppliers').id,
                'location_dest_id': self.env.ref('stock.stock_location_stock').id,
            })
            move._action_confirm()
            move._action_assign()
            move_line = move.move_line_ids[0]
            
            lot = self.env['stock.production.lot'].create({
                'name': incoming_product.sn,
                'product_id': incoming_product.product_id.id,
                'company_id': self.env.company.id,
            })
            move_line.lot_id = lot.id
            
            lot.write({
                'x_mac1': incoming_product.mac1,
                'x_mac2': incoming_product.mac2,
                'x_imei': incoming_product.imei,
                'x_app_key': incoming_product.app_key,
                'x_dev_eui': incoming_product.dev_eui,
            })
            
            move_line.qty_done = 1
            move._action_done()
            
            incoming_product.state = 'received'

        return {'type': 'ir.actions.act_window_close'}