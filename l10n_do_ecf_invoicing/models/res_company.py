from werkzeug import urls
from odoo import models, fields, api, _
from odoo .exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = "res.company"

    l10n_do_ecf_service_env = fields.Selection(
        [("TesteCF", "Test"), ("CerteCF", "Certification"), ("eCF", "Production")],
        string="ECF Service Environment",
        required=True,
        default="TesteCF",
    )
    l10n_do_send_ecf_on_payment = fields.Boolean(
        "Send ECF On Payment",
    )

    @api.constrains("l10n_do_ecf_service_env")
    def _check_ecf_service_env(self):
        """
        Checks ECF environment consistency. Once an ECF is issued to one environment,
        a distinct one can't be used.
        """
        for company in self:
            signed_invoice = self.env["account.move"].search(
                [
                    ("l10n_do_electronic_stamp", "!=", False),
                    ("company_id", "=", company.id),
                ],
                limit=1,
            )
            if not signed_invoice:
                continue

            company_service_env = company.l10n_do_ecf_service_env
            current_service_env = urls.url_unquote(
                signed_invoice.l10n_do_electronic_stamp
            ).split("/")[3]
            if (
                    company_service_env == "eCF"
                    and current_service_env != company_service_env
            ):
                raise ValidationError(
                    _(
                        "You cannot change company ECF Environment since there "
                        "are invoices sent to %s" % current_service_env
                    )
                )
