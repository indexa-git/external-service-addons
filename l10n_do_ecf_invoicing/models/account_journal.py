from odoo import models, api


class AccountJournal(models.Model):
    """
    The Electronic Invoice sequences may not be created
    at the time this module is installed. This function
    creates them automatically so that errors are avoided
    if done manually ;)

    DO NOT FORWARD PORT
    """

    _inherit = "account.journal"

    def _generate_missing_ecf_sequences(self):
        self.ensure_one()
        journal_doc_types = self.l10n_do_sequence_ids.mapped(
            "l10n_latam_document_type_id"
        )
        ncf_types = self._get_journal_ncf_types()
        documents = self.env["l10n_latam.document.type"].search(
            [
                ("id", "not in", journal_doc_types.ids),
                ("country_id.code", "=", "DO"),
                (
                    "internal_type",
                    "in",
                    ["invoice", "in_invoice", "debit_note", "credit_note"],
                ),
                ("active", "=", True),
                "|",
                ("l10n_do_ncf_type", "=", False),
                ("l10n_do_ncf_type", "in", ncf_types),
            ]
        )
        for document in documents:
            self.env["ir.sequence"].sudo().create(
                document._get_document_sequence_vals(self)
            )

    @api.model
    def generate_missing_ecf_sequences(self):
        l10n_do_fiscal_journals = self.search(
            [
                ("l10n_latam_use_documents", "=", True),
                ("type", "in", ("sale", "purchase")),
            ]
        )
        for journal in l10n_do_fiscal_journals.filtered(
            lambda j: j.l10n_latam_country_code == "DO"
        ):
            journal._generate_missing_ecf_sequences()
