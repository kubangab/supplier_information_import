#  © opyright 2024 Lasse Larsson, Kubang AB
{
    'name': 'Supplier Information Import',
    'version': '16.0.5.2.0',
    'category': 'Inventory',
    'summary': 'Import and manage incoming product information',
    'description': """
This module allows importing product information from various suppliers and managing the reception of physical products.
    """,
    'author': 'Lasse Larsson, Kubang AB',
    'depends': [
                'base',
                'product',
                'stock',
                'purchase',
                'supplier_information_config',
                'supplier_information_import_file',
                'supplier_information_logistics'
    ],
    'data': ['views/menu_views'],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
    'auto_install': False,
}