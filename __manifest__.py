#  © opyright 2024 Lasse Larsson, Kubang AB
{
    'name': 'Product Information Import',
    'version': '1.0',
    'category': 'Inventory',
    'summary': 'Import and manage incoming product information',
    'description': """
This module allows importing product information from various suppliers and managing the reception of physical products.
    """,
    'author': 'Lasse Larsson, Kubang AB',
    'depends': ['base', 'product', 'stock'],
    'license': 'LGPL-3',
    'data': [
        'security/ir.model.access.csv',
        'views/incoming_product_info_views.xml',
        'wizards/product_operations_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}