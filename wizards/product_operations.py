# wizards/product_operations.py
import base64
import csv
import io
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
        file_content = file_content.decode('utf-8')
        
        reader = csv.DictReader(io.StringIO(file_content), delimiter='\t')
        self.process_rows(reader)

        return {'type': 'ir.actions.act_window_close'}

    def process_rows(self, rows):
        IncomingProductInfo = self.env['incoming.product.info']
        Product = self.env['product.product']

        for row in rows:
            product = Product.search([('default_code', '=', row.get('Model No.'))], limit=1)
            if not product:
                product = Product.create({
                    'name': row.get('Model No.'),
                    'default_code': row.get('Model No.'),
                })

            values = {
                'supplier_id': self.supplier_id.id,
                'product_id': product.id,
                'sn': row.get('SN'),
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

            incoming_product_info = IncomingProductInfo.create(values)

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