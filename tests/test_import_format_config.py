from odoo.tests.common import TransactionCase

class TestImportFormatConfig(TransactionCase):

    def setUp(self):
        super(TestImportFormatConfig, self).setUp()
        self.ImportFormatConfig = self.env['import.format.config']
        self.supplier = self.env['res.partner'].create({
            'name': 'Test Supplier',
            'supplier_rank': 1,
        })

    def test_create_import_format_config(self):
        config = self.ImportFormatConfig.create({
            'name': 'Test Config',
            'file_type': 'csv',
            'supplier_id': self.supplier.id,
        })
        self.assertTrue(config, "Import Format Config should be created")
        self.assertEqual(config.name, 'Test Config', "Name should be set correctly")
        self.assertEqual(config.file_type, 'csv', "File type should be set correctly")
        self.assertEqual(config.supplier_id, self.supplier, "Supplier should be set correctly")

    def test_compute_supplier_name(self):
        config = self.ImportFormatConfig.create({
            'name': 'Test Config',
            'file_type': 'csv',
            'supplier_id': self.supplier.id,
        })
        self.assertEqual(config.supplier_name, 'Test Supplier', "Supplier name should be computed correctly")