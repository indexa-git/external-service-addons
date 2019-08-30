# -*- coding: utf-8 -*-
#  Copyright (c) 2018 - Indexa SRL. (https://www.indexa.do) <info@indexa.do>
#  See LICENSE file for full licensing details.

import json
import logging
import requests
import datetime
import pytz
from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

CURRENCY_MAPPING = {
    'euro': 'EUR',
    'cdol': 'CAD',
    'doll': 'USD',
    'poun': 'GBP',
    'swis': 'CHF',
}


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_do_currency_interval_unit = fields.Selection([
        ('manually', 'Manually'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly')],
        default='daily', string='Interval Unit')
    l10n_do_currency_provider = fields.Selection([
        ('bpd', 'Banco Popular Dominicano'),
        ('bnr', 'Banco de Reservas'),
        ('bpr', 'Banco del Progreso'),
        ('bsc', 'Banco Santa Cruz'),
        ('bdi', 'Banco BDI'),
        ('bpm', 'Banco Promerica'),
        ('bvm', 'Banco Vimenca'),
        ('bcd', 'Banco Central Dominicano'),
    ], default='bpd', string='Bank')
    currency_base = fields.Selection([('buyrate', 'Buy rate'), ('sellrate', 'Sell rate')], default='sellrate')
    rate_offset = fields.Float('Offset', default=0)
    l10n_do_currency_next_execution_date = fields.Date(string="Next Execution Date")
    currency_service_token = fields.Char()
    last_currency_sync_date = fields.Date(string="Last Sync Date", readonly=True)

    _sql_constraints = [
        ('token_uniq', 'unique(currency_service_token)', 'Token must be unique per company.')
    ]

    def get_currency_rates(self, params, token):
        api_url = self.env['ir.config_parameter'].sudo().get_param('indexa.api.url')

        try:
            response = requests.get(api_url, params, headers={'x-access-token': token})
        except requests.exceptions.ConnectionError as e:
            _logger.warning(_('API requests return the following error %s' % e))
            return {}
        return response.text

    @api.multi
    def l10n_do_update_currency_rates(self):

        all_good = True
        res = True
        for company in self:
            if company.l10n_do_currency_provider:
                _logger.info("Calling API rates resource.")

                tz = pytz.timezone('America/Santo_Domingo')
                today = datetime.datetime.now(tz)
                params = {'bank': company.l10n_do_currency_provider,
                          'date': datetime.datetime.strftime(today, '%Y-%m-%d')}

                token = company.currency_service_token or ''
                rates_dict = self.get_currency_rates(params, token)

                d = {}
                try:
                    d = json.loads(rates_dict)
                except TypeError:
                    _logger.warning(_('No serializable data from API response'))

                if 'data' in d:
                    for currency in d['data']:
                        if str(currency['name']).endswith(company.currency_base or 'x') and currency['rate']:
                            inverse_rate = 1 / (float(currency['rate']) + company.rate_offset)
                            self.env['res.currency.rate'].create(
                                {'currency_id': self.env.ref('base.' + CURRENCY_MAPPING[str(currency['name'])[:4]]).id,
                                 'rate': inverse_rate, 'company_id': company.id})
                    company.last_currency_sync_date = fields.Date.today()
                else:
                    res = False
            else:
                res = False
            if not res:
                all_good = False
                _logger.warning(_('Unable to fetch new rates records from API'))
        return all_good

    @api.model
    def l10n_do_run_update_currency(self):

        records = self.search([('l10n_do_currency_next_execution_date', '<=', fields.Date.today())])
        if records:
            to_update = self.env['res.company']
            for record in records:
                if record.l10n_do_currency_interval_unit == 'daily':
                    next_update = relativedelta(days=+1)
                elif record.l10n_do_currency_interval_unit == 'weekly':
                    next_update = relativedelta(weeks=+1)
                elif record.l10n_do_currency_interval_unit == 'monthly':
                    next_update = relativedelta(months=+1)
                else:
                    record.l10n_do_currency_interval_unit = False
                    continue
                record.l10n_do_currency_next_execution_date = datetime.datetime.now() + next_update
                to_update += record
            to_update.l10n_do_update_currency_rates()
