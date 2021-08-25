import requests
from odoo.tools.safe_eval import safe_eval

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

        def check_rnc_format(vat):
            if not vat or not str(vat).isdigit() or len(vat) not in (9, 11):
                raise ValidationError(
                    _("A valid RNC/Cédula is required to request a NCF validation.")
                )

        rnc = (
            self.company_id.vat
            if self.move_type not in ("in_invoice", "in_refund")
            else self.partner_id.vat
        )
        check_rnc_format(rnc)

        ncf = self.ref
        if not ncf or len(ncf) not in (11, 13) or ncf[0] not in ("B", "E"):
            raise ValidationError(
                _("NCF %s has a invalid format. Please fix it and try again." % ncf)
            )

        get_param = self.env["ir.config_parameter"].sudo().get_param
        payload = {"ncf": ncf, "rnc": rnc}

        if self.is_ecf_invoice and self.company_id.validate_ecf:
            l10n_do_ecf_security_code = self.l10n_do_ecf_security_code
            if (
                not str(l10n_do_ecf_security_code).strip()
                or len(l10n_do_ecf_security_code) != 6
            ):
                raise ValidationError(
                    _("ECF Security Code must be a 6 character length alphanumeric")
                )
            buyer_rnc = (
                self.company_id.vat
                if self.move_type in ("in_invoice", "in_refund")
                else self.partner_id.vat
            )
            check_rnc_format(buyer_rnc)

            payload.update(
                {
                    "buyerRNC": buyer_rnc,
                    "securityCode": self.l10n_do_ecf_security_code,
                }
            )

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

    def action_post(self):

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
                    and not invoice.l10n_latam_manual_document_number
                ):
                    continue

            if not invoice._has_valid_ncf():
                raise ValidationError(
                    _(
                        "Cannot validate Fiscal Invoice "
                        "because %s is not a valid NCF" % invoice.ref
                    )
                )

        return super(AccountMove, self).action_post()
