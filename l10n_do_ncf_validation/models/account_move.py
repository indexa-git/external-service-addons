from odoo import models, _
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    def _has_valid_ncf(self):
        """
        Query external service to check NCF status
        :return: boolean: True if valid NCF, otherwise False
        """
        self.ensure_one()
        # TODO: implement external service request
        return False

    def _is_internal_generated_ncf(self):
        """
        Returns True if NCF is internally generated, otherwise False
        """
        self.ensure_one()
        if self.type in (
            "out_invoice",
            "out_refund",
        ) or self.l10n_latam_document_type_id.l10n_do_ncf_type in (
            "minor",
            "e-minor",
            "informal",
            "e-informal",
        ):
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
                    and invoice._is_internal_generated_ncf()
                ):
                    pass
                elif (
                    ncf_validation_target == "external"
                    and invoice._is_internal_generated_ncf()
                ):
                    continue

            if not invoice._has_valid_ncf():
                raise UserError(
                    _(
                        "Cannot validate Fiscal Invoice "
                        "because %s is not a valid NCF" % invoice.ref
                    )
                )

        return super(AccountMove, self).post()
