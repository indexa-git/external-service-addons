from odoo import fields
from odoo.tests import tagged
from odoo.exceptions import ValidationError
from odoo.addons.l10n_do_accounting.tests.common import L10nDOTestsCommon
import unittest.mock as mock


@tagged("-at_install", "post_install")
class AccountMoveTest(L10nDOTestsCommon):
    @mock.patch("requests.get")
    def test_001_ncf_validation_valid_response(self, mock_get):
        """
        Test NCF validation with valid response from external service
        """
        # Setup mock response
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.text = '{"valid": true}'
        mock_get.return_value = mock_response

        # Create account move
        account_move = self._create_l10n_do_invoice(
            data={"document_number": "B0100000002"},
            invoice_type="out_invoice",
        )

        # Check valid NCF
        self.assertTrue(account_move._has_valid_ncf(), "NCF should be valid")

    @mock.patch("requests.get")
    def test_002_ncf_validation_invalid_response(self, mock_get):
        """
        Test NCF validation with invalid response from external service
        """
        # Setup mock response
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.text = '{"valid": false}'
        mock_get.return_value = mock_response

        # Create account move
        account_move = self._create_l10n_do_invoice(
            data={"document_number": "B0100000002"},
            invoice_type="out_invoice",
        )

        # Check invalid NCF
        self.assertFalse(account_move._has_valid_ncf(), "NCF should be invalid")

    def test_003_ncf_format_validation(self):
        """
        Test validation of incorrect NCF format
        """
        # Check raise of ValidationError
        with self.assertRaises(
            ValidationError, msg="NCF A0000000001 doesn't have the correct structure"
        ):
            self._create_l10n_do_invoice(
                data={"document_number": "A0000000001"},
                invoice_type="out_invoice",
            )
