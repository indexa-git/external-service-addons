{
    "name": "Dominican Banks Currency Update",
    "summary": """
    Updates company secondary currency rates from dominican banks
    """,
    "author": "Indexa",
    "website": "https://www.indexa.do",
    "category": "Accounting",
    "version": "15.0.1.0.0",
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
