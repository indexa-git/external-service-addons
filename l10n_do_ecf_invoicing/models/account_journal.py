from odoo import models, api


class AccountJournal(models.Model):
    _inherit = "account.journal"

    @api.depends(
        "type", "company_id", "company_id.country_id", "l10n_latam_use_documents"
    )
    def _compute_compatible_edi_ids(self):
        if hasattr(self, "_compute_compatible_edi_ids"):
            l10n_do_journals = self.filtered(
                lambda j: j.l10n_latam_use_documents and j.country_code == "DO"
            )
            l10n_do_journals.write({"compatible_edi_ids": False})
            super(AccountJournal, self - l10n_do_journals)._compute_compatible_edi_ids()

    @api.depends(
        "type", "company_id", "company_id.country_id", "l10n_latam_use_documents"
    )
    def _compute_edi_format_ids(self):
        if hasattr(self, "_compute_edi_format_ids"):
            l10n_do_journals = self.filtered(
                lambda j: j.l10n_latam_use_documents and j.country_code == "DO"
            )
            l10n_do_journals.write({"edi_format_ids": False})
            super(AccountJournal, self - l10n_do_journals)._compute_edi_format_ids()
