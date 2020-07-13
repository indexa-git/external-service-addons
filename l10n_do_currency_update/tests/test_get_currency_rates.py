
from odoo import fields
from odoo.tests.common import TransactionCase


class GetCurrencyRatesTest(TransactionCase):

    def test_001_get_currency_rates(self):

        data = self.env["res.company"].get_currency_rates(
            {"bank": "bpd", "date": fields.Date.today()},
            "a79c2dfc-858d-4813-bb77-7695c1c320db"
        )
        import ast
        data = ast.literal_eval(data)
        status = data.get("status", False)

        assert status
        assert status == "success"
