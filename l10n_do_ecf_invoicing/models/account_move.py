#  Copyright (c) 2020 - Indexa SRL. (https://www.indexa.do) <info@indexa.do>
#  See LICENSE file for full licensing details.

import json
import base64
import logging
import requests
from datetime import datetime as dt
from collections import OrderedDict as od

from odoo import models, fields, api, _
from odoo.tools.safe_eval import safe_eval
from odoo.exceptions import ValidationError, RedirectWarning, UserError


_logger = logging.getLogger(__name__)

ECF_STATE_MAP = {
    "Aceptado": "delivered_accepted",
    "AceptadoCondicional": "conditionally_accepted",
    "EnProceso": "delivered_pending",
    "Rechazado": "delivered_refused",
    "FirmadoPendiente": "signed_pending",
    "error": "signed_pending",
}


class AccountMove(models.Model):
    _inherit = "account.move"

    def _get_l10n_do_ecf_send_state(self):
        """Returns actual invoice ECF sending status

        - to_send: default state.
        - invalid: sent ecf didn't pass XSD validation.
        - contingency: DGII unreachable by external service. Odoo should send it later
          until delivered accepted state is received.
        - delivered_accepted: expected state that indicate everything is ok with ecf
          issuing.
        - conditionally_accepted: DGII has accepted the ECF but has some remarks
        - delivered_refused: ecf rejected by DGII.
        - not_sent: Odoo have not connection.
        - service_unreachable: external service may be down.
        - signed_pending: ECF was signed but API could not reach DGII. May be resend
          later.

        """
        return [
            ("to_send", _("Not sent")),
            ("invalid", _("Sent, but invalid")),
            ("contingency", _("Contingency")),
            ("delivered_accepted", _("Delivered and accepted")),
            ("conditionally_accepted", _("Conditionally accepted")),
            ("delivered_pending", _("Delivered and pending")),
            ("delivered_refused", _("Delivered and refused")),
            ("not_sent", _("Could not send the e-CF")),
            ("service_unreachable", _("Service unreachable")),
            ("signed_pending", _("Signed and pending")),
        ]

    l10n_do_ecf_send_state = fields.Selection(
        string="e-CF Send State",
        selection="_get_l10n_do_ecf_send_state",
        copy=False,
        index=True,
        readonly=True,
        default="to_send",
        tracking=True,
    )
    l10n_do_ecf_trackid = fields.Char(
        "e-CF Trackid",
        readonly=True,
        copy=False,
    )
    l10n_do_ecf_security_code = fields.Char(
        states={"draft": [("readonly", False)]},
    )
    l10n_do_ecf_sign_date = fields.Datetime(
        readonly=True,
    )
    l10n_do_ecf_expecting_payment = fields.Boolean(
        string="Payment expected to send ECF",
        compute="_compute_l10n_do_ecf_expecting_payment",
    )

    @api.depends("l10n_do_ecf_security_code", "l10n_do_ecf_sign_date", "invoice_date")
    @api.depends_context("l10n_do_ecf_service_env")
    def _compute_l10n_do_electronic_stamp(self):
        return super(
            AccountMove,
            self.with_context(
                l10n_do_ecf_service_env=self.company_id.l10n_do_ecf_service_env
            ),
        )._compute_l10n_do_electronic_stamp()

    def _compute_l10n_do_ecf_expecting_payment(self):
        invoices = self.filtered(lambda i: i.type != "entry" and i.is_ecf_invoice)
        for invoice in invoices:
            invoice.l10n_do_ecf_expecting_payment = bool(
                not invoice._do_immediate_send()
                and invoice.l10n_do_ecf_send_state == "to_send"
                and invoice.state != "draft"
            )
        (self - invoices).l10n_do_ecf_expecting_payment = False

    def is_l10n_do_partner(self):
        return self.partner_id.country_id and self.partner_id.country_id.code == "DO"

    def is_company_currency(self):
        return self.currency_id == self.company_id.currency_id

    def get_l10n_do_ncf_type(self):
        """
        Indicates if the document Code Type:

        31: Factura de Crédito Fiscal Electrónica
        32: Factura de Consumo Electrónica
        33: Nota de Débito Electrónica
        34: Nota de Crédito Electrónica
        41: Compras Electrónico
        43: Gastos Menores Electrónico
        44: Regímenes Especiales Electrónica
        45: Gubernamental Electrónico
        46: Comprobante para Exportaciones Electrónico
        47: Comprobante para Pagos al Exterior Electrónico
        """

        self.ensure_one()
        return self.l10n_latam_document_type_id.doc_code_prefix[1:]

    def get_payment_type(self):
        """
        Indicates the type of customer payment. Free delivery invoices (code 3)
        are not valid for Crédito Fiscal.

        1 - Al Contado
        2 - Crédito
        3 - Gratuito
        """
        self.ensure_one()
        # TODO: evaluate payment type 3 <Gratuito> Check DGII docs
        if not self.invoice_payment_term_id and self.invoice_date_due:
            if (
                self.invoice_date_due and self.invoice_date
            ) and self.invoice_date_due > self.invoice_date:
                return 2
            else:
                return 1
        elif not self.invoice_payment_term_id:
            return 1
        elif not self.invoice_payment_term_id == self.env.ref(
            "account.account_payment_term_immediate"
        ):
            return 2
        else:
            return 1

    def get_payment_forms(self):

        """
        1: Efectivo
        2: Cheque/Transferencia/Depósito
        3: Tarjeta de Débito/Crédito
        4: Venta a Crédito
        5: Bonos o Certificados de regalo
        6: Permuta
        7: Nota de crédito
        8: Otras Formas de pago

        """

        payment_dict = {
            "cash": "01",
            "bank": "02",
            "card": "03",
            "credit": "04",
            "swap": "06",
            "credit_note": "07",
        }

        payments = []

        for payment in self._get_reconciled_info_JSON_values():
            payment_id = self.env["account.payment"].browse(
                payment.get("account_payment_id")
            )

            payment_amount = payment.get("amount", 0)

            # Convert payment amount to company currency if needed
            if payment.get("currency") != self.company_id.currency_id.symbol:
                currency_id = self.env["res.currency"].search(
                    [("symbol", "=", payment.get("currency"))], limit=1
                )
                payment_amount = currency_id._convert(
                    payment_amount,
                    self.currency_id,
                    self.company_id,
                    payment.get("date"),
                )

            move_id = False
            if payment_id:
                if payment_id.journal_id.type in ["cash", "bank"]:
                    payment_form = payment_id.journal_id.l10n_do_payment_form
                    if not payment_form:
                        raise ValidationError(
                            _(
                                "Missing *Payment Form* on %s journal"
                                % payment_id.journal_id.name
                            )
                        )
                    payments.append(
                        {
                            "FormaPago": payment_dict[payment_form],
                            "MontoPago": payment_amount,
                        }
                    )

            elif not payment_id:
                move_id = self.env["account.move"].browse(payment.get("move_id"))
                if move_id:
                    payments.append(
                        {
                            "FormaPago": payment_dict["swap"],
                            "MontoPago": payment_amount,
                        }
                    )
            elif not move_id:
                # If invoice is paid, but the payment doesn't come from
                # a journal, assume it is a credit note
                payments.append(
                    {
                        "FormaPago": payment_dict["credit_note"],
                        "MontoPago": payment_amount,
                    }
                )

        return payments

    def _get_IdDoc_data(self):
        """Document Identification values"""
        self.ensure_one()

        l10n_do_ncf_type = self.get_l10n_do_ncf_type()
        itbis_group = self.env.ref("l10n_do.group_itbis")

        id_doc_data = od(
            {
                "TipoeCF": self.get_l10n_do_ncf_type(),
                "eNCF": self.ref,
            }
        )

        if l10n_do_ncf_type not in ("32", "34") and self.ncf_expiration_date:
            id_doc_data["FechaVencimientoSecuencia"] = dt.strftime(
                self.ncf_expiration_date, "%d-%m-%Y"
            )

        if l10n_do_ncf_type == "34":
            credit_origin_id = self.search(
                [("ref", "=", self.l10n_do_origin_ncf)], limit=1
            )
            delta = abs(self.invoice_date - credit_origin_id.invoice_date)
            id_doc_data["IndicadorNotaCredito"] = int(delta.days > 30)

        if self.company_id.l10n_do_ecf_deferred_submissions:
            id_doc_data["IndicadorEnvioDiferido"] = 1

        if l10n_do_ncf_type not in ("43", "44", "46", "47"):
            if "IndicadorMontoGravado" not in id_doc_data:
                id_doc_data["IndicadorMontoGravado"] = None
            id_doc_data["IndicadorMontoGravado"] = int(
                any(
                    True
                    for t in self.invoice_line_ids.tax_ids.filtered(
                        lambda tax: tax.tax_group_id.id == itbis_group.id
                    )
                    if t.price_include
                )
            )

        if l10n_do_ncf_type not in ("41", "43", "47"):
            if "TipoIngresos" not in id_doc_data:
                id_doc_data["TipoIngresos"] = None
            id_doc_data["TipoIngresos"] = self.l10n_do_income_type

        id_doc_data["TipoPago"] = self.get_payment_type()

        # TODO: actually DGII is not allowing send TablaFormasPago
        # if self.invoice_payment_state != "not_paid" and l10n_do_ncf_type not in (
        #     "34",
        #     "43",
        # ):
        #     id_doc_data["TablaFormasPago"] = {"FormaDePago": self.get_payment_forms()}

        if (
            self.invoice_date_due
            and id_doc_data["TipoPago"] == 2
            and l10n_do_ncf_type != "43"
        ):
            id_doc_data["FechaLimitePago"] = dt.strftime(
                self.invoice_date_due, "%d-%m-%Y"
            )

            if l10n_do_ncf_type not in ("34", "43"):
                delta = self.invoice_date_due - self.invoice_date
                id_doc_data["TerminoPago"] = "%s días" % delta.days

        return id_doc_data

    def _get_Emisor_data(self):
        """Issuer (company) values"""
        self.ensure_one()
        issuer_data = od(
            {
                "RNCEmisor": self.company_id.vat,
                "RazonSocialEmisor": self.company_id.name,
                "NombreComercial": "N/A",
                "Sucursal": "N/A",
                "DireccionEmisor": "",
                "FechaEmision": dt.strftime(self.invoice_date, "%d-%m-%Y"),
            }
        )

        if not self.company_id.street or not len(str(self.company_id.street).strip()):
            action = self.env.ref("base.action_res_company_form")
            msg = _("Cannot send an ECF if company has no address.")
            raise RedirectWarning(msg, action.id, _("Go to Companies"))

        issuer_data["DireccionEmisor"] = self.company_id.street

        return issuer_data

    def _get_Comprador_data(self):
        """Buyer (invoice partner) values """
        self.ensure_one()
        l10n_do_ncf_type = self.get_l10n_do_ncf_type()
        partner_vat = self.partner_id.vat or ""
        is_l10n_do_partner = self.is_l10n_do_partner()

        buyer_data = od({})
        if l10n_do_ncf_type not in ("43", "47"):

            if l10n_do_ncf_type in ("31", "41", "45", "46"):
                buyer_data["RNCComprador"] = partner_vat

            if l10n_do_ncf_type == "32" and partner_vat:
                buyer_data["RNCComprador"] = partner_vat

            if l10n_do_ncf_type in ("33", "34"):
                if (
                    self.debit_origin_id
                    and self.debit_origin_id.get_l10n_do_ncf_type != "32"
                    or (
                        self.debit_origin_id.get_l10n_do_ncf_type == "32"
                        and self.debit_origin_id.amount_total_signed >= 250000
                    )
                    or self.type in ("out_refund", "in_refund")
                ):
                    if is_l10n_do_partner and partner_vat:
                        buyer_data["RNCComprador"] = partner_vat
                    elif partner_vat:
                        buyer_data["IdentificadorExtranjero"] = partner_vat

            if l10n_do_ncf_type == "44":
                if is_l10n_do_partner and partner_vat:
                    buyer_data["RNCComprador"] = partner_vat
                elif not is_l10n_do_partner and partner_vat:
                    buyer_data["IdentificadorExtranjero"] = partner_vat

            if self.company_id.partner_id.l10n_do_dgii_tax_payer_type == "special":
                if is_l10n_do_partner:
                    buyer_data["RNCComprador"] = partner_vat
                else:
                    buyer_data["IdentificadorExtranjero"] = partner_vat

        if l10n_do_ncf_type not in ("31", "41", "43", "45") and not is_l10n_do_partner:

            if l10n_do_ncf_type == "32" and self.amount_total_signed >= 250000:
                buyer_data["IdentificadorExtranjero"] = partner_vat

        if l10n_do_ncf_type not in ("43", "47"):

            # TODO: are those If really needed?
            if l10n_do_ncf_type == "32":
                if self.amount_total_signed >= 250000 or partner_vat:
                    buyer_data["RazonSocialComprador"] = self.commercial_partner_id.name

            if l10n_do_ncf_type in ("33", "34"):
                buyer_data["RazonSocialComprador"] = self.commercial_partner_id.name

            else:  # 31, 41, 44, 45, 46
                buyer_data["RazonSocialComprador"] = self.commercial_partner_id.name

        return buyer_data

    def get_taxed_amount_data(self):
        """ITBIS taxed amount
        According to the DGII, there are three types of
        amounts taxed by ITBIS:

        18% -- Most common
        16% -- Used on 'healthy products' like Yogurt, coffee and so on.
        0% -- Should be used on exported products

        See Law No. 253-12, art. 343 of dominican Tributary Code for further info
        """

        itbis_data = {
            "total_taxed_amount": 0,
            "18_taxed_base": 0,
            "18_taxed_amount": 0,
            "16_taxed_base": 0,
            "16_taxed_amount": 0,
            "0_taxed_base": 0,
            "0_taxed_amount": 0,
            "exempt_amount": 0,
            "itbis_withholding_amount": 0,
            "isr_withholding_amount": 0,
        }

        tax_data = [
            line.tax_ids.compute_all(
                price_unit=line.price_subtotal,
                currency=line.currency_id,
                product=line.product_id,
                partner=line.move_id.partner_id,
                handle_price_include=False,
            )
            for line in self.invoice_line_ids
        ]

        itbis_data["total_taxed_amount"] = sum(
            line["total_excluded"] for line in tax_data
        )
        l10n_do_ncf_type = self.get_l10n_do_ncf_type()

        for line_taxes in tax_data:
            for tax in line_taxes["taxes"]:
                if not tax["amount"] and l10n_do_ncf_type != "46":
                    itbis_data["exempt_amount"] += tax["base"]

                tax_id = self.env["account.tax"].browse(tax["id"])
                if tax_id.amount == 18:
                    itbis_data["18_taxed_base"] += tax["base"]
                    itbis_data["18_taxed_amount"] += tax["amount"]
                elif tax_id.amount == 16:
                    itbis_data["16_taxed_base"] += tax["base"]
                    itbis_data["16_taxed_amount"] += tax["amount"]
                elif tax_id.amount == 0 and l10n_do_ncf_type == "46":
                    itbis_data["0_taxed_base"] += tax["base"]
                    itbis_data["0_taxed_amount"] += tax["amount"]
                elif tax_id.amount < 0 and tax_id.tax_group_id == self.env.ref(
                    "l10n_do.group_itbis"
                ):
                    itbis_data["itbis_withholding_amount"] += tax["amount"]
                elif tax_id.amount < 0 and tax_id.tax_group_id == self.env.ref(
                    "l10n_do.group_isr"
                ):
                    itbis_data["isr_withholding_amount"] += tax["amount"]

        return itbis_data

    def _get_Totales_data(self):
        """Invoice amounts related values"""
        self.ensure_one()

        totals_data = od({})
        tax_data = self.get_taxed_amount_data()
        l10n_do_ncf_type = self.get_l10n_do_ncf_type()
        is_company_currency = self.is_company_currency()

        total_taxed = sum(
            [
                tax_data["18_taxed_base"],
                tax_data["16_taxed_base"],
                tax_data["0_taxed_base"],
            ]
        )
        total_itbis = sum(
            [
                tax_data["18_taxed_amount"],
                tax_data["16_taxed_amount"],
                tax_data["0_taxed_amount"],
            ]
        )

        if l10n_do_ncf_type not in ("43", "44"):
            if total_taxed:
                totals_data["MontoGravadoTotal"] = abs(round(total_taxed, 2))
            if tax_data["18_taxed_base"]:
                totals_data["MontoGravadoI1"] = abs(round(tax_data["18_taxed_base"], 2))
            if tax_data["16_taxed_base"]:
                totals_data["MontoGravadoI2"] = abs(round(tax_data["16_taxed_base"], 2))
            if tax_data["0_taxed_base"]:
                totals_data["MontoGravadoI3"] = abs(round(tax_data["0_taxed_base"], 2))
            if tax_data["exempt_amount"]:
                totals_data["MontoExento"] = abs(round(tax_data["exempt_amount"], 2))

            if tax_data["18_taxed_base"]:
                totals_data["ITBIS1"] = "18"
            if tax_data["16_taxed_base"]:
                totals_data["ITBIS2"] = "16"
            if tax_data["0_taxed_base"]:
                totals_data["ITBIS3"] = "0"
            if total_taxed:
                totals_data["TotalITBIS"] = abs(round(total_itbis, 2))
            if tax_data["18_taxed_base"]:
                totals_data["TotalITBIS1"] = abs(round(tax_data["18_taxed_amount"], 2))
            if tax_data["16_taxed_base"]:
                totals_data["TotalITBIS2"] = abs(round(tax_data["16_taxed_amount"], 2))
            if tax_data["0_taxed_base"]:
                totals_data["TotalITBIS3"] = abs(round(tax_data["0_taxed_amount"], 2))
        else:
            if tax_data["exempt_amount"]:
                totals_data["MontoExento"] = abs(round(tax_data["exempt_amount"], 2))

        if l10n_do_ncf_type not in ("43", "44") and total_taxed:
            totals_data["MontoTotal"] = abs(round(total_taxed + total_itbis, 2))
        else:
            totals_data["MontoTotal"] = abs(round(self.amount_untaxed, 2))

        if l10n_do_ncf_type not in ("43", "44"):
            if tax_data["itbis_withholding_amount"] or l10n_do_ncf_type == "41":
                totals_data["TotalITBISRetenido"] = abs(
                    round(tax_data["itbis_withholding_amount"], 2)
                )
            if tax_data["isr_withholding_amount"]:
                totals_data["TotalISRRetencion"] = abs(
                    round(tax_data["isr_withholding_amount"], 2)
                )

        if not is_company_currency:
            rate = abs(round(1 / (self.amount_total / self.amount_total_signed), 2))
            totals_data = od(
                {
                    f: round(v * rate, 2) if not isinstance(v, str) else v
                    for f, v in totals_data.items()
                }
            )

        return totals_data

    def _get_OtraMoneda_data(self, ecf_object_data):
        """Only used if invoice currency is not company currency"""
        self.ensure_one()
        l10n_do_ncf_type = self.get_l10n_do_ncf_type()
        currency_data = od({})

        currency_data["TipoMoneda"] = self.currency_id.name
        currency_data["TipoCambio"] = abs(
            round(1 / (self.amount_total / self.amount_total_signed), 2)
        )

        rate = currency_data["TipoCambio"]

        if l10n_do_ncf_type not in ("43", "44", "47"):

            if "MontoGravadoTotal" in ecf_object_data["ECF"]["Encabezado"]["Totales"]:
                currency_data["MontoGravadoTotalOtraMoneda"] = round(
                    ecf_object_data["ECF"]["Encabezado"]["Totales"]["MontoGravadoTotal"]
                    / rate,
                    2,
                )

            if "MontoGravadoI1" in ecf_object_data["ECF"]["Encabezado"]["Totales"]:
                currency_data["MontoGravado1OtraMoneda"] = round(
                    ecf_object_data["ECF"]["Encabezado"]["Totales"]["MontoGravadoI1"]
                    / rate,
                    2,
                )

            if "MontoGravadoI2" in ecf_object_data["ECF"]["Encabezado"]["Totales"]:
                currency_data["MontoGravado2OtraMoneda"] = round(
                    ecf_object_data["ECF"]["Encabezado"]["Totales"]["MontoGravadoI2"]
                    / rate,
                    2,
                )

            if "MontoGravadoI3" in ecf_object_data["ECF"]["Encabezado"]["Totales"]:
                currency_data["MontoGravado3OtraMoneda"] = round(
                    ecf_object_data["ECF"]["Encabezado"]["Totales"]["MontoGravadoI3"]
                    / rate,
                    2,
                )

        if (
            "MontoExento" in ecf_object_data["ECF"]["Encabezado"]["Totales"]
            and l10n_do_ncf_type != "46"
        ):
            currency_data["MontoExentoOtraMoneda"] = round(
                ecf_object_data["ECF"]["Encabezado"]["Totales"]["MontoExento"] / rate, 2
            )

        if "MontoGravadoTotal" in ecf_object_data["ECF"]["Encabezado"]["Totales"]:
            currency_data["TotalITBISOtraMoneda"] = round(
                ecf_object_data["ECF"]["Encabezado"]["Totales"]["TotalITBIS"] / rate,
                2,
            )
        if "MontoGravadoI1" in ecf_object_data["ECF"]["Encabezado"]["Totales"]:
            currency_data["TotalITBIS1OtraMoneda"] = round(
                ecf_object_data["ECF"]["Encabezado"]["Totales"]["TotalITBIS1"] / rate,
                2,
            )
        if "MontoGravadoI2" in ecf_object_data["ECF"]["Encabezado"]["Totales"]:
            currency_data["TotalITBIS2OtraMoneda"] = round(
                ecf_object_data["ECF"]["Encabezado"]["Totales"]["TotalITBIS2"] / rate,
                2,
            )
        if "MontoGravadoI3" in ecf_object_data["ECF"]["Encabezado"]["Totales"]:
            currency_data["TotalITBIS3OtraMoneda"] = round(
                ecf_object_data["ECF"]["Encabezado"]["Totales"]["TotalITBIS3"] / rate,
                2,
            )

        currency_data["MontoTotalOtraMoneda"] = abs(
            sum(
                self.line_ids.filtered(lambda aml: aml.exclude_from_invoice_tab).mapped(
                    "amount_currency"
                )
            )
        )

        return currency_data

    def _get_item_withholding_vals(self, invoice_line):
        """ Returns invoice line withholding taxes values """

        line_withholding_vals = invoice_line.tax_ids.compute_all(
            price_unit=invoice_line.price_unit,
            currency=invoice_line.currency_id,
            quantity=invoice_line.quantity,
            product=invoice_line.product_id,
            partner=invoice_line.move_id.partner_id,
            is_refund=True if invoice_line.move_id.type == "in_refund" else False,
        )

        withholding_vals = od()
        itbis_withhold_amount = abs(
            sum(
                tax["amount"]
                for tax in line_withholding_vals["taxes"]
                if tax["amount"] < 0
                and self.env["account.tax"].browse(tax["id"]).tax_group_id
                == self.env.ref("l10n_do.group_itbis")
            )
        )
        isr_withhold_amount = abs(
            sum(
                tax["amount"]
                for tax in line_withholding_vals["taxes"]
                if tax["amount"] < 0
                and self.env["account.tax"].browse(tax["id"]).tax_group_id
                == self.env.ref("l10n_do.group_isr")
            )
        )

        if itbis_withhold_amount or self.get_l10n_do_ncf_type() == "41":
            withholding_vals["MontoITBISRetenido"] = itbis_withhold_amount

        withholding_vals["MontoISRRetenido"] = isr_withhold_amount

        return withholding_vals

    def _get_Item_list(self, ecf_object_data):
        """Product lines related values"""
        self.ensure_one()

        itbis_group = self.env.ref("l10n_do.group_itbis")
        is_company_currency = self.is_company_currency()
        l10n_do_ncf_type = self.get_l10n_do_ncf_type()

        def get_invoicing_indicator(inv_line):
            "IndicadorFacturacion"
            if not inv_line.tax_ids:
                return 4
            tax_set = set(
                tax.amount
                for tax in inv_line.tax_ids
                if tax.tax_group_id.id == itbis_group.id
            )
            if len(tax_set) > 1 or 18 in tax_set:
                return 1
            elif 16 in tax_set:
                return 2
            elif l10n_do_ncf_type == "46" and 0 in tax_set:
                return 3
            else:
                return 4

        lines_data = []

        for i, line in enumerate(
            self.invoice_line_ids.filtered(lambda l: not l.display_type).sorted(
                "sequence"
            ),
            1,
        ):

            rate = 1
            if "OtraMoneda" in ecf_object_data["ECF"]["Encabezado"]:
                rate = ecf_object_data["ECF"]["Encabezado"]["OtraMoneda"]["TipoCambio"]

            line_dict = od()
            product = line.product_id
            product_name = product.name if product else line.name
            line_dict["NumeroLinea"] = i
            line_dict["IndicadorFacturacion"] = get_invoicing_indicator(line)

            if l10n_do_ncf_type in ("41", "47"):
                withholding_vals = od([("IndicadorAgenteRetencionoPercepcion", 1)])
                for k, v in self._get_item_withholding_vals(line).items():
                    withholding_vals[k] = round(
                        v if is_company_currency else v * rate, 2
                    )
                line_dict["Retencion"] = withholding_vals

            # line_dict["NombreItem"] = product.name if product else line.name
            line_dict["NombreItem"] = (
                (product_name[:78] + "..") if len(product_name) > 78 else product_name
            )
            line_dict["IndicadorBienoServicio"] = (
                "2"
                if (product and product.type == "service") or l10n_do_ncf_type == "47"
                else "1"
            )
            line_dict["DescripcionItem"] = line.name
            line_dict["CantidadItem"] = ("%f" % line.quantity).rstrip("0").rstrip(".")

            line_dict["PrecioUnitarioItem"] = abs(
                round(
                    line.price_unit if is_company_currency else line.price_unit * rate,
                    4,
                )
            )

            price_wo_discount = line.quantity * line.price_unit
            price_with_discount = price_wo_discount * (1 - (line.discount / 100.0))
            discount_amount = (
                abs(round(price_with_discount - price_wo_discount, 2))
                if line.discount
                else 0
            )

            currency_discount_amount = discount_amount
            discount_amount = (
                discount_amount
                if is_company_currency
                else round(discount_amount * rate, 2)
            )

            if line.discount:
                line_dict["DescuentoMonto"] = discount_amount
                line_dict["TablaSubDescuento"] = {
                    "SubDescuento": [
                        {
                            "TipoSubDescuento": "%",
                            "SubDescuentoPorcentaje": line.discount,
                            "MontoSubDescuento": discount_amount,
                        }
                    ]
                }

            if not is_company_currency:
                line_dict["OtraMonedaDetalle"] = {
                    "PrecioOtraMoneda": abs(line.price_unit),
                    "DescuentoOtraMoneda": currency_discount_amount,
                    "MontoItemOtraMoneda": abs(round(line.price_subtotal, 2)),
                }

            line_dict["MontoItem"] = abs(
                round(
                    price_with_discount
                    if is_company_currency
                    else price_with_discount * rate,
                    2,
                )
            )

            lines_data.append(line_dict)

        return lines_data

    def _get_InformacionReferencia_data(self, ecf_object_data):
        """Data included Debit/Credit Note"""
        self.ensure_one()
        reference_info_data = od({})

        origin_id = (
            self.search([("ref", "=", self.l10n_do_origin_ncf)], limit=1)
            if self.get_l10n_do_ncf_type() == "34"
            else self.debit_origin_id
        )

        if not origin_id:
            raise ValidationError(_("Could not found origin document."))

        if "InformacionReferencia" not in ecf_object_data["ECF"]:
            ecf_object_data["ECF"]["InformacionReferencia"] = od({})
        reference_info_data["NCFModificado"] = origin_id.ref
        reference_info_data["FechaNCFModificado"] = dt.strftime(
            origin_id.invoice_date, "%d-%m-%Y"
        )
        reference_info_data["CodigoModificacion"] = self.l10n_do_ecf_modification_code

        return reference_info_data

    def _get_invoice_data_object(self):
        """Builds invoice e-CF data object to be send to DGII

        Invoice e-CF data object is composed by the following main parts:

        * Encabezado -- Corresponds to the identification of the e-CF, where it contains
        the issuer, buyer and tax data
        * Detalle de Bienes o Servicios -- In this section one line must be detailed for
        each item
        * Subtotales Informativos -- These subtotals do not increase or decrease the tax
        base, nor do they modify the totalizing fields; they are only informative fields
        * Descuentos o Recargos -- This section is used to specify global discounts or
        surcharges that affect the total e-CF. Item-by-item specification is not
        required
        * Paginación -- This section indicates the number of e-CF pages in the Printed
        Representation and what items will be on each one. This should be repeated for
        the total number of pages specified
        * Información de Referencia -- This section must detail the e-CFs modified by
        Electronic Credit or Debit Note and the eCFs issued due to the replacement of
        a voucher issued in contingency.
        * Fecha y Hora de la firma digital -- Date and Time of the digital signature
        * Firma Digital -- Digital Signature on all the above information to guarantee
        the integrity of the e-CF

        Data order is a key aspect of e-CF issuing. For the sake of this matter,
        OrderedDict objects are used to compose the whole e-CF.

        Eg:

        OrderedDict([('ECF',
        OrderedDict([('Encabezado',
        OrderedDict([('Version', '1.0'),
        ('IdDoc',
        OrderedDict([('TipoeCF', '31'),
                     ('eNCF', 'E310000000007'),
                     ('FechaVencimientoSecuencia', '31-12-2020'),
                     ('IndicadorMontoGravado', 0),
                     ('TipoIngresos', '01'),
                     ('TipoPago', 2),
                     ('FechaLimitePago', '20-06-2020'),
                     ('TerminoPago', '0 días')])),
        ('Emisor',
        OrderedDict([('RNCEmisor', '131793916'),
                     ('RazonSocialEmisor', 'INDEXA SRL'),
                     ('NombreComercial', ''),
                     ('Sucursal', ''),
                     ('DireccionEmisor', 'Calle Rafael Augusto Sánchez 86'),
                     ('FechaEmision', '20-06-2020')])),
        ('Comprador',
        OrderedDict([('RNCComprador', '101654325'),
                     ('RazonSocialComprador', 'CONSORCIO DE TARJETAS DOMINICANAS S A')])),
        ('Totales',
        OrderedDict([('MontoGravadoTotal', 4520.0),
                     ('MontoGravadoI1', 4520.0),
                     ('ITBIS1', '18'),
                     ('TotalITBIS', 813.6),
                     ('TotalITBIS1', 813.6),
                     ('MontoTotal', 10667.2)]))])),
        ('DetallesItems',
        OrderedDict([('Item',
        [OrderedDict([('NumeroLinea', 1),
                    ('IndicadorFacturacion', 1),
                    ('NombreItem', 'Product A'),
                    ('IndicadorBienoServicio', '1'),
                    ('DescripcionItem', 'Product A'),
                    ('CantidadItem', 5.0),
                    ('PrecioUnitarioItem', 800.0),
                    ('MontoItem', 4000.0)])])])),
        ('FechaHoraFirma', '20-06-2020 23:51:44'),
        ('_ANY_', '')]))])

        """
        self.ensure_one()

        l10n_do_ncf_type = self.get_l10n_do_ncf_type()
        is_company_currency = self.is_company_currency()

        # At this point, ecf_object_data only contains required
        # fields in all e-CF's types
        ecf_object_data = od(
            {
                "ECF": od(
                    {
                        "Encabezado": od(
                            {
                                "Version": "1.0",  # is this value going to change anytime?
                                "IdDoc": self._get_IdDoc_data(),
                                "Emisor": self._get_Emisor_data(),
                                "Comprador": self._get_Comprador_data(),
                                "Totales": self._get_Totales_data(),
                            }
                        ),
                        "DetallesItems": od({}),
                        "InformacionReferencia": od({}),
                        # This is a dummy date. The one we use in the digital stamp
                        # is the one received from the external service
                        "FechaHoraFirma": fields.Datetime.context_timestamp(
                            self.with_context(tz="America/Santo_Domingo"),
                            fields.Datetime.now(),
                        ).strftime("%d-%m-%Y %H:%M:%S"),
                    }
                ),
            }
        )

        if l10n_do_ncf_type == "43":
            del ecf_object_data["ECF"]["Encabezado"]["Comprador"]

        if not is_company_currency:
            if "OtraMoneda" not in ecf_object_data["ECF"]["Encabezado"]:
                ecf_object_data["ECF"]["Encabezado"]["OtraMoneda"] = od({})
            ecf_object_data["ECF"]["Encabezado"][
                "OtraMoneda"
            ] = self._get_OtraMoneda_data(ecf_object_data)

        # Invoice lines
        ecf_object_data["ECF"]["DetallesItems"]["Item"] = self._get_Item_list(
            ecf_object_data
        )

        if l10n_do_ncf_type in ("33", "34"):
            ecf_object_data["ECF"][
                "InformacionReferencia"
            ] = self._get_InformacionReferencia_data(ecf_object_data)
        else:
            del ecf_object_data["ECF"]["InformacionReferencia"]

        return ecf_object_data

    def log_error_message(self, body):
        self.ensure_one()

        msg_body = "<ul>"
        try:
            error_message = safe_eval(body)
            for msg in list(error_message.get("messages") or []):
                msg_body += "<li>%s</li>" % msg.get("valor")
        except SyntaxError:
            msg_body += "<li>%s</li>" % body

        msg_body += "</ul>"
        dgii_action = (
            _("rejected")
            if self.l10n_do_ecf_send_state == "delivered_refused"
            else _("Conditionally Accepted")
        )
        refused_msg = _("DGII has %s this ECF. Details:\n") % dgii_action

        refused_msg += msg_body

        # Use sudo to post message because we want user actions
        # separated of ECF messages posts
        self.sudo().message_post(body=refused_msg)

    def _show_service_unreachable_message(self, log_msg=""):
        if log_msg:
            _logger.error("Service Unreachable Error. Details: %s" % log_msg)
        msg = _(
            "ECF %s can not be sent due External Service communication issue. "
            "Try again in while or enable company contingency status" % self.ref
        )
        raise ValidationError(msg)

    def _send_ecf_submit_request(self, ecf_data, api_url):
        self.ensure_one()
        response = requests.post(
            "%s?env=%s" % (api_url, self.company_id.l10n_do_ecf_service_env),
            files={"data": json.dumps(ecf_data)},
        )

        try:
            vals = safe_eval(str(response.text).replace("null", "None"))
        except (
            ValueError,
            TypeError,
            SyntaxError,
        ):  # could not parse a dict from response text
            vals = {}

        return response, vals

    def send_ecf_data(self):

        for invoice in self:

            if invoice.l10n_do_ecf_send_state in (
                "delivered_accepted",
                "conditionally_accepted",
            ):
                raise ValidationError(_("Resend a Delivered e-CF is not allowed."))

            ecf_data = invoice._get_invoice_data_object()

            l10n_do_ncf_type = invoice.get_l10n_do_ncf_type()
            if l10n_do_ncf_type == "47":
                del ecf_data["ECF"]["Encabezado"]["Comprador"]

            try:
                _logger.info(json.dumps(ecf_data, indent=4, default=str))
                response, vals = invoice._send_ecf_submit_request(
                    ecf_data,
                    self.env["ir.config_parameter"].sudo().get_param("ecf.api.url"),
                )

                status = vals.get("status", False)
                response_text = str(response.text).replace("null", "None")

                if response.status_code == 200 or status:

                    ecf_xml = b""
                    if "xml" in vals:
                        ecf_xml += str(vals["xml"]).encode("utf-8")

                    if status in ECF_STATE_MAP:
                        status = status.replace(" ", "")
                        sign_datetime = vals.get("signature_datetime", False)
                        try:
                            strp_sign_datetime = dt.strptime(
                                sign_datetime, "%Y-%m-%d %H:%M:%S"
                            )
                        except (TypeError, ValueError):
                            strp_sign_datetime = False

                        invoice_vals = {}
                        if invoice.l10n_do_ecf_send_state != "signed_pending":
                            # Signed and pending invoices already have trackid,
                            # security_code and sign_date. Do not overwrite it.
                            invoice_vals.update(
                                {
                                    "l10n_do_ecf_trackid": vals.get("trackId"),
                                    "l10n_do_ecf_security_code": vals.get(
                                        "security_code"
                                    ),
                                    "l10n_do_ecf_sign_date": strp_sign_datetime,
                                    "l10n_do_ecf_edi_file_name": "%s.xml" % invoice.ref,
                                    "l10n_do_ecf_edi_file": base64.b64encode(ecf_xml),
                                }
                            )

                        invoice_vals["l10n_do_ecf_send_state"] = ECF_STATE_MAP[status]
                        invoice.write(invoice_vals)

                        if status in ("AceptadoCondicional", "Rechazado"):
                            invoice.log_error_message(response_text)
                            if status == "Rechazado":
                                invoice.with_context(
                                    cancelled_by_dgii=True
                                ).button_cancel()

                    else:
                        raise ValidationError(
                            _(
                                "There was an unexpected error message from DGII.\n"
                                "Status: %s\n"
                                "Message: %s"
                            )
                            % (status, response_text)
                        )

                elif response.status_code == 408:  # API could not reach DGII
                    invoice.l10n_do_ecf_send_state = "signed_pending"

                elif response.status_code == 400:  # XSD validation failed
                    msg_body = _("External Service XSD Validation Error:\n\n")
                    error_message = safe_eval(response_text)
                    for msg in list(error_message.get("messages") or []):
                        msg_body += "%s\n" % msg
                    raise ValidationError(msg_body)

                else:  # anything else will be treated as a communication issue

                    log_msg = ""
                    if response:
                        log_msg += "status_code: %s " % response.status_code
                    if response_text:
                        log_msg += "message: %s" % response_text

                    invoice._show_service_unreachable_message(log_msg)

            except requests.exceptions.MissingSchema:
                raise ValidationError(_("Wrong external service URL"))

            except requests.exceptions.ConnectionError:
                # Odoo could not send the request
                invoice.l10n_do_ecf_send_state = "not_sent"

        return True

    def update_ecf_status(self):
        """
        Invoices ecf send status may be pending after first send.
        This function re-check its status and update if needed.
        """
        for invoice in self:

            trackid = invoice.l10n_do_ecf_trackid
            api_url = (
                self.env["ir.config_parameter"].sudo().get_param("ecf.result.api.url")
            )

            try:
                response = requests.post(
                    "%s?env=%s" % (api_url, invoice.company_id.l10n_do_ecf_service_env),
                    json={"trackId": trackid},
                )
                response_text = str(response.text).replace("null", "None")

                try:
                    vals = safe_eval(response_text)
                    status = vals.get("estado", "EnProceso").replace(" ", "")
                    if status in ECF_STATE_MAP:
                        invoice.l10n_do_ecf_send_state = ECF_STATE_MAP[status]
                        if ECF_STATE_MAP[status] in (
                            "delivered_refused",
                            "conditionally_accepted",
                        ):
                            invoice.log_error_message(response_text)
                            if ECF_STATE_MAP[status] == "delivered_refused":
                                invoice.with_context(
                                    cancelled_by_dgii=True
                                ).button_cancel()
                    else:
                        continue

                except (ValueError, TypeError, SyntaxError):
                    continue

            except requests.exceptions.ConnectionError:
                continue

    @api.model
    def check_pending_ecf(self):
        """
        This function is meant to be called from ir.cron. It will update pending ecf
        status.
        """

        pending_invoices = self.search(
            [
                ("type", "in", ("out_invoice", "out_refund", "in_invoice")),
                (
                    "l10n_do_ecf_send_state",
                    "in",
                    ("delivered_pending", "signed_pending"),
                ),
                ("l10n_do_ecf_trackid", "!=", False),
            ]
        )
        pending_invoices.update_ecf_status()

    def _do_immediate_send(self):
        self.ensure_one()

        # Invoices which will receive immediate full or partial payment based on
        # payment terms won't be sent until payment is applied.
        # Note: E41 invoices will be never sent on post. These are sent on payment
        # because this type of ECF must have withholding data included.
        if (
            self.get_l10n_do_ncf_type() == "41"
            or self.company_id.l10n_do_send_ecf_on_payment
            and (
                not self.invoice_payment_term_id
                or self.invoice_payment_term_id
                == self.env.ref("account.account_payment_term_immediate")
                or self.invoice_payment_term_id.line_ids.filtered(
                    lambda line: not line.days
                )
            )
        ):
            return False

        return True

    @api.depends(
        "line_ids.debit",
        "line_ids.credit",
        "line_ids.currency_id",
        "line_ids.amount_currency",
        "line_ids.amount_residual",
        "line_ids.amount_residual_currency",
        "line_ids.payment_id.state",
        "l10n_do_ecf_send_state",
    )
    def _compute_amount(self):
        super(AccountMove, self)._compute_amount()
        fiscal_invoices = self.filtered(
            lambda i: i.is_l10n_do_internal_sequence
            and i.is_ecf_invoice
            and i.l10n_do_ecf_send_state
            not in ("delivered_accepted", "conditionally_accepted", "delivered_pending")
            and i.invoice_payment_state != "not_paid"
        )
        fiscal_invoices.send_ecf_data()

    def l10n_do_ecf_unreconcile_payments(self):
        self.ensure_one()
        for payment_info in self._get_reconciled_info_JSON_values():
            move_lines = self.env["account.move.line"]
            if payment_info["account_payment_id"]:
                move_lines += (
                    self.env["account.payment"]
                    .browse(payment_info["account_payment_id"])
                    .move_line_ids
                )
            else:
                move_lines += (
                    self.env["account.move"].browse(payment_info["payment_id"]).line_ids
                )
            move_lines.with_context(move_id=self.id).remove_move_reconcile()
            self._compute_amount()  # recompute invoice_payment_state

    def button_cancel(self):

        for inv in self.filtered(
            lambda i: i.is_ecf_invoice
            and i.is_l10n_do_internal_sequence
            and i.l10n_do_ecf_send_state not in ("not_sent", "to_send")
        ):
            if not self._context.get("cancelled_by_dgii", False):
                raise UserError(_("Error. Only DGII can cancel an Electronic Invoice"))

            if inv.l10n_do_ecf_send_state == "delivered_refused":
                # Because ECF's are automatically cancelled when DGII refuse them,
                # undo payments reconcile before cancelling
                inv.l10n_do_ecf_unreconcile_payments()

        return super(AccountMove, self).button_cancel()

    def button_draft(self):
        if self.filtered(
            lambda i: i.is_ecf_invoice
            and i.is_l10n_do_internal_sequence
            and i.l10n_do_ecf_send_state not in ("not_sent", "to_send")
        ) and not self._context.get("cancelled_by_dgii", False):
            raise UserError(
                _("Error. A sent Electronic Invoice cannot be set to Draft")
            )
        return super(AccountMove, self).button_draft()

    def post(self):

        res = super(AccountMove, self).post()

        fiscal_invoices = self.filtered(
            lambda i: i.is_l10n_do_internal_sequence
            and i.is_ecf_invoice
            and i.l10n_do_ecf_send_state
            not in (
                "delivered_accepted",
                "conditionally_accepted",
                "delivered_pending",
                "signed_pending",
            )
            and i._do_immediate_send()
        )
        fiscal_invoices.send_ecf_data()
        fiscal_invoices._compute_l10n_do_electronic_stamp()

        return res
