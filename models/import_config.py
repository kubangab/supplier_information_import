from odoo import models, fields, api

class ImportFormatConfig(models.Model):
    _name = 'import.format.config'
    _description = 'Import Format Configuration'

    name = fields.Char(string='Configuration Name', required=True)
    file_type = fields.Selection([
        ('csv', 'CSV'),
        ('excel', 'Excel')
    ], string='File Type', required=True)
    column_mapping = fields.One2many('import.column.mapping', 'config_id', string='Column Mappings')
    supplier_id = fields.Many2one('res.partner', string='Supplier', domain=[('supplier_rank', '>', 0)])

class ImportColumnMapping(models.Model):
    _name = 'import.column.mapping'
    _description = 'Import Column Mapping'

    config_id = fields.Many2one('import.format.config', string='Import Configuration')
    source_column = fields.Char(string='Source Column Name', required=True)
    destination_field = fields.Many2one('ir.model.fields', string='Destination Field', 
                                        domain=[('model', '=', 'incoming.product.info')], required=True)