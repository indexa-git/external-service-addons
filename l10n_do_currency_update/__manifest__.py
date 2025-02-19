{
    "name": "Dominican Banks Currency Update",
    "summary": """
    Updates company secondary currency rates from dominican banks
    """,
    "author": "Indexa",
    "website": "https://www.indexa.do",
    "category": "Accounting",
    "license": "LGPL-3",
<<<<<<< HEAD
    "version": "17.0.1.0.1",
=======
    "version": "15.0.1.0.2",
>>>>>>> 19aee4e ([IMP] l10n_do_currency_update : add forceupdate false)
    "depends": ["account"],
    "data": [
        "data/ir_cron_data.xml",
        "data/ir_config_parameter_data.xml",
        "views/res_config_settings_views.xml",
    ],
    "demo": [
        "demo/res_company_demo.xml",
    ],
    "installable": True,
}
