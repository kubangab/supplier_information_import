from odoo import api, SUPERUSER_ID

def post_init_hook(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    fill_empty_destination_field_names(env)

def fill_empty_destination_field_names(env):
    # Get the English translation
    english = env['res.lang'].search([('code', '=', 'en_US')], limit=1)
    
    if english:
        # Temporarily activate English language
        original_lang = env.context.get('lang')
        env = env(context=dict(env.context, lang='en_US'))

        # Fill empty destination field names
        mapping_model = env['import.column.mapping']
        empty_records = mapping_model.search([('destination_field_name', '=', False), ('destination_field', '!=', False)])
        
        for record in empty_records:
            record.with_context(lang='en_US').write({
                'destination_field_name': record.destination_field.field_description.split(' (')[0]
            })

        # Restore original language
        if original_lang:
            env = env(context=dict(env.context, lang=original_lang))

def uninstall_hook(cr, registry):
    # This function will be called when the module is uninstalled
    # You can add any cleanup code here if needed
    pass