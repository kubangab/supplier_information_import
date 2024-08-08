from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging
import re

_logger = logging.getLogger(__name__)

class IncomingProductInfo(models.Model):
    _name = 'incoming.product.info'
    _description = 'Incoming Product Information'

    name = fields.Char(string='Name', compute='_compute_name', store=True)
    supplier_id = fields.Many2one('res.partner', string='Supplier', required=True)
    supplier_product_code = fields.Char(string='Supplier Product Code', required=True)
    product_id = fields.Many2one('product.product', string='Product')
    product_tmpl_id = fields.Many2one('product.template', related='product_id.product_tmpl_id', store=True)
    sn = fields.Char(string='Serial Number', required=True)
    mac1 = fields.Char(string='MAC1')
    mac2 = fields.Char(string='MAC2')
    model_no = fields.Char(string='Model No.', required=True)
    imei = fields.Char(string='IMEI')
    app_eui = fields.Char(string='AppEUI')
    app_key = fields.Char(string='AppKey')
    app_key_mode = fields.Char(string='AppKeyMode')
    pn = fields.Char(string='PN')
    dev_eui = fields.Char(string='DEVEUI')
    root_password = fields.Char(string='Root Password')
    admin_password = fields.Char(string='Admin Password')
    wifi_password = fields.Char(string='WiFi Password')
    wifi_ssid = fields.Char(string='WiFi SSID')
    stock_picking_id = fields.Many2one('stock.picking', string='Related Stock Picking')
    state = fields.Selection([
        ('pending', 'Pending'),
        ('received', 'Received'),
    ], string='Status', default='pending')

    @api.depends('supplier_product_code', 'sn')
    def _compute_name(self):
        for record in self:
            record.name = f"{record.supplier_product_code or ''} - {record.sn or ''}"

    @api.model
    def _search_product(self, values, config):
        try:
            _logger.info(f"Starting _search_product with values: {values}")
            supplier = config.supplier_id
            main_supplier = supplier.parent_id or supplier
            supplier_domain = [
                '|', '|',
                ('id', '=', main_supplier.id),
                ('parent_id', '=', main_supplier.id),
                ('id', 'child_of', main_supplier.id)
            ]
            supplier_and_contacts = self.env['res.partner'].search(supplier_domain)
            _logger.info(f"Supplier and contacts: {supplier_and_contacts.mapped('name')}")

            model_no = values.get('model_no')
            supplier_product_code = values.get('supplier_product_code') or model_no

            # 1. Check Combination Rules
            rule_product = self._check_combination_rules(values, config, supplier_and_contacts)
            if rule_product:
                _logger.info(f"Product found via Combination Rules: {rule_product.name}")
                return rule_product

            # 2. Check Unmatched Model No
            unmatched_product = self._check_unmatched_model(model_no, config, supplier_and_contacts)
            if unmatched_product:
                _logger.info(f"Product found via Unmatched Model No: {unmatched_product.name}")
                return unmatched_product

            # 3. Check against supplier product code
            domain = [
                ('seller_ids.product_code', '=', supplier_product_code),
                ('seller_ids.partner_id', 'in', supplier_and_contacts.ids)
            ]
            
            _logger.info(f"Search domain: {domain}")
            products = self.env['product.product'].search(domain)
            _logger.info(f"Found {len(products)} products")

            if len(products) == 1:
                _logger.info(f"Single product found: {products.name}")
                return products
            elif len(products) > 1:
                _logger.warning(f"Multiple products found for supplier_product_code {supplier_product_code}. Adding to Unmatched Model No.")
                self._add_to_unmatched_models(values, config)
                return False

            _logger.info(f"No product found for model_no {model_no} and supplier_product_code {supplier_product_code}")
            self._add_to_unmatched_models(values, config)
            return False
        
        except Exception as e:
            _logger.error(f"Error in _search_product: {str(e)}", exc_info=True)
            return False

    def _check_combination_rules(self, values, config, supplier_and_contacts):
        for rule in config.combination_rule_ids:
            field1_value = values.get(rule.field_1.destination_field_name)
            field2_value = values.get(rule.field_2.destination_field_name)
            
            # Kontrollera om värdena matchar regeln
            if (field1_value == rule.value_1 or not rule.value_1) and (field2_value == rule.value_2 or not rule.value_2):
                if rule.product_id:
                    # Kontrollera om produkten har en leverantör som matchar
                    matching_supplier = rule.product_id.seller_ids.filtered(
                        lambda s: s.partner_id in supplier_and_contacts
                    )
                    if matching_supplier:
                        _logger.info(f"Matched product {rule.product_id.name} via Combination Rule: {rule.name}")
                        return rule.product_id
        
        _logger.info("No match found via Combination Rules")
        return False

    def _check_unmatched_model(self, model_no, config, supplier_and_contacts):
        unmatched = self.env['unmatched.model.no'].search([
            ('config_id', '=', config.id),
            ('model_no', '=', model_no),
            ('supplier_id', 'in', supplier_and_contacts.ids),
            ('product_id', '!=', False)
        ], limit=1)
        return unmatched.product_id if unmatched else False

    def _add_to_unmatched_models(self, values, config):
        UnmatchedModelNo = self.env['unmatched.model.no']
        model_no = values.get('model_no')
        existing = UnmatchedModelNo.search([
            ('config_id', '=', config.id),
            ('model_no', '=', model_no)
        ], limit=1)

        if existing:
            existing.write({
                'count': existing.count + 1,
                'raw_data': f"{existing.raw_data}\n{str(values)}"
            })
        else:
            UnmatchedModelNo.create({
                'config_id': config.id,
                'supplier_id': config.supplier_id.id,
                'model_no': model_no,
                'pn': values.get('pn'),
                'product_code': values.get('supplier_product_code') or model_no,
                'raw_data': str(values),
                'count': 1
            })

    def _check_model_no_against_product_code(self, model_no, config, supplier_ids):
        domain = [
            ('seller_ids.name', 'in', supplier_ids),
            '|', '|', '|',
            ('default_code', '=', model_no),
            ('default_code', 'ilike', model_no),
            ('seller_ids.product_code', '=', model_no),
            ('seller_ids.product_code', 'ilike', model_no)
        ]
        products = self.env['product.product'].search(domain)
        
        if products:
            if len(products) == 1:
                return products[0]
            else:
                _logger.warning(f"Multiple products found for model_no {model_no}")
        return None

    @api.model
    def create(self, vals_list):
        if not isinstance(vals_list, list):
            vals_list = [vals_list]
        
        for vals in vals_list:
            if 'sn' not in vals or not vals['sn']:
                raise ValidationError(_("Serial Number (SN) is required and cannot be empty."))
            if 'model_no' not in vals or not vals['model_no']:
                raise ValidationError(_("Model Number is required and cannot be empty."))
            _logger.info(f"Creating incoming product info with values: {vals}")
        
        return super(IncomingProductInfo, self).create(vals_list)
    
    def write(self, vals):
        if 'supplier_product_code' in vals and not vals['supplier_product_code']:
            vals['supplier_product_code'] = self.model_no or ''
        return super(IncomingProductInfo, self).write(vals)

    @api.model
    def _get_combined_code(self, values, config):
        if not config.combination_rule_ids:
            return values.get('supplier_product_code')
    
        for rule in config.combination_rule_ids:
            if not rule.field_1 or not rule.field_2 or not rule.combination_pattern:
                continue
    
            field1_value = values.get(rule.field_1.destination_field_name, '')
            field2_value = values.get(rule.field_2.destination_field_name, '')
    
            field1_value = str(field1_value).strip() if field1_value is not None else ''
            field2_value = str(field2_value).strip() if field2_value is not None else ''
            
            if not field1_value or not field2_value:
                continue
    
            if ((not rule.value_1 or field1_value.lower() == rule.value_1.lower()) and 
                (not rule.value_2 or field2_value.lower() == rule.value_2.lower())):
                combined = rule.combination_pattern.format(field1_value, field2_value)
    
                if rule.regex_pattern:
                    match = re.search(rule.regex_pattern, combined)
                    if match:
                        return match.group(1)
                else:
                    return combined
    
        return values.get('supplier_product_code')
    
class ProductTemplate(models.Model):
    _inherit = 'product.template'

    incoming_info_ids = fields.One2many('incoming.product.info', 'product_tmpl_id', string='Incoming Product Info')
    incoming_info_count = fields.Integer(compute='_compute_incoming_info_count', string='Incoming Info Count')

    @api.depends('incoming_info_ids')
    def _compute_incoming_info_count(self):
        for product in self:
            product.incoming_info_count = len(product.incoming_info_ids)

class SupplierInfo(models.Model):
    _inherit = 'product.supplierinfo'

    incoming_info_ids = fields.One2many('incoming.product.info', 'supplier_id', string='Incoming Product Info')
    incoming_info_count = fields.Integer(compute='_compute_incoming_info_count', string='Incoming Info Count')

    @api.depends('incoming_info_ids')
    def _compute_incoming_info_count(self):
        for supplier_info in self:
            supplier_info.incoming_info_count = len(supplier_info.incoming_info_ids.filtered(lambda r: r.supplier_product_code == supplier_info.product_code))