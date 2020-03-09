#  Copyright (c) 2018 - Indexa SRL. (https://www.indexa.do) <info@indexa.do>
#  See LICENSE file for full licensing details.

from odoo import models, fields, api


class ResCompanyTokenWizard(models.TransientModel):
    _name = 'res.company.token.wizard'
    _description = "Set Token Wizard"

    def _get_default_token_ids(self):
        company_ids = self._context.get('active_model') == 'res.company' and self._context.get('active_ids') or []
        return [
            (0, 0, {'company_id': company.id, 'name': company.name})
            for company in self.env['res.company'].browse(company_ids)
        ]

    token_ids = fields.One2many('res.company.token.list', 'token_wizard_id', string='Companies',
                                default=_get_default_token_ids)

    @api.multi
    def set_company_token(self):
        self.ensure_one()
        for rec in self.token_ids:
            rec.company_id.write({'currency_service_token': rec.token})


class ResCompanyTokenList(models.TransientModel):
    _name = 'res.company.token.list'

    company_id = fields.Many2one('res.company', 'Company')
    name = fields.Char()
    token = fields.Char()
    token_wizard_id = fields.Many2one('res.company.token.wizard', 'Wizard', required=True)
