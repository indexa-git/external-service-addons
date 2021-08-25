from odoo import fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class GetCurrencyRatesTest(AccountTestInvoicingCommon):
    def test_001_get_currency_rates(self):

        data = self.env["res.company"].get_currency_rates(
            {"bank": "bpd", "date": fields.Date.today()},
            "a79c2dfc-858d-4813-bb77-7695c1c320db",
        )
        import ast

        data = ast.literal_eval(data)
        status = data.get("status", False)

        assert status
        assert status == "success"
