from odoo import models, fields, api, _

class IncomingProductInfo(models.Model):
    _name = 'incoming.product.info'
    _description = 'Incoming Product Information'

    name = fields.Char(string='Name', compute='_compute_name', store=True)
    supplier_id = fields.Many2one('res.partner', string='Supplier', required=True)
    supplier_product_code = fields.Char(string='Supplier Product Code', required=True)
    product_id = fields.Many2one('product.product', string='Product')
    product_tmpl_id = fields.Many2one('product.template', related='product_id.product_tmpl_id', store=True)
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
        supplier = config.supplier_id
        main_supplier = supplier.parent_id or supplier
        supplier_and_contacts = self.env['res.partner'].search([
            '|', '|',
            ('id', '=', main_supplier.id),
            ('parent_id', '=', main_supplier.id),
            ('id', 'child_of', main_supplier.id)
        ])

        if config.combination_rule_ids:
            matching_product = self._check_combination_rules(values, config, supplier_and_contacts)
            if matching_product:
                return matching_product

        model_no = values.get('model_no')
        if model_no:
            product = self._check_model_no_against_product_code(model_no, config, supplier_and_contacts)
            if product:
                return product
            elif product is None:
                return False

        supplier_product_code = values.get('supplier_product_code')
        if supplier_product_code:
            products = self.env['product.product'].search([
                ('seller_ids.partner_id', 'in', supplier_and_contacts.ids),
                '|',
                ('seller_ids.product_code', '=', supplier_product_code),
                ('seller_ids.product_code', 'ilike', supplier_product_code)
            ])
            if len(products) == 1:
                return products[0]
            elif len(products) > 1:
                return False

        if model_no:
            unmatched_model = self._check_unmatched_model(model_no, config, supplier_and_contacts)
            if unmatched_model and unmatched_model.product_id:
                return unmatched_model.product_id

        return False

    @api.model
    def _check_combination_rules(self, values, config, supplier_and_contacts):
        for rule in config.combination_rule_ids:
            field1_value = values.get(rule.field_1.destination_field_name)
            field2_value = values.get(rule.field_2.destination_field_name)
            
            if field1_value == rule.value_1 and field2_value == rule.value_2:
                if rule.product_id and rule.product_id.seller_ids.filtered(lambda s: s.partner_id in supplier_and_contacts):
                    return rule.product_id
        return False

    @api.model
    def _check_unmatched_model(self, model_no, config, supplier_and_contacts):
        return self.env['unmatched.model.no'].search([
            ('config_id', '=', config.id),
            ('model_no', '=', model_no),
            ('supplier_id', 'in', supplier_and_contacts.ids),
            ('product_id', '!=', False)
        ], limit=1)
    
    @api.model
    def _check_model_no_against_product_code(self, model_no, config, supplier_and_contacts):
        domain = [
            ('seller_ids.partner_id', 'in', supplier_and_contacts.ids),
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
                return None
        return None

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