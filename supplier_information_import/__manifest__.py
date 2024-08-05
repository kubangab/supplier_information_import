{
    'name': 'Supplier Information Import',
    'version': '16.0.1.0.0',
    'category': 'Inventory',
    'summary': 'Import module for Supplier Information',
    'description': """
        This module handles the import process of supplier information.
        It includes functionality for importing product information and
        managing incoming product data.
    """,
    'author': 'Lasse Larsson, Kubang AB',
    'website': 'https://www.kubang.se',
    'depends': ['base', 'product', 'stock', 'purchase', 'supplier_information_config'],
    'data': [
        'security/ir.model.access.csv',
        'views/product_views.xml',
        'views/incoming_product_info_views.xml',
        'wizards/product_operations_views.xml',
        'wizards/import_product_info_views.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}