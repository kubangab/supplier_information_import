{
    'name': 'Supplier Information Logistics',
    'version': '16.0.1.0.0',
    'category': 'Inventory',
    'summary': 'Logistics extension for Supplier Information',
    'description': """
        This module extends stock picking and sales order functionalities
        to work with imported supplier information.
    """,
    'author': 'Lasse Larsson, Kubang AB',
    'website': 'https://www.kubang.se',
    'depends': [
        'base', 
        'stock', 
        'sale', 
        'supplier_information_config', 
        'supplier_information_import'
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/email_templates.xml',
        'views/stock_picking_views.xml',
        'views/sale_order_views.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}