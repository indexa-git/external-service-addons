# -*- coding: utf-8 -*-
#  Copyright (c) 2018 - Indexa SRL. (https://www.indexa.do) <info@indexa.do>
#  See LICENSE file for full licensing details.

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ResCompanyHashWizard(models.TransientModel):
    _name = 'res.company.hash.wizard'

    def _get_default_hash_ids(self):
        context = dict(self._context or {})
        active_model = context.get('active_model')
        active_ids = context.get('active_ids')
        if active_model != 'res.company':
            raise UserError(_("Programmation error: the expected model for this action is "
                              "'res.company'. The provided one is '%s'.") % active_model)

        company_ids = self.env['res.company'].browse(active_ids)
        Line = self.env['res.company.hash.list']
        lines = Line

        print self.id

        for company in company_ids:
            lines += Line.create({'company_id': company.id, 'hash_wizard_id': self.id})

        return [(4, line.id) for line in lines]

    hash_ids = fields.One2many('res.company.hash.list', 'hash_wizard_id', string='Companies',
                               default=_get_default_hash_ids)

    @api.multi
    def set_company_hash(self):
        self.ensure_one()
        for rec in self.env['res.company.hash.list'].search([('hash_wizard_id', '=', self.id)]):
            print rec.company_id.name
            # rec.company_id.hash = rec.hash


class ResCompanyHashList(models.TransientModel):
    _name = 'res.company.hash.list'

    company_id = fields.Many2one('res.company', 'Company')
    name = fields.Char(related='company_id.name')
    hash = fields.Char()
    hash_wizard_id = fields.Many2one('res.company.hash.wizard', 'Wizard')
