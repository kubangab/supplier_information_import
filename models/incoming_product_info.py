# models/incoming_product_info.py
from odoo import models, fields, api

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    imported_info_count = fields.Integer(compute='_compute_imported_info_count', string='Imported Info Count')

    @api.depends()
    def _compute_imported_info_count(self):
        for product in self:
            product.imported_info_count = self.env['incoming.product.info'].search_count([('product_id', '=', product.id)])

class IncomingProductInfo(models.Model):
    _name = 'incoming.product.info'
    _description = 'Incoming Product Information'

    name = fields.Char(string='Name', compute='_compute_name', store=True)
    supplier_id = fields.Many2one('res.partner', string='Supplier', required=True)
    product_id = fields.Many2one('product.product', string='Product')
    sn = fields.Char(string='Serial Number')
    mac1 = fields.Char(string='MAC1')
    mac2 = fields.Char(string='MAC2')
    model_no = fields.Char(string='Model No.')
    imei = fields.Char(string='IMEI')
    app_key = fields.Char(string='AppKey')
    app_key_mode = fields.Char(string='AppKeyMode')
    pn = fields.Char(string='PN')
    dev_eui = fields.Char(string='DEVEUI')
    root_password = fields.Char(string='Root Password')
    admin_password = fields.Char(string='Admin Password')
    wifi_password = fields.Char(string='WiFi Password')
    wifi_ssid = fields.Char(string='WiFi SSID')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('received', 'Received'),
    ], string='Status', default='pending')

    @api.depends('sn', 'model_no')
    def _compute_name(self):
        for record in self:
            record.name = f"{record.model_no or ''} - {record.sn or ''}"