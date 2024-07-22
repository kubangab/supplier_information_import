#  © opyright 2024 Lasse Larsson, Kubang AB
{
    'name': 'Supplier Product Import',
    'version': '1.0',
    'category': 'Inventory',
    'summary': 'Import supplier products from Excel or CSV',
    'description': """
This module allows importing supplier product information from Excel or CSV files.
    """,
    'author': 'Lasse Larsson, Kubang AB',
    'depends': ['base', 'product', 'stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/supplier_product_views.xml',
        'wizard/import_supplier_products_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
