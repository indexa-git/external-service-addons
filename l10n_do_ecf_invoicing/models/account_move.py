#  Copyright (c) 2020 - Indexa SRL. (https://www.indexa.do) <info@indexa.do>
#  See LICENSE file for full licensing details.

import ast
import requests
from datetime import datetime as dt
from collections import OrderedDict as od

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class AccountMove(models.Model):
    _inherit = "account.move"

    def _get_l10n_do_ecf_send_state(self):
        """Returns actual invoice ECF sending status

        - to_send: default state.
        - invalid: sent ecf didn't pass XSD validation.
        - contingency: DGII unreachable by external service. Odoo should send it
        later until delivered accepted state is received.
        - delivered_accepted: expected state that indicate everything is ok with ecf
        issuing.
        - delivered_refused: ecf rejected by DGII.
        - not_sent: Odoo have not connection.
        - service_unreachable: external service may be down.

        """
        return [
            ("to_send", _("Not sent")),
            ("invalid", _("Sent, but invalid")),
            ("contingency", _("Contingency")),
            ("delivered_accepted", _("Delivered and accepted")),
            ("delivered_pending", _("Delivered and pending")),
            ("delivered_refused", _("Delivered and refused")),
            ("not_sent", _("Could not send the e-CF")),
            ("service_unreachable", _("Service unreachable")),
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
    l10n_do_ecf_trackid = fields.Char("e-CF Trackid", readonly=True, copy=False,)
    l10n_do_ecf_security_code = fields.Char(readonly=True,)
    l10n_do_ecf_sign_date = fields.Datetime(readonly=True,)

    def get_itbis_tax_group(self):
        return self.env.ref("l10n_do.group_itbis")

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
            return 2
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

        NOT YET IMPLEMENTED

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
                currency_id = self.env["res.currency"].search([
                    ('symbol', '=', payment.get("currency"))], limit=1)
                payment_amount = currency_id._convert(
                    payment_amount,
                    self.currency_id,
                    self.company_id,
                    payment.get("date")
                )

            move_id = False
            if payment_id:
                if payment_id.journal_id.type in ["cash", "bank"]:
                    payment_form = payment_id.journal_id.l10n_do_payment_form
                    if not payment_form:
                        raise ValidationError(
                            _("Missing *Payment Form* on %s journal" %
                              payment_id.journal_id.name))
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
        itbis_group = self.get_itbis_tax_group()

        id_doc_data = od(
            {
                "TipoeCF": self.get_l10n_do_ncf_type(),
                "eNCF": self.ref,
                "FechaVencimientoSecuencia": "31-12-2020",  # TODO: get this from ncf_expiration_date
                "IndicadorMontoGravado": None,
                "TipoIngresos": self.l10n_do_income_type,
                "TipoPago": self.get_payment_type(),
            }
        )

        if self.invoice_payment_state != "not_paid":
            id_doc_data["TablaFormasPago"] = {"FormaDePago": self.get_payment_forms()}
        else:
            id_doc_data["TipoPago"] = 2

        if l10n_do_ncf_type in ("32", "34"):
            del id_doc_data["FechaVencimientoSecuencia"]

        if l10n_do_ncf_type == "34":
            delta = self.debit_origin_id.invoice_date - fields.Date.context_today(self)
            id_doc_data["IndicadorNotaCredito"] = int(delta.days > 30)

        if self.company_id.l10n_do_ecf_deferred_submissions:
            id_doc_data["IndicadorEnvioDiferido"] = 1

        if l10n_do_ncf_type not in ("43", "44", "46"):
            id_doc_data["IndicadorMontoGravado"] = int(
                any(
                    True
                    for t in self.invoice_line_ids.tax_ids.filtered(
                        lambda tax: tax.tax_group_id.id == itbis_group.id
                    )
                    if t.price_include
                )
            )
        else:
            del id_doc_data["IndicadorMontoGravado"]

        if l10n_do_ncf_type not in ("41", "43", "47"):
            id_doc_data["TipoIngresos"] = self.l10n_do_income_type
        else:
            del id_doc_data["TipoIngresos"]

        if id_doc_data["TipoPago"] == 2:
            id_doc_data["FechaLimitePago"] = dt.strftime(
                self.invoice_date_due, "%d-%m-%Y"
            )

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
                "NombreComercial": "",
                "Sucursal": "",
                "DireccionEmisor": "",
                "FechaEmision": dt.strftime(self.invoice_date, "%d-%m-%Y"),
            }
        )

        if self.company_id.street:
            issuer_data["DireccionEmisor"] = self.company_id.street

        return issuer_data

    def _get_Comprador_data(self):
        """Buyer (invoice partner) values """
        self.ensure_one()
        l10n_do_ncf_type = self.get_l10n_do_ncf_type()
        partner_vat = self.partner_id.vat
        is_l10n_do_partner = self.is_l10n_do_partner()

        buyer_data = od({})
        if l10n_do_ncf_type not in ("43", "47"):

            if l10n_do_ncf_type in ("31", "41", "45"):
                buyer_data["RNCComprador"] = partner_vat

            if l10n_do_ncf_type == "32" or partner_vat:
                buyer_data["RNCComprador"] = partner_vat

            if l10n_do_ncf_type in ("33", "34"):
                if (
                    self.debit_origin_id
                    and self.debit_origin_id.amount_total_signed >= 250000
                ):
                    if is_l10n_do_partner:
                        buyer_data["RNCComprador"] = partner_vat
                    else:
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
                    buyer_data["RazonSocialComprador"] = self.partner_id.name

            if l10n_do_ncf_type in ("33", "34"):
                if (
                    self.debit_origin_id
                    and self.debit_origin_id.amount_total_signed >= 250000
                ):
                    buyer_data["RazonSocialComprador"] = self.partner_id.name

            else:  # 31, 41, 44, 45, 46
                buyer_data["RazonSocialComprador"] = self.partner_id.name

        return buyer_data

    def get_taxed_amount_data(self):
        """ITBIS taxed amount
        :param tax_rate: Intenger. According to the DGII, there are three types of
        amounts taxed by ITBIS:

        18% -- Most common
        16% -- Used on 'healthy products' like Yogurt, coffee and so on.
        0% -- Should be used on exported products

        See Law No. 253-12, art. 343 of dominican Tributary Code for further info
        """

        itbis_group = self.get_itbis_tax_group()
        itbis_data = {}
        itbis_taxed_lines = self.invoice_line_ids.filtered(
            lambda l: itbis_group.id in l.tax_ids.mapped("tax_group_id").ids
        )
        for line in itbis_taxed_lines:
            for tax in line.tax_ids.filtered(lambda t: t.tax_group_id == itbis_group):
                line_itbis_data = tax.compute_all(
                    line.price_unit, quantity=line.quantity
                )
                if tax.amount not in itbis_data:
                    itbis_data[tax.amount] = {
                        "base": sum([t["base"] for t in line_itbis_data["taxes"]]),
                        "amount": sum([t["amount"] for t in line_itbis_data["taxes"]]),
                    }
                else:
                    itbis_data[tax.amount]["base"] += sum(
                        [t["base"] for t in line_itbis_data["taxes"]]
                    )
                    itbis_data[tax.amount]["amount"] += sum(
                        [t["amount"] for t in line_itbis_data["taxes"]]
                    )

        return itbis_data

    def _get_Totales_data(self):
        """Invoice amounts related values"""
        self.ensure_one()
        l10n_do_ncf_type = self.get_l10n_do_ncf_type()

        totals_data = od({})

        if l10n_do_ncf_type not in ("43", "44", "47") and self.amount_tax_signed:

            tax_data = self.get_taxed_amount_data()

            # Montos gravados con 18%, 16% y 0% de ITBIS
            taxed_amount_1 = tax_data.get(18, {}).get("base", 0)
            taxed_amount_2 = tax_data.get(16, {}).get("base", 0)
            taxed_amount_3 = tax_data.get(0, {}).get("base", 0)
            exempt_amount = sum(
                line.credit
                for line in self.line_ids.filtered(
                    lambda l: l.product_id
                    and (not l.tax_ids or (l.tax_line_id and not l.tax_line_id.amount))
                )
            )

            itbis1_total = tax_data.get(18, {}).get("amount", 0)
            itbis2_total = tax_data.get(16, {}).get("amount", 0)
            itbis3_total = tax_data.get(0, {}).get("amount", 0)

            total_taxed = sum([taxed_amount_1, taxed_amount_2, taxed_amount_3])
            total_itbis = sum([itbis1_total, itbis2_total, itbis3_total])

            if total_taxed:
                totals_data["MontoGravadoTotal"] = abs(round(total_taxed, 2))
            if taxed_amount_1:
                totals_data["MontoGravadoI1"] = abs(round(taxed_amount_1, 2))
            if taxed_amount_2:
                totals_data["MontoGravadoI2"] = abs(round(taxed_amount_2, 2))
            if taxed_amount_3:
                totals_data["MontoGravadoI3"] = abs(round(taxed_amount_3, 2))
            if exempt_amount:
                totals_data["MontoExento"] = abs(round(exempt_amount, 2))

            if taxed_amount_1:
                totals_data["ITBIS1"] = "18"
            if taxed_amount_2:
                totals_data["ITBIS2"] = "16"
            if taxed_amount_3:
                totals_data["ITBIS3"] = "0%"  # do not touch the '%'

            if total_taxed:
                totals_data["TotalITBIS"] = abs(round(total_itbis, 2))
            if taxed_amount_1:
                totals_data["TotalITBIS1"] = abs(round(itbis1_total, 2))
            if taxed_amount_2:
                totals_data["TotalITBIS2"] = abs(round(itbis2_total, 2))
            if taxed_amount_3:
                totals_data["TotalITBIS3"] = abs(round(itbis3_total, 2))

            totals_data["MontoTotal"] = abs(round(self.amount_total_signed, 2))

        # TODO: implement TotalITBISRetenido and TotalISRRetencion of Totales section

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

        currency_data["MontoTotalOtraMoneda"] = self.amount_total

        rate = currency_data["TipoCambio"]

        if l10n_do_ncf_type not in ("43", "44", "47"):

            if "MontoGravadoTotal" in ecf_object_data["ECF"]["Encabezado"]["Totales"]:
                currency_data["MontoGravadoTotalOtraMoneda"] = round(
                    ecf_object_data["ECF"]["Encabezado"]["Totales"]["MontoGravadoTotal"]
                    / rate,
                    2,
                )
                currency_data["TotalITBISOtraMoneda"] = round(
                    ecf_object_data["ECF"]["Encabezado"]["Totales"]["TotalITBIS"]
                    / rate,
                    2,
                )

            if "MontoGravadoI1" in ecf_object_data["ECF"]["Encabezado"]["Totales"]:
                currency_data["MontoGravado1OtraMoneda"] = round(
                    ecf_object_data["ECF"]["Encabezado"]["Totales"]["MontoGravadoI1"]
                    / rate,
                    2,
                )
                currency_data["TotalITBIS1OtraMoneda"] = round(
                    ecf_object_data["ECF"]["Encabezado"]["Totales"]["TotalITBIS1"]
                    / rate,
                    2,
                )

            if "MontoGravadoI2" in ecf_object_data["ECF"]["Encabezado"]["Totales"]:
                currency_data["MontoGravado2OtraMoneda"] = round(
                    ecf_object_data["ECF"]["Encabezado"]["Totales"]["MontoGravadoI2"]
                    / rate,
                    2,
                )
                currency_data["TotalITBIS2OtraMoneda"] = round(
                    ecf_object_data["ECF"]["Encabezado"]["Totales"]["TotalITBIS2"]
                    / rate,
                    2,
                )

            if "MontoGravadoI3" in ecf_object_data["ECF"]["Encabezado"]["Totales"]:
                currency_data["MontoGravado3OtraMoneda"] = round(
                    ecf_object_data["ECF"]["Encabezado"]["Totales"]["MontoGravadoI3"]
                    / rate,
                    2,
                )
                currency_data["TotalITBIS3OtraMoneda"] = round(
                    ecf_object_data["ECF"]["Encabezado"]["Totales"]["TotalITBIS3"]
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

    def _get_Item_list(self, ecf_object_data):
        """Product lines related values"""
        self.ensure_one()

        itbis_group = self.get_itbis_tax_group()
        is_company_currency = self.is_company_currency()

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
            elif 0 in tax_set:
                return 4
            else:
                return 3

        lines_data = []

        for i, line in enumerate(self.invoice_line_ids.sorted("sequence"), 1):

            rate = 1
            if "OtraMoneda" in ecf_object_data["ECF"]["Encabezado"]:
                rate = ecf_object_data["ECF"]["Encabezado"]["OtraMoneda"]["TipoCambio"]

            line_dict = od()
            product = line.product_id
            line_dict["NumeroLinea"] = i
            line_dict["IndicadorFacturacion"] = get_invoicing_indicator(line)
            line_dict["NombreItem"] = product.name if product else line.name
            line_dict["IndicadorBienoServicio"] = (
                "2" if product and product.type == "service" else "1"
            )
            line_dict["DescripcionItem"] = line.name
            line_dict["CantidadItem"] = line.quantity

            line_dict["PrecioUnitarioItem"] = abs(
                line.price_unit
                if is_company_currency
                else round(line.price_unit / rate, 2)
            )

            price_unit_wo_discount = line.price_unit * (1 - (line.discount / 100.0))
            discount_amount = abs(
                round(price_unit_wo_discount - line.price_subtotal, 2)
            )
            if line.discount:
                line_dict["TablaSubDescuento"] = {
                    "SubDescuento": [
                        {
                            "TipoSubDescuento": "%",
                            "SubDescuentoPorcentaje": line.discount,
                            "MontoSubDescuento": discount_amount
                            if is_company_currency
                            else round(discount_amount / rate, 2),
                        }
                    ]
                }
                line_dict["DescuentoMonto"] = sum(
                    d["MontoSubDescuento"]
                    for d in line_dict["TablaSubDescuento"]["SubDescuento"]
                )

            if not is_company_currency:
                line_dict["OtraMonedaDetalle"] = {
                    "PrecioOtraMoneda": abs(line.price_unit),
                    "DescuentoOtraMoneda": discount_amount,
                    "MontoItemOtraMoneda": abs(round(line.price_subtotal, 2)),
                }

            line_dict["MontoItem"] = abs(
                round(
                    line.price_subtotal
                    if is_company_currency
                    else line.price_subtotal / rate,
                    2,
                )
            )

            lines_data.append(line_dict)

        return lines_data

    def _get_InformacionReferencia_data(self, ecf_object_data):
        """Data included Debit/Credit Note"""
        self.ensure_one()
        reference_info_data = od({})

        if "InformacionReferencia" not in ecf_object_data["ECF"]:
            ecf_object_data["ECF"]["InformacionReferencia"] = od({})
        reference_info_data["NCFModificado"] = self.debit_origin_id.ref
        reference_info_data["FechaNCFModificado"] = dt.strftime(
            self.debit_origin_id.invoice_date, "%d-%m-%Y"
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
                        # This is a dummy date. The one we use in the digital stamp
                        # is the one received from the external service
                        "FechaHoraFirma": dt.strftime(dt.today(), "%d-%m-%Y %H:%M:%S"),
                        "_ANY_": "",
                    }
                ),
            }
        )

        if not is_company_currency:
            if "OtraMoneda" not in ecf_object_data["ECF"]["Encabezado"]:
                ecf_object_data["ECF"]["Encabezado"]["OtraMoneda"] = od({})
            ecf_object_data["ECF"]["Encabezado"][
                "OtraMoneda"] = self._get_OtraMoneda_data(ecf_object_data)

        # Invoice lines
        ecf_object_data["ECF"]["DetallesItems"]["Item"] = self._get_Item_list(
            ecf_object_data
        )

        if l10n_do_ncf_type in ("33", "34"):
            ecf_object_data["ECF"][
                "InformacionReferencia"
            ] = self._get_InformacionReferencia_data(ecf_object_data)

        return ecf_object_data

    def log_error_message(self, body, sent_data):

        msg_body = "<ul>"
        try:
            error_message = ast.literal_eval(body)
            for msg in list(error_message.get("messages") or []):
                msg_body += "<li>%s</li>" % msg
        except SyntaxError:
            msg_body += "<li>%s</li>" % body

        msg_body += "</ul>"
        msg_body += "<p>%s</p>" % sent_data
        self.env["mail.message"].sudo().create(
            {
                "record_name": self.ref,
                "subject": _("e-CF Sending Error"),
                "body": msg_body,
            }
        )

    def send_ecf_data(self):
        for invoice in self:

            if invoice.l10n_do_ecf_send_state == "delivered_accepted":
                raise ValidationError(
                    _("Resend a Delivered and Accepted e-CF is not " "allowed.")
                )

            ecf_data = invoice._get_invoice_data_object()
            api_url = self.env["ir.config_parameter"].sudo().get_param("ecf.api.url")
            try:
                response = requests.post(api_url, json=ecf_data)

                if response.status_code == 400:  # XSD validation failed
                    self.log_error_message(response.text, ecf_data)
                    invoice.l10n_do_ecf_send_state = "invalid"

                elif response.status_code == 200:

                    # DGII return a 'null' as an empty message value. We convert it to
                    # its python similar: None
                    response_text = str(response.text).replace("null", "None")

                    vals = ast.literal_eval(response_text)
                    status = vals.get("status", False)

                    if status:

                        sign_datetime = vals.get("signature_datetime", False)
                        try:
                            strp_sign_datetime = dt.strptime(
                                sign_datetime, "%Y-%m-%d %H:%M:%S"
                            )
                        except (TypeError, ValueError):
                            strp_sign_datetime = False

                        vals = {}
                        if invoice.l10n_do_ecf_send_state != "contingency":
                            # Contingency invoices already have trackid,
                            # security_code and sign_date. Do not overwrite it.
                            vals.update({
                                "l10n_do_ecf_trackid": vals.get("trackId"),
                                "l10n_do_ecf_security_code": vals.get("security_code"),
                                "l10n_do_ecf_sign_date": strp_sign_datetime,
                            })

                        if status == "Aceptado":  # everything is ok with e-cf
                            vals["l10n_do_ecf_send_state"] = "delivered_accepted"

                        elif status == "AceptadoCondicional":
                            # accepted but should be improved
                            vals["l10n_do_ecf_send_state"] = "delivered_accepted"
                            self.log_error_message(response_text, ecf_data)

                        elif status == "EnProceso":
                            # DGII still validating e-cf. Status must be re-checked
                            # again later
                            vals["l10n_do_ecf_send_state"] = "delivered_pending"

                        else:  # status == Rechazado. Rejected by DGII
                            invoice.l10n_do_ecf_send_state = "delivered_refused"
                            self.log_error_message(response_text, ecf_data)

                        if status != "Rechazado":
                            invoice.write(vals)

                elif response.status_code == 402:  # DGII is fucked up
                    invoice.l10n_do_ecf_send_state = "contingency"

                else:  # anything else will be treated as a communication issue
                    invoice.l10n_do_ecf_send_state = "service_unreachable"

            except requests.exceptions.ConnectionError:
                # Odoo could not send the request
                invoice.l10n_do_ecf_send_state = "not_sent"

        return True

    def _check_ecf_status(self):
        """
        Invoices ecf send status may be pending after first send. This function re-check
        its status and update if needed.
        """
        self.ensure_one()
        # TODO: implement feature
        return

    @api.model
    def resend_contingency_ecf(self):
        """
        This function is meant to be called from ir.cron. It will resend all
        contingency invoices
        """

        contingency_invoices = self.search([
            ('type', 'in', ('out_invoice', 'out_refund', 'in_invoice')),
            ('l10n_do_ecf_send_state', '=', 'contingency'),
        ])
        contingency_invoices.send_ecf_data()

    def _do_immediate_send(self):
        self.ensure_one()

        # Invoices which will receive immediate full or partial payment based on
        # payment terms won't be sent until payment is applied.
        if not self.invoice_payment_term_id or \
                self.invoice_payment_term_id == self.env.ref(
                "account.account_payment_term_immediate") or \
                self.invoice_payment_term_id.line_ids.filtered(lambda line: line.days):
            return False

        return True

    def post(self):

        res = super(AccountMove, self).post()

        fiscal_invoices = self.filtered(
            lambda i: i.is_ecf_invoice
            and i.l10n_do_ecf_send_state not in ("delivered_accepted", "delivered_pending")
            and i._do_immediate_send()
        )
        fiscal_invoices.send_ecf_data()

        return res
