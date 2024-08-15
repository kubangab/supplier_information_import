from odoo import models, fields, api, _

class ReportFieldConfig(models.Model):
    _name = 'report.field.config'
    _description = 'Report Field Configuration'
    _order = 'sequence, id'

    config_id = fields.Many2one('import.format.config', string='Import Configuration', ondelete='cascade')
    field_id = fields.Many2one('ir.model.fields', string='Field', required=True, ondelete='cascade',
                               domain="[('id', 'in', parent.available_field_ids)]")
    name = fields.Char(string='Display Name', required=True, translate=True)
    sequence = fields.Integer(string='Sequence', default=10)

    @api.depends('field_id')
    def _compute_field_name(self):
        for record in self:
            record.field_name = record.field_id.field_description if record.field_id else ''

    @api.onchange('field_id')
    def _onchange_field_id(self):
        if self.field_id:
            self.name = self.field_id.field_description

    @api.model
    def _get_field_domain(self):
        config_id = self._context.get('config_id')
        if not config_id:
            return []
        
        config = self.env['import.format.config'].browse(config_id)
        allowed_models = ['product.product', 'sale.order.line', 'stock.move.line', 'incoming.product.info']
        allowed_fields = ['default_code', 'name', 'product_uom_qty', 'lot_id']
        allowed_fields += config.column_mapping.mapped('destination_field_name')

        return [
            ('model', 'in', allowed_models),
            '|',
            ('name', 'in', allowed_fields),
            ('model', '=', 'incoming.product.info')
        ]