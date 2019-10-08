# -*- coding: utf-8 -*-
#  Copyright (c) 2018 - Indexa SRL. (https://www.indexa.do) <info@indexa.do>
#  See LICENSE file for full licensing details.

from odoo import models, fields, api


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    rate = fields.Float(
        compute='_compute_rate',
        store=True,
    )
    show_rate = fields.Boolean(
        compute='_compute_show_rate'
    )

    @api.multi
    @api.depends('currency_id', 'company_id')
    def _compute_show_rate(self):
        for inv in self:
            inv.show_rate = not inv.company_id.currency_id == inv.currency_id

    def get_invoice_rate(self, date):

        Rate = self.env['res.currency.rate']

        rate_id = Rate.search([('name', '=', date),
                               ('currency_id', '=', self.currency_id.id),
                               ('company_id', '=', self.company_id.id)])

        if rate_id:
            return 1 / rate_id.rate

        before_rate_id = Rate.search(
            [('name', '<', date), ('currency_id', '=', self.currency_id.id),
             ('company_id', '=', self.company_id.id)], order='name desc', limit=1)

        return 1 / before_rate_id.rate if before_rate_id else 1

    @api.multi
    @api.depends('state', 'date_invoice', 'currency_id')
    def _compute_rate(self):
        for inv in self.filtered(lambda i: i.date_invoice and i.state != 'paid'):
            inv.rate = inv.get_invoice_rate(inv.date_invoice)
