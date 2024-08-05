{
    'name': 'Supplier Information Config',
    'version': '16.0.1.0.0',
    'category': 'Inventory',
    'summary': 'Configuration module for Supplier Information Import',
    'description': """
        This module provides configuration options for importing supplier information.
        It includes import format configuration, combination rules, column mapping,
        and unmatched model handling.
    """,
    'author': 'Lasse Larsson, Kubang AB',
    'website': 'https://www.kubang.se',
    'depends': ['base', 'product', 'stock', 'purchase'],
    'data': [
        'security/ir.model.access.csv',
        'views/import_config_views.xml',
        'views/product_views.xml',
        'views/file_analysis_wizard_view.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}