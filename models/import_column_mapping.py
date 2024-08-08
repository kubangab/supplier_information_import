from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class ImportColumnMapping(models.Model):
    _name = 'import.column.mapping'
    _description = 'Import Column Mapping'

    config_id = fields.Many2one('import.format.config', string='Import Configuration')
    source_column = fields.Char(string='Source Column Name', required=True)
    destination_field_name = fields.Selection(
        selection='_get_destination_field_selection',
        string='Destination Field Name',
        required=True
    )
    custom_field_name = fields.Char(string='Custom Field Name')
    custom_label = fields.Char(string='Custom Label', translate=True, required=True)
    is_custom_field = fields.Boolean(string='Is Custom Field', compute='_compute_is_custom_field', store=True)
    is_required = fields.Boolean(string='Is Required', compute='_compute_is_required', store=True)
    is_readonly = fields.Boolean(string='Is Readonly', compute='_compute_is_readonly')

    @api.depends('destination_field_name')
    def _compute_is_custom_field(self):
        for record in self:
            record.is_custom_field = record.destination_field_name == 'custom'

    @api.depends('destination_field_name')
    def _compute_is_required(self):
        for record in self:
            record.is_required = record.destination_field_name in ['sn', 'model_no']

    @api.depends('destination_field_name')
    def _compute_is_readonly(self):
        for record in self:
            record.is_readonly = record.destination_field_name in ['sn', 'model_no']

    @api.model
    def _get_destination_field_selection(self):
        fields = self.env['incoming.product.info'].fields_get()
        selection = [(name, field['string']) for name, field in fields.items()]
        selection.append(('custom', 'Create New Field'))
        return selection

    @api.onchange('destination_field_name', 'source_column')
    def _onchange_destination_field_name(self):
        if self.destination_field_name == 'custom':
            self.custom_field_name = self._generate_custom_field_name(self.source_column)
        else:
            self.custom_field_name = False
        self.custom_label = self._get_default_custom_label()

    @api.model
    def _generate_unique_custom_label(self, config_id, base_label):
        counter = 1
        unique_label = base_label
        while self.search_count([('config_id', '=', config_id), ('custom_label', '=', unique_label)]):
            unique_label = f"{base_label}_{counter}"
            counter += 1
        return unique_label
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('custom_label'):
                vals['custom_label'] = vals.get('source_column') or vals.get('custom_field_name') or _('Unnamed Column')
        return super(ImportColumnMapping, self).create(vals_list)

    def write(self, vals):
        if vals.get('destination_field_name') == 'custom':
            vals['custom_field_name'] = self._generate_custom_field_name(self.source_column)
        elif 'destination_field_name' in vals:
            vals['custom_field_name'] = False
        if 'destination_field_name' in vals and 'custom_label' not in vals:
            vals['custom_label'] = self.source_column or vals.get('custom_field_name', 'Unknown')
        return super(ImportColumnMapping, self).write(vals)

    def _get_default_custom_label(self):
        self.ensure_one()
        if self.is_custom_field:
            return self.source_column or 'Custom Field'
        selection = self._fields['destination_field_name'].selection
        if callable(selection):
            selection = selection(self)
        selection_dict = {item[0]: item[1] for item in selection if isinstance(item, (list, tuple)) and len(item) == 2}
        return selection_dict.get(self.destination_field_name, self.source_column or self.destination_field_name)

    @api.model
    def _generate_custom_field_name(self, source_column):
        base_name = 'x_' + (source_column or '').lower().replace(' ', '_')
        existing_fields = self.env['incoming.product.info'].fields_get().keys()
        counter = 1
        field_name = base_name
        while field_name in existing_fields:
            field_name = f"{base_name}_{counter}"
            counter += 1
        return field_name

    @api.model
    def _fill_empty_custom_labels(self):
        empty_labels = self.search([('custom_label', '=', False)])
        for record in empty_labels:
            record.custom_label = record._get_default_custom_label()

    @api.constrains('config_id', 'custom_label', 'is_custom_field')
    def _check_unique_custom_label(self):
        for record in self:
            if not record.is_custom_field:
                same_label = self.search([
                    ('config_id', '=', record.config_id.id),
                    ('custom_label', '=', record.custom_label),
                    ('id', '!=', record.id),
                    ('is_custom_field', '=', False)
                ])
                if same_label:
                    raise ValidationError(_("Custom label must be unique per configuration for non-custom fields."))