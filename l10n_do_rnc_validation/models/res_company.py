
from odoo import fields, models, api


class ResCompany(models.Model):
    _inherit = 'res.company'

    can_validate_rnc = fields.Boolean(
        default=True,
    )

    @api.onchange("name")
    def _onchange_company_name(self):
        if self.name:
            result = self.env['res.partner'].with_context(
                model=self._name).validate_rnc_cedula(self.name)
            if result:
                self.name = result.get('name')
                self.vat = result.get('vat')

    @api.onchange("vat")
    def _onchange_company_vat(self):
        if self.vat:
            result = self.env['res.partner'].with_context(
                model=self._name).validate_rnc_cedula(self.vat)
            if result:
                self.name = result.get('name')
                self.vat = result.get('vat')