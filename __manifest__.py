# -*- coding: utf-8 -*-
{
    'name': "Approval Rules",

    'summary': """
      Allows customization to the Purchase Approval process without taking restarting the Server.""",

    'description': """
        This is an Odoo 17 customization I created for Electric Power Systems. I have made the necessary changes to post a copy
        in my personal git.
                
        It allows users to easily make rules for the purchase approval process to enforce purchasing policy.
        It supports quick group section for a multi-tier approval process and even supports custom python code.
        This allows it to be extremely flexible for each Odoo instance.
    """,

    'author': "Tanner Troumbley",
    'category': 'Inventory/Purchase',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'purchase'],

    # always loaded
    'data': [
        'data/conditions.xml',
        'security/ir.model.access.csv',
        'security/purchase_security.xml',
        'views/purchase_approval_rules.xml',
        'views/res_config_settings.xml',
        'views/purchase.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
    
    'installable': True,
    'auto_install': False,
    'application': True,
    'license': 'LGPL-3',
}
