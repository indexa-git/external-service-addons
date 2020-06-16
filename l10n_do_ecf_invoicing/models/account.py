#  Copyright (c) 2020 - Indexa SRL. (https://www.indexa.do) <info@indexa.do>
#  See LICENSE file for full licensing details.

import requests
from collections import OrderedDict as od
from datetime import datetime as dt

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class AccountMove(models.Model):
    _inherit = "account.move"

    def _get_l10n_do_ecf_send_state(self):
        return [
            ("to_send", _("Not send")),
            ("invalid", _("Sent, but invalid")),  # no pasó validacion xsd
            ("delivered_accepted", _("Delivered and accepted")),  # to' ta bien
            ("delivered_refused", _("Delivered and refused")),  # rechazado por dgii
            ("not_sent", _("Could not send the e-CF")),  #  request no pudo salir de odoo
            ("service_unreachable", _("Service unreachable")),  # no se pudo comunicar con api
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

        itbis_group = self.env.ref("l10n_do.group_itbis")

        def get_taxed_amount(inv, tax_rate):  # Monto gravado

            return sum(((line.credit+line.debit)/2) for line in inv.invoice_line_ids if any(
                True for tax in line.tax_ids if tax.tax_group_id.id == itbis_group.id
                and tax.amount == tax_rate))

        def get_tax_amount(inv, tax_rate):  # Monto del impuesto

            return sum(((line.credit+line.debit)/2) for line in self.line_ids.filtered(
                lambda l: l.tax_line_id and l.tax_line_id.tax_group_id.id ==
                          itbis_group.id and l.tax_line_id.amount == tax_rate))

        def get_invoicing_indicator(inv_line):
            "IndicadorFacturacion"
            if not inv_line.tax_ids:
                return 4
            tax_set = set(tax.amount for tax in inv_line.tax_ids
                          if tax.tax_group_id.id == itbis_group.id)
            if len(tax_set) > 1 or 18 in tax_set:
                return 1
            elif 16 in tax_set:
                return 2
            elif 0 in tax_set:
                return 4
            else:
                return 3

        l10n_do_ncf_type = self.l10n_latam_document_type_id.doc_code_prefix[1:]
        is_l10n_do_partner = self.partner_id.country_id and \
                             self.partner_id.country_id.code == "DO"
        partner_vat = self.partner_id.vat
        is_company_currency = self.currency_id == self.company_id.currency_id

        # At this point, json only contains required
        # fields in all e-CF's types
        ecf_json = od({
            "ECF": od({
                "Encabezado": od({
                    "Version": "1.0",  # TODO: is this value going to change anytime?
                    "IdDoc": od({
                        "TipoeCF": l10n_do_ncf_type,
                        "eNCF": self.ref,
                        "FechaVencimientoSecuencia": "31-12-2020",
                        "IndicadorMontoGravado": None,
                        "TipoIngresos": "01",
                        "TipoPago": get_payment_type(self),
                    }),
                    "Emisor": od({
                        "RNCEmisor": self.company_id.vat,
                        "RazonSocialEmisor": self.company_id.name,
                        "NombreComercial": "",
                        "Sucursal": "",
                        "DireccionEmisor": "",
                        "FechaEmision": dt.strftime(self.invoice_date, "%d-%m-%Y"),
                    }),
                    "Comprador": od({}),
                    "Totales": od({}),
                }),
                "DetallesItems": od({
                    "Item": []
                    # Items data would be added later
                }),
                "FechaHoraFirma": dt.strftime(dt.today(), "%d-%m-%Y %H:%M:%S"),
                "_ANY_": "",
            }),
        })

        if self.company_id.street:
            ecf_json["ECF"]["Encabezado"]["Emisor"][
                "DireccionEmisor"] = self.company_id.street

        if self.invoice_payment_state != "not_paid":
            ecf_json["ECF"]["Encabezado"]["IdDoc"]["TablaFormasPago"] = {
                "FormaDePago": get_payment_forms(self)}

        if l10n_do_ncf_type in ("32", "34"):
            # TODO: pending
            del ecf_json["ECF"]["Encabezado"]["IdDoc"]["FechaVencimientoSecuencia"]

        if l10n_do_ncf_type == "34":
            origin_move_id = self.search(
                [('ref', '=', self.l10n_do_origin_ncf)])
            delta = origin_move_id.invoice_date - fields.Date.context_today(self)
            ecf_json["ECF"]["Encabezado"]["IdDoc"][
                "IndicadorNotaCredito"] = int(delta.days > 30)

        if self.company_id.l10n_do_ecf_deferred_submissions:
            ecf_json["ECF"]["Encabezado"]["IdDoc"]["IndicadorEnvioDiferido"] = 1

        if l10n_do_ncf_type not in ("43", "44", "46"):
            ecf_json["ECF"]["Encabezado"]["IdDoc"]["IndicadorMontoGravado"] = int(
                any(True for t in self.invoice_line_ids.tax_ids if t.price_include))
        else:
            del ecf_json["ECF"]["Encabezado"]["IdDoc"]["IndicadorMontoGravado"]

        if l10n_do_ncf_type not in ("41", "43", "47"):
            ecf_json["ECF"]["Encabezado"]["IdDoc"][
                "TipoIngresos"] = self.l10n_do_income_type
        else:
            del ecf_json["ECF"]["Encabezado"]["IdDoc"]["TipoIngresos"]

        if ecf_json["ECF"]["Encabezado"]["IdDoc"]["TipoPago"] == 2:
            ecf_json["ECF"]["Encabezado"]["IdDoc"]["FechaLimitePago"] = dt.strftime(
                self.invoice_date_due, "%d-%m-%Y")

            delta = self.invoice_date_due - self.invoice_date
            ecf_json["ECF"]["Encabezado"]["IdDoc"][
                "TerminoPago"] = "%s días" % delta.days

        if l10n_do_ncf_type not in ("43", "47"):

            if l10n_do_ncf_type in ("31", "41", "45"):
                ecf_json["ECF"]["Encabezado"]["Comprador"][
                    "RNCComprador"] = partner_vat

            if l10n_do_ncf_type == "32" or partner_vat:
                ecf_json["ECF"]["Encabezado"]["Comprador"][
                    "RNCComprador"] = partner_vat

            if l10n_do_ncf_type in ("33", "34"):
                origin_move_id = self.search([
                    ('ref', '=', self.l10n_do_origin_ncf)])
                if origin_move_id and origin_move_id.amount_total_signed >= 250000:
                    if is_l10n_do_partner:
                        ecf_json["ECF"]["Encabezado"]["Comprador"][
                            "RNCComprador"] = partner_vat
                    else:
                        ecf_json["ECF"]["Encabezado"]["Comprador"][
                            "IdentificadorExtranjero"] = partner_vat

            if l10n_do_ncf_type == "44":
                if is_l10n_do_partner and partner_vat:
                    ecf_json["ECF"]["Encabezado"]["Comprador"][
                        "RNCComprador"] = partner_vat
                elif not is_l10n_do_partner and partner_vat:
                    ecf_json["ECF"]["Encabezado"]["Comprador"][
                        "IdentificadorExtranjero"] = partner_vat

            if self.company_id.partner_id.l10n_do_dgii_tax_payer_type == "special":
                if is_l10n_do_partner:
                    ecf_json["ECF"]["Encabezado"]["Comprador"][
                        "RNCComprador"] = partner_vat
                else:
                    ecf_json["ECF"]["Encabezado"]["Comprador"][
                        "IdentificadorExtranjero"] = partner_vat

        if l10n_do_ncf_type not in ("31", "41", "43", "45") and not is_l10n_do_partner:
            if "Comprador" not in ecf_json["ECF"]["Encabezado"]:
                ecf_json["ECF"]["Encabezado"]["Comprador"] = {}

            if l10n_do_ncf_type == "32" and self.amount_total_signed >= 250000:
                ecf_json["ECF"]["Encabezado"]["Comprador"][
                    "IdentificadorExtranjero"] = partner_vat

        if l10n_do_ncf_type not in ("43", "47"):

            if l10n_do_ncf_type == "32":
                if self.amount_total_signed >= 250000 or partner_vat:
                    ecf_json["ECF"]["Encabezado"]["Comprador"][
                        "RazonSocialComprador"] = self.partner_id.name

            if l10n_do_ncf_type in ("33", "34"):
                origin_move_id = self.search(
                    [('ref', '=', self.l10n_do_origin_ncf)])
                if origin_move_id and origin_move_id.amount_total_signed >= 250000:
                    ecf_json["ECF"]["Encabezado"]["Comprador"][
                        "RazonSocialComprador"] = self.partner_id.name

            else:  # 31, 41, 44, 45, 46
                ecf_json["ECF"]["Encabezado"]["Comprador"][
                    "RazonSocialComprador"] = self.partner_id.name

        if l10n_do_ncf_type not in ("43", "44", "47") and self.amount_tax_signed:

            # Montos gravados con 18%, 16% y 0% de ITBIS
            taxed_amount_1 = get_taxed_amount(self, 18)
            taxed_amount_2 = get_taxed_amount(self, 16)
            taxed_amount_3 = get_taxed_amount(self, 0)
            exempt_amount = sum(line.credit for line in self.line_ids.filtered(
                lambda l: l.product_id and (
                        not l.tax_ids or (l.tax_line_id and not l.tax_line_id.amount))))

            itbis1_total = get_tax_amount(self, 18)
            itbis2_total = get_tax_amount(self, 16)
            itbis3_total = get_tax_amount(self, 0)

            total_taxed = sum([taxed_amount_1, taxed_amount_2, taxed_amount_3])
            total_itbis = sum([itbis1_total, itbis2_total, itbis3_total])

            if total_taxed:
                ecf_json["ECF"]["Encabezado"]["Totales"]["MontoGravadoTotal"] = abs(
                    round(total_taxed, 2))
            if taxed_amount_1:
                ecf_json["ECF"]["Encabezado"]["Totales"]["MontoGravadoI1"] = abs(
                    round(taxed_amount_1, 2))
            if taxed_amount_2:
                ecf_json["ECF"]["Encabezado"]["Totales"]["MontoGravadoI2"] = abs(
                    round(taxed_amount_2, 2))
            if taxed_amount_3:
                ecf_json["ECF"]["Encabezado"]["Totales"]["MontoGravadoI3"] = abs(
                    round(taxed_amount_3, 2))
            if exempt_amount:
                ecf_json["ECF"]["Encabezado"]["Totales"]["MontoExento"] = abs(
                    round(exempt_amount, 2))

            if taxed_amount_1:
                ecf_json["ECF"]["Encabezado"]["Totales"]["ITBIS1"] = "18"
            if taxed_amount_2:
                ecf_json["ECF"]["Encabezado"]["Totales"]["ITBIS2"] = "16"
            if taxed_amount_3:
                ecf_json["ECF"]["Encabezado"]["Totales"]["ITBIS3"] = "0%"

            if total_taxed:
                ecf_json["ECF"]["Encabezado"]["Totales"]["TotalITBIS"] = abs(
                    round(total_itbis, 2))
            if taxed_amount_1:
                ecf_json["ECF"]["Encabezado"]["Totales"]["TotalITBIS1"] = abs(
                    round(itbis1_total, 2))
            if taxed_amount_2:
                ecf_json["ECF"]["Encabezado"]["Totales"]["TotalITBIS2"] = abs(
                    round(itbis2_total, 2))
            if taxed_amount_3:
                ecf_json["ECF"]["Encabezado"]["Totales"]["TotalITBIS3"] = abs(
                    round(itbis3_total, 2))

            ecf_json["ECF"]["Encabezado"]["Totales"]["MontoTotal"] = abs(
                round(self.amount_total_signed, 2))

        # TODO: implement TotalITBISRetenido and TotalISRRetencion of Totales section

        if not is_company_currency:
            if "OtraMoneda" not in ecf_json["ECF"]["Encabezado"]:
                ecf_json["ECF"]["Encabezado"]["OtraMoneda"] = {}

            ecf_json["ECF"]["Encabezado"]["OtraMoneda"][
                "TipoMoneda"] = self.currency_id.name
            ecf_json["ECF"]["Encabezado"]["OtraMoneda"]["TipoCambio"] = abs(round(
                1 / (self.amount_total / self.amount_total_signed), 2))

            ecf_json["ECF"]["Encabezado"]["OtraMoneda"][
                "MontoTotalOtraMoneda"] = self.amount_total

            if l10n_do_ncf_type not in ("43", "44", "47"):

                rate = ecf_json["ECF"]["Encabezado"]["OtraMoneda"]["TipoCambio"]

                if "MontoGravadoTotal" in ecf_json["ECF"]["Encabezado"]["Totales"]:
                    ecf_json["ECF"]["Encabezado"]["OtraMoneda"][
                        "MontoGravadoTotalOtraMoneda"] = round(
                        ecf_json["ECF"]["Encabezado"]["Totales"][
                            "MontoGravadoTotal"] / rate,
                        2)
                    ecf_json["ECF"]["Encabezado"]["OtraMoneda"][
                        "TotalITBISOtraMoneda"] = \
                        round(ecf_json["ECF"]["Encabezado"]["Totales"][
                                  "TotalITBIS"] / rate, 2)

                if "MontoGravadoI1" in ecf_json["ECF"]["Encabezado"]["Totales"]:
                    ecf_json["ECF"]["Encabezado"]["OtraMoneda"][
                        "MontoGravado1OtraMoneda"] = round(
                        ecf_json["ECF"]["Encabezado"]["Totales"][
                            "MontoGravadoI1"] / rate, 2)
                    ecf_json["ECF"]["Encabezado"]["OtraMoneda"][
                        "TotalITBIS1OtraMoneda"] = \
                        round(ecf_json["ECF"]["Encabezado"]["Totales"][
                                  "TotalITBIS1"] / rate,
                              2)

                if "MontoGravadoI2" in ecf_json["ECF"]["Encabezado"]["Totales"]:
                    ecf_json["ECF"]["Encabezado"]["OtraMoneda"][
                        "MontoGravado2OtraMoneda"] = round(
                        ecf_json["ECF"]["Encabezado"]["Totales"][
                            "MontoGravadoI2"] / rate, 2)
                    ecf_json["ECF"]["Encabezado"]["OtraMoneda"][
                        "TotalITBIS2OtraMoneda"] = \
                        round(ecf_json["ECF"]["Encabezado"]["Totales"][
                                  "TotalITBIS2"] / rate,
                              2)

                if "MontoGravadoI3" in ecf_json["ECF"]["Encabezado"]["Totales"]:
                    ecf_json["ECF"]["Encabezado"]["OtraMoneda"][
                        "MontoGravado3OtraMoneda"] = round(
                        ecf_json["ECF"]["Encabezado"]["Totales"][
                            "MontoGravadoI3"] / rate, 2)
                    ecf_json["ECF"]["Encabezado"]["OtraMoneda"][
                        "TotalITBIS3OtraMoneda"] = \
                        round(ecf_json["ECF"]["Encabezado"]["Totales"][
                                  "TotalITBIS3"] / rate,
                              2)

            if "MontoExento" in ecf_json["ECF"]["Encabezado"][
                "Totales"] and l10n_do_ncf_type != "46":
                ecf_json["ECF"]["Encabezado"]["OtraMoneda"][
                    "MontoExentoOtraMoneda"] = round(
                    ecf_json["ECF"]["Encabezado"]["Totales"]["MontoExento"] / rate, 2)

        for i, line in enumerate(self.invoice_line_ids.sorted('sequence'), 1):

            rate = 1
            if "OtraMoneda" in ecf_json["ECF"]["Encabezado"]:
                rate = ecf_json["ECF"]["Encabezado"]["OtraMoneda"]["TipoCambio"]

            line_dict = od()
            product = line.product_id
            line_dict["NumeroLinea"] = i
            line_dict["IndicadorFacturacion"] = get_invoicing_indicator(line)
            line_dict["NombreItem"] = product.name if product else line.name
            line_dict["IndicadorBienoServicio"] = "2" if \
                product and product.type == "service" else "1"
            line_dict["DescripcionItem"] = line.name
            line_dict["CantidadItem"] = line.quantity

            line_dict["PrecioUnitarioItem"] = abs(line.price_unit if is_company_currency \
                else round(line.price_unit / rate, 2))

            price_unit_wo_discount = line.price_unit * (1 - (line.discount / 100.0))
            discount_amount = abs(
                round(price_unit_wo_discount - line.price_subtotal, 2))
            if line.discount:
                line_dict["TablaSubDescuento"] = {"SubDescuento": [{
                    "TipoSubDescuento": "%",
                    "SubDescuentoPorcentaje": line.discount,
                    "MontoSubDescuento": discount_amount if is_company_currency \
                        else round(discount_amount / rate, 2),
                }]}
                line_dict["DescuentoMonto"] = sum(
                    d["MontoSubDescuento"] for d in line_dict[
                        "TablaSubDescuento"]["SubDescuento"])

            if not is_company_currency:
                line_dict["OtraMonedaDetalle"] = {
                    "PrecioOtraMoneda": abs(line.price_unit),
                    "DescuentoOtraMoneda": discount_amount,
                    "MontoItemOtraMoneda": abs(round(line.price_subtotal, 2)),
                }

            line_dict["MontoItem"] = abs(round(line.price_subtotal if is_company_currency \
                else line.price_subtotal / rate, 2))

            ecf_json["ECF"]["DetallesItems"]["Item"].append(line_dict)

        if l10n_do_ncf_type in ("33", "34"):
            if "InformacionReferencia" not in ecf_json["ECF"]:
                ecf_json["ECF"]["InformacionReferencia"] = {}
            origin_move_id = self.search(
                [('ref', '=', self.l10n_do_origin_ncf)])
            ecf_json["ECF"]["InformacionReferencia"][
                "NCFModificado"] = origin_move_id.ref
            ecf_json["ECF"]["InformacionReferencia"][
                "FechaNCFModificado"] = dt.strftime(
                origin_move_id.invoice_date, "%d-%m-%Y")
            ecf_json["ECF"]["InformacionReferencia"][
                "CodigoModificacion"] = self.l10n_do_ecf_modification_code

        return ecf_json

    def log_error_message(self, body, sent_data):

        msg_body = "<ul>"
        try:
            import ast
            error_message = ast.literal_eval(body)
            for msg in list(error_message.get("messages") or []):
                msg_body += "<li>%s</li>" % msg
        except SyntaxError:
            msg_body += "<li>%s</li>" % body

        msg_body += "</ul>"
        msg_body += "<p>%s</p>" % sent_data
        self.env["mail.message"].sudo().create({
            "record_name": self.ref,
            "subject": _("e-CF Sending Error"),
            "body": msg_body,
        })

    def send_ecf_data(self):
        for invoice in self:

            if invoice.l10n_do_ecf_send_state == "delivered_accepted":
                raise ValidationError(_("Resend a Delivered and Accepted e-CF is not "
                                        "allowed."))

            ecf_data = invoice._get_invoice_ecf_json()
            api_url = self.env['ir.config_parameter'].sudo().get_param('ecf.api.url')
            try:
                response = requests.post(api_url, json=ecf_data)
                if response.status_code >= 400:
                    self.log_error_message(response.text, ecf_data)
                    invoice.l10n_do_ecf_send_state = "invalid"

                # if response.status_code == 401:
                #     # TODO: cuáles son los status_code del API?
                #     #  para saber si poner un rango de códigos
                #
                #     # Request could not authenticate with API
                #     invoice.l10n_do_ecf_send_state = "service_unreachable"
            except requests.exceptions.ConnectionError:
                # Odoo cound not send the request
                invoice.l10n_do_ecf_send_state = "not_sent"

        return True

    def post(self):

        res = super(AccountMove, self).post()

        fiscal_invoices = self.filtered(
            lambda i: i.is_ecf_invoice and i.l10n_do_ecf_send_state != \
                      "delivered_accepted")
        fiscal_invoices.send_ecf_data()

        return res
