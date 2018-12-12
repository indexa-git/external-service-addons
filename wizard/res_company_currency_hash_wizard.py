# -*- coding: utf-8 -*-
#  Copyright (c) 2018 - Indexa SRL. (https://www.indexa.do) <info@indexa.do>
#  See LICENSE file for full licensing details.

from odoo import models, fields, api


class ResCompanyHashWizard(models.TransientModel):
    _name = 'res.company.hash.wizard'
    _description = "Set Hash Wizard"

    def _get_default_hash_ids(self):
        company_ids = self._context.get('active_model') == 'res.company' and self._context.get('active_ids') or []
        return [
            (0, 0, {'company_id': company.id, 'name': company.name})
            for company in self.env['res.company'].browse(company_ids)
        ]

    hash_ids = fields.One2many('res.company.hash.list', 'hash_wizard_id', string='Companies',
                               default=_get_default_hash_ids)

    @api.multi
    def set_company_hash(self):
        self.ensure_one()
        for rec in self.hash_ids:
            rec.company_id.write({'currency_service_hash': rec.hash})


class ResCompanyHashList(models.TransientModel):
    _name = 'res.company.hash.list'

    company_id = fields.Many2one('res.company', 'Company')
    name = fields.Char()
    hash = fields.Char()
    hash_wizard_id = fields.Many2one('res.company.hash.wizard', 'Wizard', required=True)
