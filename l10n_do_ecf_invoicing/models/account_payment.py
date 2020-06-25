from odoo import models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    def post(self):

        res = super(AccountPayment, self).post()

        # If an invoice was not sent after posting,
        # it means a partial or full payment is expected.

        fiscal_invoices = self.invoice_ids.filtered(
            lambda i: i.is_ecf_invoice
            and i.l10n_do_ecf_send_state not in ("delivered_accepted", "delivered_pending")
        )
        fiscal_invoices.with_context(ecf_sending_model=self._name).send_ecf_data()

        return res
