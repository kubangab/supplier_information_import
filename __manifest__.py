#  © opyright 2024 Lasse Larsson, Kubang AB
{
    'name': 'Supplier Information Import',
    'version': '5.0.0',
    'category': 'Inventory',
    'summary': 'Import and manage incoming product information',
    'description': """
This module allows importing product information from various suppliers and managing the reception of physical products.
    """,
    'author': 'Lasse Larsson, Kubang AB',
    'depends': ['base', 'product', 'stock', 'purchase','sale'],
    'license': 'LGPL-3',
    'data': [
        'security/ir.model.access.csv',
        'data/email_templates.xml',
        'wizards/product_operations_views.xml',
        'views/import_config_views.xml',
        'views/file_analysis_wizard_view.xml',
        'views/incoming_product_info_views.xml',
        'views/product_views.xml',
        'views/stock_picking_views.xml',
        'views/sale_order_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
