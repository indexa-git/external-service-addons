# -*- coding: utf-8 -*-
{
    'name': "Dominican Banks Currency Update",

    'summary': """
        Updates company secondary currency rates from dominican banks""",

    'author': "Indexa",
    'website': "https://www.indexa.do",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/master/odoo/addons/base/module/module_data.xml
    # for the full list
    'category': 'Accounting',
    'version': '1.0.1',

    # any module necessary for this one to work correctly
    'depends': [
        'base',
        'account',
    ],

    # always loaded
    'data': [
        'data/ir_cron_data.xml',
        'data/ir_config_parameter_data.xml',
        'wizard/update_rate_wizard_view.xml',
        'views/account_views.xml',
        'views/res_config_settings_views.xml',
        'wizard/res_company_currency_hash_wizard_views.xml',
    ],
    'demo': [
        'demo/res_company_demo.xml',
    ],
}
