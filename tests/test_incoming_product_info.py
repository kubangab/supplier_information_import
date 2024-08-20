from odoo.tests.common import TransactionCase

class TestIncomingProductInfo(TransactionCase):

    def setUp(self):
        super(TestIncomingProductInfo, self).setUp()
        self.IncomingProductInfo = self.env['incoming.product.info']
        self.supplier = self.env['res.partner'].create({
            'name': 'Test Supplier',
            'supplier_rank': 1,
        })
        self.product = self.env['product.product'].create({
            'name': 'Test Product',
            'type': 'product',
        })

    def test_create_incoming_product_info(self):
        info = self.IncomingProductInfo.create({
            'supplier_id': self.supplier.id,
            'product_id': self.product.id,
            'sn': 'TEST001',
            'model_no': 'MODEL001',
            'supplier_product_code': 'SUPP001',
        })
        self.assertTrue(info, "Incoming Product Info should be created")
        self.assertEqual(info.supplier_id, self.supplier, "Supplier should be set correctly")
        self.assertEqual(info.product_id, self.product, "Product should be set correctly")
        self.assertEqual(info.sn, 'TEST001', "Serial number should be set correctly")

    def test_compute_name(self):
        info = self.IncomingProductInfo.create({
            'supplier_id': self.supplier.id,
            'product_id': self.product.id,
            'sn': 'TEST001',
            'model_no': 'MODEL001',
            'supplier_product_code': 'SUPP001',
        })
        expected_name = 'SUPP001 - TEST001'
        self.assertEqual(info.name, expected_name, "Name should be computed correctly")