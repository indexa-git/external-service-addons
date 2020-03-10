#  Copyright (c) 2018 - Indexa SRL. (https://www.indexa.do) <info@indexa.do>
#  See LICENSE file for full licensing details.

from odoo import models, fields, api


class AccountMove(models.Model):
    _inherit = 'account.move'

    rate = fields.Float(
        compute='_compute_rate',
        store=True,
    )
    show_rate = fields.Boolean(
        compute='_compute_show_rate'
    )

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

    @api.depends('state', 'invoice_date', 'currency_id')
    def _compute_rate(self):
<<<<<<< HEAD
        for inv in self.filtered(lambda i: i.invoice_date and i.state != 'paid'):
            inv.rate = inv.get_invoice_rate(inv.invoice_date)
=======
        for inv in self.filtered(lambda i: i.date_invoice):
            if not inv.rate:
                inv.rate = inv.get_invoice_rate(inv.date_invoice)
            else:
                inv.rate = inv.rate
>>>>>>> 12.0

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
