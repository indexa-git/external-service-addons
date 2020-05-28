{
    'name': "l10n_do_ecf_invoicing",

    'summary': """
        Short (1 phrase/line) summary of the module's purpose, used as
        subtitle on modules listing or apps.openerp.com""",

    'description': """
        Long description of module's purpose
    """,

    'author': "Indexa",
    'website': "https://www.indexa.do",

    'category': 'Accounting',
    'version': "13.0.1.0.0",
    'depends': ['l10n_do_accounting'],
    'data': [
        # 'security/ir.model.access.csv',
        'views/views.xml',
        'views/templates.xml',
    ],
    'demo': [
        'demo/demo.xml',
    ],
}
