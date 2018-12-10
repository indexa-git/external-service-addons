# -*- coding: utf-8 -*-
{
    'name': "l10n_do_currency_update",

    'summary': """
        Short (1 phrase/line) summary of the module's purpose, used as
        subtitle on modules listing or apps.openerp.com""",

    'description': """
        Long description of module's purpose
    """,

    'author': "Indexa",
    'website': "https://www.indexa.do",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/master/odoo/addons/base/module/module_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base',
                'account'],

    # always loaded
    'data': [
        'data/ir_cron_data.xml',
        'data/ir_config_parameter_data.xml',
        'views/account_config_settings_views.xml',
    ],
}