#  © opyright 2024 Lasse Larsson, Kubang AB
{
    'name': 'Supplier Information Import',
    'version': '16.0.4.0.0',
    'category': 'Inventory',
    'summary': 'Import and manage incoming product information',
    'description': """
This module allows importing product information from various suppliers and managing the reception of physical products.
    """,
    'author': 'Lasse Larsson, Kubang AB',
    'depends': ['base', 'product', 'stock', 'purchase'],
    'license': 'LGPL-3',
    'data': [
        'security/ir.model.access.csv',
        'views/menu_views.xml',
        'data/email_templates.xml',
        'views/incoming_product_info_views.xml',
        'views/import_config_views.xml',
        'views/product_views.xml',
        'views/stock_picking_views.xml',
        'wizards/product_operations_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}