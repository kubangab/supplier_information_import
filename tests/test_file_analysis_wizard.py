from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError

class TestFileAnalysisWizard(TransactionCase):

    def setUp(self):
        super(TestFileAnalysisWizard, self).setUp()
        self.FileAnalysisWizard = self.env['file.analysis.wizard']
        self.ImportFormatConfig = self.env['import.format.config']
        self.ImportColumnMapping = self.env['import.column.mapping']
        
        self.supplier = self.env['res.partner'].create({
            'name': 'Test Supplier',
            'supplier_rank': 1,
        })
        
        self.config = self.ImportFormatConfig.create({
            'name': 'Test Config',
            'file_type': 'csv',
            'supplier_id': self.supplier.id,
        })
        
        self.column_mapping = self.ImportColumnMapping.create({
            'config_id': self.config.id,
            'source_column': 'Test Column',
            'destination_field_name': 'test_field',
            'custom_label': 'Test Field',
        })

    def test_compute_available_fields(self):
        wizard = self.FileAnalysisWizard.create({
            'import_config_id': self.config.id,
        })
        self.assertEqual(len(wizard.available_field_ids), 1, "There should be one available field")
        self.assertEqual(wizard.available_field_ids[0], self.column_mapping, "The available field should match the created column mapping")

    def test_analyze_file_without_file(self):
        wizard = self.FileAnalysisWizard.create({
            'import_config_id': self.config.id,
        })
        with self.assertRaises(UserError):
            wizard.action_analyze_file()

    # Add more tests as needed for other functionalities of the wizard