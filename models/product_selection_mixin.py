from odoo import models, fields, api


class ProductSelectionMixin(models.AbstractModel):
    _name = 'product.selection.mixin'
    _description = 'Product Selection Mixin'

    supplier_id = fields.Many2one('res.partner', string='Supplier')
    product_id = fields.Many2one('product.product', string='Product')

    @api.onchange('supplier_id')
    def _onchange_supplier_id(self):
        return {'domain': {'product_id': self._get_product_domain()}}

    def _get_product_domain(self):
        self.ensure_one()
        if self.supplier_id:
            main_supplier = self.supplier_id.parent_id or self.supplier_id
            return [('seller_ids.partner_id', 'in', [main_supplier.id] + main_supplier.child_ids.ids)]
        return []

    def action_link_product(self):
        self.ensure_one()
        if self.product_id:
            IncomingProductInfo = self.env['incoming.product.info']
            for _ in range(getattr(self, 'count', 1)):
                incoming_product = IncomingProductInfo.create({
                    'supplier_id': self.supplier_id.id,
                    'product_id': self.product_id.id,
                    'model_no': getattr(self, 'model_no', False),
                    'sn': getattr(self, 'pn', False) or getattr(self, 'sn', False),
                    'supplier_product_code': getattr(self, 'supplier_product_code', False) or getattr(self, 'product_code', False),
                })
            
            supplierinfo = self.env['product.supplierinfo'].search([
                ('partner_id', '=', self.supplier_id.id),
                ('product_id', '=', self.product_id.id)
            ], limit=1)
            if not supplierinfo:
                self.env['product.supplierinfo'].create({
                    'partner_id': self.supplier_id.id,
                    'product_id': self.product_id.id,
                    'product_code': getattr(self, 'supplier_product_code', False) or getattr(self, 'product_code', False),
                })
            else:
                supplierinfo.write({
                    'product_code': getattr(self, 'supplier_product_code', False) or getattr(self, 'product_code', False),
                })

            if hasattr(self, 'unlink'):
                self.unlink()

            return {
                'type': 'ir.actions.act_window',
                'name': 'Linked Product Info',
                'res_model': 'incoming.product.info',
                'res_id': incoming_product.id,
                'view_mode': 'form',
                'view_type': 'form',
                'target': 'current',
            }
        return {'type': 'ir.actions.do_nothing'}