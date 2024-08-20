from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError
from unittest.mock import patch
import base64

class TestProductInfoReport(TransactionCase):

    def setUp(self):
        super(TestProductInfoReport, self).setUp()
        self.SaleOrder = self.env['sale.order']
        self.StockPicking = self.env['stock.picking']
        self.Partner = self.env['res.partner']
        self.Product = self.env['product.product']
        self.IncomingProductInfo = self.env['incoming.product.info']

        # Create test data
        self.customer = self.Partner.create({
            'name': 'Test Customer',
            'email': 'customer@test.com',
        })
        self.product = self.Product.create({
            'name': 'Test Product',
            'type': 'product',
        })
        self.incoming_info = self.IncomingProductInfo.create({
            'product_id': self.product.id,
            'sn': 'TEST001',
            'model_no': 'MODEL001',
            'supplier_product_code': 'SUPP001',
        })

    def test_generate_excel_report(self):
        # Create a sale order
        sale_order = self.SaleOrder.create({
            'partner_id': self.customer.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 1,
            })],
        })
        sale_order.action_confirm()

        # Test excel report generation
        excel_data = sale_order.generate_excel_report()
        self.assertTrue(excel_data, "Excel data should be generated")
        self.assertTrue(isinstance(excel_data, bytes), "Excel data should be bytes")

    @patch('odoo.addons.mail.models.mail_template.MailTemplate.send_mail')
    def test_action_generate_and_send_excel(self, mock_send_mail):
        # Create a sale order
        sale_order = self.SaleOrder.create({
            'partner_id': self.customer.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 1,
            })],
        })
        sale_order.action_confirm()

        # Test the action to generate and send excel
        result = sale_order.action_generate_and_send_excel()
        
        self.assertTrue(mock_send_mail.called, "Send mail should be called")
        self.assertEqual(result['type'], 'ir.actions.act_window', "Should return window action")
        self.assertEqual(result['res_model'], 'mail.compose.message', "Should open mail compose window")

    def test_get_report_lines(self):
        # Create a stock picking (delivery order)
        picking = self.StockPicking.create({
            'partner_id': self.customer.id,
            'picking_type_id': self.env.ref('stock.picking_type_out').id,
            'location_id': self.env.ref('stock.stock_location_stock').id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
        })
        self.env['stock.move'].create({
            'name': 'Test Move',
            'product_id': self.product.id,
            'product_uom_qty': 1,
            'product_uom': self.product.uom_id.id,
            'picking_id': picking.id,
            'location_id': self.env.ref('stock.stock_location_stock').id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
        })
        
        # Confirm and assign the picking
        picking.action_confirm()
        picking.action_assign()

        # Test get_report_lines
        lines = picking._get_report_lines()
        self.assertTrue(lines, "Report lines should be generated")
        self.assertEqual(len(lines), 1, "Should have one report line")

    def test_get_field_value(self):
        sale_order = self.SaleOrder.create({
            'partner_id': self.customer.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 1,
            })],
        })
        sale_order.action_confirm()

        # Mock a field configuration
        field_config = self.env['ir.model.fields'].search([('model', '=', 'product.product'), ('name', '=', 'name')], limit=1)

        # Test _get_field_value method
        value = sale_order._get_field_value(sale_order.order_line[0], None, field_config, 'en_US')
        self.assertEqual(value, self.product.name, "Should return the correct product name")

    @patch('odoo.addons.mail.models.mail_template.MailTemplate.send_mail')
    def test_send_excel_report_email(self, mock_send_mail):
        sale_order = self.SaleOrder.create({
            'partner_id': self.customer.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 1,
            })],
        })
        sale_order.action_confirm()

        # Create a mock attachment
        attachment = self.env['ir.attachment'].create({
            'name': 'Test Attachment',
            'datas': base64.b64encode(b'Test content'),
            'res_model': 'sale.order',
            'res_id': sale_order.id,
        })

        # Test send_excel_report_email method
        template = self.env.ref('supplier_information_import.email_template_product_info_sale_order')
        sale_order.send_excel_report_email(template, attachment)

        mock_send_mail.assert_called_once()
        call_args = mock_send_mail.call_args[1]
        self.assertEqual(call_args['res_id'], sale_order.id, "Should send email for the correct sale order")
        self.assertTrue(call_args['attachment_ids'], "Should include attachment in the email")