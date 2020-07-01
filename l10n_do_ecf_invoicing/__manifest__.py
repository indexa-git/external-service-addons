{
    "name": "l10n_do_ecf_invoicing",
    "summary": """
        Short (1 phrase/line) summary of the module's purpose, used as
        subtitle on modules listing or apps.openerp.com""",
    "description": """
        Long description of module's purpose
    """,
    "author": "Indexa",
    "website": "https://www.indexa.do",
    "category": "Accounting",
    "version": "13.0.1.0.0",
    "depends": ["l10n_do_accounting", "l10n_do_debit_note"],
    "data": [
        # 'security/ir.model.access.csv',
        "views/account_views.xml",
        "views/res_company_views.xml",
        "data/ir_config_parameter_data.xml",
        "data/ir_cron_data.xml",
    ],
    "demo": ["demo/demo.xml"],
}
