{
    'name': "Dominican Banks Currency Update",
    'summary': """
        Updates company secondary currency rates from dominican banks""",

    'author': "Indexa",
    'website': "https://www.indexa.do",
    'category': 'Accounting',
    'version': "10.0.1.0.0",
    'depends': ['base',
                'account'],
    'data': [
        'data/ir_cron_data.xml',
        'data/ir_config_parameter_data.xml',
        'views/account_views.xml',
        'views/account_config_settings_views.xml',
    ],
    'demo': [
        'demo/res_company_demo.xml',
    ],
}
