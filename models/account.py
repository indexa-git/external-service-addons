# -*- coding: utf-8 -*-
#  Copyright (c) 2018 - Indexa SRL. (https://www.indexa.do) <info@indexa.do>
#  See LICENSE file for full licensing details.

from datetime import timedelta as td
from odoo import models, fields, api


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    rate = fields.Float(
        compute='_compute_rate',
        store=True,
    )

    def get_invoice_rate(self, date):

        Rate = self.env['res.currency.rate']

        rate_id = Rate.search([('name', '=', date),
                               ('currency_id', '=', self.currency_id.id),
                               ('company_id', '=', self.company_id.id)])

        if rate_id:
            return rate_id.rate

        if Rate.search_count([('name', '<', date), ('currency_id', '=', self.currency_id.id),
                              ('company_id', '=', self.company_id.id)]):
            date = fields.Date.from_string(date) - td(days=1)
            return self.get_invoice_rate(fields.Date.to_string(date))

        return 1

    @api.multi
    @api.depends('state', 'date_invoice', 'currency_id')
    def _compute_rate(self):
        for inv in self.filtered(lambda i: i.date_invoice and i.state != 'paid'):
            inv.rate = self.get_invoice_rate(inv.date_invoice)

    def action_show_currency(self):
        self.ensure_one()
        view_id = self.env.ref('base.view_currency_form')
        return {
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'res.currency',
            'view_id': view_id.id,
            'res_id': self.currency_id.id
        }
