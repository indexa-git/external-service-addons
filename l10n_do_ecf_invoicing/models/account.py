#  Copyright (c) 2020 - Indexa SRL. (https://www.indexa.do) <info@indexa.do>
#  See LICENSE file for full licensing details.

from datetime import datetime as dt

from odoo import models, fields, api


class AccountMove(models.Model):
    _inherit = "account.move"

    def _get_invoice_ecf_json(self):
        """
        Regarding invoice type, returns its e-CF json
        representation.
        """

        self.ensure_one()

        # At this point, json only contains required
        # fields in all e-CF's types
        ecf_json = {
            "ECF": {
                "Encabezado": {
                    "Version": "1.0",  # TODO: is this value going to change anytime?
                    "IdDoc": {
                        "TipoeCF": self.l10n_latam_document_type_id.l10n_do_ncf_type,
                        "eNCF": self.l10n_latam_document_number,
                    },
                    "Emisor": {
                        "RNCEmisor": self.partner_id.vat,
                        "RazonSocialEmisor": self.company_id.name,
                        "DireccionEmisor": self.company_id.street,
                        "FechaEmision": dt.strftime(self.invoice_date, "%d-%m-%Y"),
                    },
                    "Totales": {
                        "MontoTotal": self.amount_total_signed,
                    }
                },
                "DetallesItems": {
                    # Items data would be added later
                },
            },
        }

        if self.l10n_latam_document_type_id.l10n_do_ncf_type not in ("32", "34"):
            # TODO: pending
            ecf_json["Encabezado"]["IdDoc"]["FechaVencimientoSecuencia"] = "31-12-2020"

        if self.l10n_latam_document_type_id.l10n_do_ncf_type == "34":
            origin_move_id = self.search(
                [('l10n_latam_document_number', '=', self.l10n_do_origin_ncf)])
            delta = origin_move_id.invoice_date - fields.Date.context_today(self)
            ecf_json["Encabezado"]["IdDoc"][
                "IndicadorNotaCredito"] = int(delta.days > 30)

        return ecf_json
