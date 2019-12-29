{
    'name': 'Dominican Tax ID Validation',
    'version': '12.0.0.0.0',
    'summary': 'Validate RNC/Cédula from external service',
    'category': 'Extra Tools',
    'author': 'Guavana,'
              'Indexa,'
              'Iterativo',
    'website': 'https://github.com/odoo-dominicana',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'base_setup',
    ],
    'data': [
        'views/res_partner_views.xml',
        'views/res_config_settings_views.xml',
        'data/ir_config_parameter_data.xml',
    ],
}
