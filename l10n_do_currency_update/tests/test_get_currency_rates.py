from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError
from odoo.tests import tagged
from unittest.mock import patch
from odoo import _
from odoo import fields


@tagged("post_install", "-at_install")
class GetCurrencyRatesTest(TransactionCase):

    def setUp(self):
        super(GetCurrencyRatesTest, self).setUp()
        # Create a test company or get the default company
        self.company = self.env['res.company'].create({'name': 'Test Company'})

    def test_001_update_currency_rates(self):
        """Test automatic currency update functionality."""

        # Set settings for the test company
        self.company.l10n_do_currency_provider = "bpd"  # Replace with desired bank
        self.company.l10n_do_currency_interval_unit = "daily"

        # Patch the `l10n_do_update_currency_rates` method on the company
        with patch.object(type(self.company), "l10n_do_update_currency_rates", return_value=True) as mock_update:
            # Simulate the method updating the last sync date
            self.company.l10n_do_last_currency_sync_date = fields.Date.today()

            # Trigger the update through the settings function
            settings = self.env['res.config.settings'].create({})
            settings.l10n_do_update_currency_rates()

            # Assert that the company method was called
            mock_update.assert_called_once_with()

            # Assert that the last sync date is updated
            self.assertEqual(
                self.company.l10n_do_last_currency_sync_date,
                fields.Date.today(),
                "Last sync date not updated after successful update",
            )

    def test_002_update_currency_rates_error(self):
        """Test handling of errors during currency update."""

        # Set settings for the test company
        self.company.l10n_do_currency_provider = "bnr"  # Replace with desired bank
        self.company.l10n_do_currency_interval_unit = "daily"

        # Simulate an error within the `l10n_do_update_currency_rates` method
        def trigger_error():
            raise UserError(
                _("Unable to fetch currency from given API. The service may be temporary down. Please try again in a "
                  "moment."))

        # Patch the method to raise an error
        with patch.object(type(self.company), "l10n_do_update_currency_rates", side_effect=trigger_error):
            # Trigger the update through the settings function
            settings = self.env['res.config.settings'].create({})
            with self.assertRaises(UserError) as e:
                settings.l10n_do_update_currency_rates()

            # Assert the expected error message
            self.assertEqual(
                str(e.exception),
                _("Unable to fetch currency from given API. The service may be temporary down. Please try again in a "
                  "moment."),
            )

            # Assert that the last sync date is not updated
            self.assertNotEqual(
                self.company.l10n_do_last_currency_sync_date,
                fields.Date.today(),
                "Last sync date updated despite update failure",
            )
