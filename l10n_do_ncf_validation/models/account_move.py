import requests
from odoo.tools import safe_eval

from odoo import models, _
from odoo.exceptions import ValidationError


class AccountMove(models.Model):
    _inherit = "account.move"

    def _has_valid_ncf(self):
        """
        Query external service to check NCF status
        :return: boolean: True if valid NCF, otherwise False
        """
        self.ensure_one()

        rnc = self.partner_id.vat
        if not rnc or not str(rnc).isdigit() or len(rnc) not in (9, 11):
            raise ValidationError(
                _("A valid RNC/Cédula is required to request a NCF validation.")
            )

        ncf = self.ref
        if not ncf or not len(ncf) in (11, 13) or ncf[0] not in ("B", "E"):
            raise ValidationError(
                _("NCF %s has a invalid format. Please fix it and try again." % ncf)
            )

        get_param = self.env["ir.config_parameter"].sudo().get_param
        payload = {"ncf": ncf, "rnc": rnc}

        try:
            response = requests.get(
                get_param("ncf.api.url"),
                payload,
                headers={"x-access-token": get_param("ncf.api.token")},
            )
        except requests.exceptions.ConnectionError:
            raise ValidationError(
                _(
                    "Could not establish communication with external service.\n"
                    "Try again later."
                )
            )

        if response.status_code == 403:
            raise ValidationError(
                _("Odoo couldn't authenticate with external service.")
            )

        response_text = (
            str(response.text).replace("true", "True").replace("false", "False")
        )
        if safe_eval(response_text).get("valid", False):
            return True

        return False

    def post(self):

        l10n_do_fiscal_invoice = self.filtered(
            lambda inv: inv.company_id.country_id == self.env.ref("base.do")
            and inv.l10n_latam_use_documents
            and inv.company_id.ncf_validation_target != "none"
        )
        for invoice in l10n_do_fiscal_invoice:
            ncf_validation_target = invoice.company_id.ncf_validation_target
            if ncf_validation_target != "both":

                if (
                    ncf_validation_target == "internal"
                    and not invoice.is_l10n_do_internal_sequence
                ):
                    continue
                elif (
                    ncf_validation_target == "external"
                    and invoice.is_l10n_do_internal_sequence
                ):
                    continue

            if not invoice._has_valid_ncf():
                raise ValidationError(
                    _(
                        "Cannot validate Fiscal Invoice "
                        "because %s is not a valid NCF" % invoice.ref
                    )
                )

        return super(AccountMove, self).post()
