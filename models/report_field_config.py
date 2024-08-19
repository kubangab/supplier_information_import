from odoo import models, fields, api, _

class ReportFieldConfig(models.Model):
    _name = 'report.field.config'
    _description = 'Report Field Configuration'
    _order = 'sequence, id'

    config_id = fields.Many2one('import.format.config', string='Import Configuration', ondelete='cascade')
    field_id = fields.Many2one('ir.model.fields', string='Field', required=True, ondelete='cascade',
                               domain="[('id', 'in', parent.available_field_ids)]")
    name = fields.Char(string='Custom Label', required=True, translate=True)
    sequence = fields.Integer(string='Sequence', default=10)

    # Override the display_name to use the custom label
    def name_get(self):
        result = []
        for record in self:
            name = record.name or record.field_id.field_description or 'Unnamed'
            result.append((record.id, name))
        return result

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
        self.ensure_one()
        if not self.config_id:
            return []
        
        allowed_models = ['product.product', 'sale.order.line', 'stock.move.line', 'incoming.product.info']
        allowed_fields = ['default_code', 'name', 'product_uom_qty', 'lot_id']
        allowed_fields += self.config_id.column_mapping.mapped('destination_field_name')
    
        return [
            ('model', 'in', allowed_models),
            '|',
            ('name', 'in', allowed_fields),
            ('model', '=', 'incoming.product.info')
        ]