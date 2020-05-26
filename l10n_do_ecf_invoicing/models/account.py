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

        def get_payment_type(inv):
            # TODO: evaluate payment type 3 <Gratuito> Check DGII docs
            if not inv.invoice_payment_term_id and inv.invoice_date_due:
                return 2
            elif not inv.invoice_payment_term_id:
                return 1
            elif not inv.invoice_payment_term_id == inv.env.ref(
                    "account.account_payment_term_immediate"):
                return 2
            else:
                return 1

        def get_payment_forms(inv):

            payment_dict = {'cash': '01', 'bank': '02', 'card': '03',
                            'credit': '04', 'swap': '06',
                            'credit_note': '07'}

            payments = []

            for payment in self._get_reconciled_info_JSON_values():
                payment_id = self.env['account.payment'].browse(
                    payment.get('account_payment_id'))
                move_id = False
                if payment_id:
                    if payment_id.journal_id.type in ['cash', 'bank']:
                        payment_form = payment_id.journal_id.l10n_do_payment_form
                        payments.append({
                            "FormaPago": payment_dict[payment_form],
                            "MontoPago": payment.get('amount', 0)
                        })

                elif not payment_id:
                    move_id = self.env['account.move'].browse(
                        payment.get('move_id'))
                    if move_id:
                        payments.append({
                            "FormaPago": payment_dict['swap'],
                            "MontoPago": payment.get('amount', 0)
                        })
                elif not move_id:
                    # If invoice is paid, but the payment doesn't come from
                    # a journal, assume it is a credit note
                    payments.append({
                        "FormaPago": payment_dict['credit_note'],
                        "MontoPago": payment.get('amount', 0)
                    })

            # TODO: implement amount conversion to company currency
            return payments

        # At this point, json only contains required
        # fields in all e-CF's types
        ecf_json = {
            "ECF": {
                "Encabezado": {
                    "Version": "1.0",  # TODO: is this value going to change anytime?
                    "IdDoc": {
                        "TipoeCF": self.l10n_latam_document_type_id.l10n_do_ncf_type,
                        "eNCF": self.l10n_latam_document_number,
                        "TipoPago": get_payment_type(self),
                        "TablaFormasPago": {"FormaDePago": get_payment_forms(self)}
                    },
                    "Emisor": {
                        "RNCEmisor": self.company_id.vat,
                        "RazonSocialEmisor": self.company_id.name,
                        "DireccionEmisor": self.company_id.street,
                        "FechaEmision": dt.strftime(self.invoice_date, "%d-%m-%Y"),
                        "NumeroFacturaInterna": self.name,
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

        l10n_do_ncf_type = self.l10n_latam_document_type_id.l10n_do_ncf_type
        is_l10n_do_partner = self.partner_id.country_id and \
                             self.partner_id.country_id.code == "DO"
        partner_vat = self.partner_id.vat

        if l10n_do_ncf_type not in ("32", "34"):
            # TODO: pending
            ecf_json["Encabezado"]["IdDoc"]["FechaVencimientoSecuencia"] = "31-12-2020"

        if l10n_do_ncf_type == "34":
            origin_move_id = self.search(
                [('l10n_latam_document_number', '=', self.l10n_do_origin_ncf)])
            delta = origin_move_id.invoice_date - fields.Date.context_today(self)
            ecf_json["Encabezado"]["IdDoc"][
                "IndicadorNotaCredito"] = int(delta.days > 30)

        if self.company_id.l10n_do_ecf_deferred_submissions:
            ecf_json["Encabezado"]["IdDoc"]["IndicadorEnvioDiferido"] = 1

        if l10n_do_ncf_type not in ("43", "44", "46"):
            ecf_json["Encabezado"]["IdDoc"]["IndicadorMontoGravado"] = int(
                any(True for t in self.invoice_line_ids.tax_ids if t.price_include))

        if l10n_do_ncf_type not in ("41", "43", "47"):
            ecf_json["Encabezado"]["IdDoc"]["TipoIngresos"] = self.l10n_do_income_type

        if ecf_json["Encabezado"]["IdDoc"]["TipoPago"] == 2:
            ecf_json["Encabezado"]["IdDoc"]["FechaLimitePago"] = dt.strftime(
                self.invoice_date_due, "%d-%m-%Y")

            delta = self.invoice_date_due - self.invoice_date
            ecf_json["Encabezado"]["IdDoc"]["TerminoPago"] = "%s días" % delta.days

        if l10n_do_ncf_type not in ("43", "47"):
            if "Comprador" not in ecf_json["Encabezado"]:
                ecf_json["Encabezado"]["Comprador"] = {}

            if l10n_do_ncf_type in ("31", "41", "45"):
                ecf_json["Encabezado"]["Comprador"][
                    "RNCComprador"] = partner_vat

            if l10n_do_ncf_type == "32" or partner_vat:
                ecf_json["Encabezado"]["Comprador"][
                    "RNCComprador"] = partner_vat

            if l10n_do_ncf_type in ("33", "34"):
                origin_move_id = self.search(
                    [('l10n_latam_document_number', '=', self.l10n_do_origin_ncf)])
                if origin_move_id and origin_move_id.amount_total_signed >= 250000:
                    if is_l10n_do_partner:
                        ecf_json["Encabezado"]["Comprador"][
                            "RNCComprador"] = partner_vat
                    else:
                        ecf_json["Encabezado"]["Comprador"][
                            "IdentificadorExtranjero"] = partner_vat

            if l10n_do_ncf_type == "44":
                if is_l10n_do_partner and partner_vat:
                    ecf_json["Encabezado"]["Comprador"][
                        "RNCComprador"] = partner_vat
                elif not is_l10n_do_partner and partner_vat:
                    ecf_json["Encabezado"]["Comprador"][
                        "IdentificadorExtranjero"] = partner_vat

            if self.company_id.l10n_do_dgii_tax_payer_type == "special":
                if is_l10n_do_partner:
                    ecf_json["Encabezado"]["Comprador"][
                        "RNCComprador"] = partner_vat
                else:
                    ecf_json["Encabezado"]["Comprador"][
                        "IdentificadorExtranjero"] = partner_vat

        if l10n_do_ncf_type not in ("31", "41", "43", "45") and not is_l10n_do_partner:
            if "Comprador" not in ecf_json["Encabezado"]:
                ecf_json["Encabezado"]["Comprador"] = {}

            if l10n_do_ncf_type == "32" and self.amount_total_signed >= 250000:
                ecf_json["Encabezado"]["Comprador"][
                    "IdentificadorExtranjero"] = partner_vat

        if l10n_do_ncf_type not in ("43", "47"):

            if l10n_do_ncf_type == "32":
                if self.amount_total_signed >= 250000 or partner_vat:
                    ecf_json["Encabezado"]["Comprador"][
                        "RazonSocialComprador"] = self.partner_id.name

            if l10n_do_ncf_type in ("33", "34"):
                origin_move_id = self.search(
                    [('l10n_latam_document_number', '=', self.l10n_do_origin_ncf)])
                if origin_move_id and origin_move_id.amount_total_signed >= 250000:
                    ecf_json["Encabezado"]["Comprador"][
                        "RazonSocialComprador"] = self.partner_id.name

            else:  # 31, 41, 44, 45, 46
                ecf_json["Encabezado"]["Comprador"][
                    "RazonSocialComprador"] = self.partner_id.name

        return ecf_json
