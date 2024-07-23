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
    supplier_id = fields.Many2one('res.partner', string='Supplier', required=True)

    def import_file(self):
        if not self.file:
            raise exceptions.UserError('Please select a file to import.')

        file_content = base64.b64decode(self.file)
        
        if self.file_name.lower().endswith('.csv'):
            self.process_csv(file_content)
        elif self.file_name.lower().endswith(('.xls', '.xlsx')):
            self.process_excel(file_content)
        else:
            raise exceptions.UserError('Unsupported file format. Please use CSV or Excel files.')

        return {'type': 'ir.actions.act_window_close'}

    def process_csv(self, file_content):
        csv_data = io.StringIO(file_content.decode('utf-8', errors='replace'))
        reader = csv.DictReader(csv_data, delimiter='\t')
        self.process_rows(reader)

    def process_excel(self, file_content):
        workbook = xlrd.open_workbook(file_contents=file_content)
        sheet = workbook.sheet_by_index(0)
        header = [sheet.cell_value(0, col) for col in range(sheet.ncols)]
        rows = [dict(zip(header, [sheet.cell_value(row, col) for col in range(sheet.ncols)]))
                for row in range(1, sheet.nrows)]
        self.process_rows(rows)

    def process_rows(self, rows):
        IncomingProductInfo = self.env['incoming.product.info']
        SupplierInfo = self.env['product.supplierinfo']

        for row in rows:
            supplier_product_code = row.get('Supplier Product Code')
            serial_number = row.get('SN')

            # Sök efter befintlig IncomingProductInfo
            existing_info = IncomingProductInfo.search([
                ('supplier_id', '=', self.supplier_id.id),
                ('sn', '=', serial_number)
            ], limit=1)

            supplier_info = SupplierInfo.search([
                ('name', '=', self.supplier_id.id),
                ('product_code', '=', supplier_product_code)
            ], limit=1)

            if not supplier_info:
                # Skapa en ny produkt och leverantörsinformation om den inte finns
                product_tmpl = self.env['product.template'].create({
                    'name': row.get('Model No.'),
                    'default_code': row.get('Model No.'),
                })
                supplier_info = SupplierInfo.create({
                    'name': self.supplier_id.id,
                    'product_tmpl_id': product_tmpl.id,
                    'product_code': supplier_product_code,
                })
                product = product_tmpl.product_variant_id
            else:
                product = supplier_info.product_tmpl_id.product_variant_id

            values = {
                'supplier_id': self.supplier_id.id,
                'product_id': product.id,
                'supplier_product_code': supplier_product_code,
                'sn': serial_number,
                'mac1': row.get('MAC1'),
                'mac2': row.get('MAC2'),
                'model_no': row.get('Model No.'),
                'imei': row.get('IMEI'),
                'app_key': row.get('AppKey'),
                'app_key_mode': row.get('AppKeyMode'),
                'pn': row.get('PN'),
                'dev_eui': row.get('DEVEUI'),
                'root_password': row.get('ROOT_PASSWORD'),
                'admin_password': row.get('ADMIN_PASSWORD'),
                'wifi_password': row.get('WIFI_PASSWORD'),
                'wifi_ssid': row.get('WIFISSID'),
            }

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