# -*- coding: utf-8 -*-
# © 2015-2018 Marcos Organizador de Negocios SRL. (https://marcos.do/)
#             Eneldo Serrata <eneldo@marcos.do>
# © 2017-2018 iterativo SRL. (https://iterativo.do/)
#             Gustavo Valverde <gustavo@iterativo.do>
# © 2019 Yasmany Castillo <yasmany003@gmail.com>
# This file is part of Dominican Banks Currency Update.
# ######################################################################

from datetime import datetime as dt
import json
import requests
import pytz

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


CURRENCY_MAPPING = {
    'euro': 'EUR',
    'cdol': 'CAD',
    'doll': 'USD',
    'poun': 'GBP',
    'swis': 'CHF',
}

CURRENCY_PROVIDER = {
    'bpd': 'Banco Popular Dominicano',
    'bnr': 'Banco de Reservas',
    'bpr': 'Banco del Progreso',
    'bsc': 'Banco Santa Cruz',
    'bdi': 'Banco BDI',
    'bpm': 'Banco Promerica',
    'bvm': 'Banco Vimenca',
    'bcd': 'Banco Central Dominicano'
}


class UpdateRateWizard(models.TransientModel):
    _name = "update.rate.wizard"
    _description = "Update rate wizard."

    def _get_bank_rates(self):
        """Prepare a default list of banks by currency with rates."""
        rates = []
        company = self.env.user.company_id
        token = company.currency_service_token or ''
        tz = pytz.timezone('America/Santo_Domingo')
        date = dt.strftime(fields.Date.today(), "%Y-%m-%d")

        for k, v in CURRENCY_PROVIDER.items():
            params = {'bank': k, 'date': date}

            # Get rates info from INDEXA api
            rates_dict = company.get_currency_rates(params, token)
            d = {}
            try:
                d = json.loads(rates_dict)
            except TypeError:
                _logger.warning(_('No serializable data from API response'))

            if 'data' in d:
                for currency in d['data']:
                    if str(currency['name']).endswith(company.currency_base or 'x') and currency['rate']:
                        inverse_rate = 1 / (float(currency['rate']) + company.rate_offset)
                        currency_name = CURRENCY_MAPPING[str(currency['name'])[:4]]
                        rate = currency['rate']

                        # Prepare values to make a tuple for the list
                        value1 = "%s_%s_%s" % (k, currency_name.lower(), rate)
                        value2 = "%s %s - %s" % (v, currency_name, rate)
                        tuple_values = (value1, value2)

                        # Add tuple of bank rate info for our list
                        rates.append(tuple_values)
        return rates

    @api.model
    def default_get(self, fields):
        active_id = self._context.get("active_id", False)
        invoice_id = self.env["account.invoice"].browse(active_id)

        if not invoice_id.date_invoice:
            raise ValidationError(_(u"Debe especificar la fecha de la factura primero."))

        if invoice_id.state != "draft":
            raise UserError(_(u"¡No puede cambiar la tasa porque la factura no está en estado borrador!"))
        return super(UpdateRateWizard, self).default_get(fields)


    bank_rates = fields.Selection(_get_bank_rates, string="Tasa en bancos")
    custom_rate = fields.Boolean("Digitar tasa manualmente", default=True)
    rate = fields.Monetary(string="Tasa")

    @api.multi
    def change_rate(self):
        """ Update/create currency rate if neccesary and update invoice rate"""

        Rate = self.env['res.currency.rate']
        active_id = self._context.get("active_id", False)
        invoice_id = self.env["account.invoice"].browse(active_id)
        company = invoice_id.company_id
        currency_id = invoice_id.currency_id
        date = dt.strftime(fields.Date.today(), "%Y-%m-%d")
        inverse_rate = 0

        if not self.custom_rate:
            # Split field value to get rate from it
            bank, cur, rate = self.bank_rates.split('_')
            invoice_rate = float(rate)
        else:
            invoice_rate = self.rate

        inverse_rate = 1/(invoice_rate + company.rate_offset)

        # If this rate exists then update if not create it
        if currency_id and currency_id.active:
            rate_id = Rate.search([
                ('name', '=', invoice_id.date_invoice),
                ('currency_id', '=', currency_id.id),
                ('company_id', '=', company.id)
            ])
            if rate_id:
                rate_id.write({'rate': inverse_rate})
            else:
                Rate.create({
                    'name': invoice_id.date_invoice,
                    'currency_id': currency_id.id,
                    'rate': inverse_rate,
                    'company_id': company.id
                })

        # Update invoice rate
        invoice_id.update({'rate': invoice_rate})
