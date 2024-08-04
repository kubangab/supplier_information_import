from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)

class IncomingProductInfo(models.Model):
    _name = 'incoming.product.info'
    _description = 'Incoming Product Information'

    name = fields.Char(string='Name', compute='_compute_name', store=True)
    supplier_id = fields.Many2one('res.partner', string='Supplier', required=True)
    product_id = fields.Many2one('product.product', string='Product')
    product_tmpl_id = fields.Many2one('product.template', related='product_id.product_tmpl_id', store=True)
    supplier_product_code = fields.Char(string='Supplier Product Code', required=True)
    sn = fields.Char(string='Serial Number')
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
        _logger.info(f"Searching for product with values: {values}")
    
        try:
            # 1. Check Combination Rules (highest priority)
            if config.combination_rule_ids:
                matching_rule = self._check_combination_rules(values, config)
                if matching_rule:
                    return matching_rule
    
            # 2. Check Unmatched Model Numbers rules
            model_no = values.get('model_no')
            if model_no:
                unmatched_model = self._check_unmatched_model(model_no, config)
                if unmatched_model:
                    return unmatched_model.product_id
    
            # 3. Check Model No. against Product Code
            if model_no:
                product = self._check_model_no_against_product_code(model_no, config)
                if product:
                    return product
    
        except Exception as e:
            _logger.error(f"Error in _search_product: {str(e)}")
            # Do not re-raise the exception, just return False
    
        _logger.warning(f"No matching product found for values: {values}")
        return False
    
    def _check_combination_rules(self, values, config):
        for rule in config.combination_rule_ids:
            field1_value = values.get(rule.field_1.destination_field_name)
            field2_value = values.get(rule.field_2.destination_field_name)
            
            if field1_value == rule.value_1 and field2_value == rule.value_2:
                if rule.product_id and rule.product_id.seller_ids.filtered(lambda s: s.partner_id == config.supplier_id):
                    _logger.info(f"Found product via combination rule: {rule.product_id.name} (ID: {rule.product_id.id})")
                    return rule.product_id
        return False
    
    def _check_unmatched_model(self, model_no, config):
        try:
            unmatched_model = self.env['unmatched.model.no'].search([
                ('config_id', '=', config.id),
                ('model_no', '=', model_no),
                ('product_id', '!=', False)
            ], limit=1)
            
            if unmatched_model:
                _logger.info(f"Found product via Unmatched Model Number: {unmatched_model.product_id.name} (ID: {unmatched_model.product_id.id})")
            return unmatched_model
        except Exception as e:
            _logger.error(f"Error checking unmatched model: {str(e)}")
            return False
    
    def _check_model_no_against_product_code(self, model_no, config):
        product = self.env['product.product'].search([
            ('seller_ids.product_code', '=', model_no),
            ('seller_ids.partner_id', '=', config.supplier_id.id)
        ], limit=1)
        
        if product:
            _logger.info(f"Found product via Model No. matching Product Code: {product.name} (ID: {product.id})")
        return product

    @api.model
    def _get_combined_code(self, values, config):
        _logger.info(f"Starting _get_combined_code with values: {values}")
        if not config.combination_rule_ids:
            _logger.info("No combination rules found, returning supplier_product_code")
            return values.get('supplier_product_code')
    
        for rule in config.combination_rule_ids:
            _logger.info(f"Checking rule: {rule.name}")
            if not rule.field_1 or not rule.field_2 or not rule.combination_pattern:
                _logger.info("Incomplete rule, skipping")
                continue
    
            field1_value = values.get(rule.field_1.destination_field_name, '')
            field2_value = values.get(rule.field_2.destination_field_name, '')
            _logger.info(f"Field1 ({rule.field_1.destination_field_name}): {field1_value}")
            _logger.info(f"Field2 ({rule.field_2.destination_field_name}): {field2_value}")
    
            # Convert to string and strip whitespace
            field1_value = str(field1_value).strip() if field1_value is not None else ''
            field2_value = str(field2_value).strip() if field2_value is not None else ''
            
            # Skip rows where either field is empty
            if not field1_value or not field2_value:
                _logger.info("Missing value for field1 or field2, skipping")
                continue
    
            # Check if the rule matches (ignoring case)
            if ((not rule.value_1 or field1_value.lower() == rule.value_1.lower()) and 
                (not rule.value_2 or field2_value.lower() == rule.value_2.lower())):
                _logger.info("Rule matched")
                combined = rule.combination_pattern.format(field1_value, field2_value)
                _logger.info(f"Combined code: {combined}")
    
                if rule.regex_pattern:
                    match = re.search(rule.regex_pattern, combined)
                    if match:
                        result = match.group(1)
                        _logger.info(f"Regex matched, result: {result}")
                        return result
                else:
                    _logger.info(f"No regex, returning combined: {combined}")
                    return combined
            else:
                _logger.info(f"Rule did not match. Rule values: {rule.value_1}, {rule.value_2}")
    
        _logger.info("No matching rule found, returning supplier_product_code")
        return values.get('supplier_product_code')
    
    @api.model
    def create(self, vals):
        if 'supplier_product_code' not in vals or not vals['supplier_product_code']:
            vals['supplier_product_code'] = vals.get('model_no', '')
        return super(IncomingProductInfo, self).create(vals)
    
    def write(self, vals):
        if 'supplier_product_code' in vals and not vals['supplier_product_code']:
            vals['supplier_product_code'] = self.model_no or ''
        return super(IncomingProductInfo, self).write(vals)
    
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