
import json
import logging
import requests

from odoo import models, api, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def name_search(self, name, args=None, operator='ilike', limit=100):
        res = super(ResPartner, self).name_search(
            name,
            args=args,
            operator=operator,
            limit=100
        )
        if not res and name:
            if len(name) in (9, 11):
                partners = self.search([('vat', '=', name)])
            else:
                partners = self.search([('vat', 'ilike', name)])
            if partners:
                res = partners.name_get()
        return res

    @api.model
    def get_contact_data(self, vat):
        """
        Gets contact fiscal data from external service.

        :param vat: string representation of contact tax id
        :return: json object containing contact fiscal data
        Eg:
        {
            "status": "success",
            "data": [
                {
                    "sector": "LOS RESTAURADORES",
                    "street_number": "18",
                    "street": "4",
                    "economic_activity": "VENTA DE SOFTWARE",
                    "phone": "9393231",
                    "tradename": "INDEXA",
                    "state": "ACTIVO",
                    "business_name": "INDEXA SRL",
                    "rnc": "131793916",
                    "payment_regime": "NORMAL",
                    "constitution_date": "2018-07-20"
                }
            ]
        }
        """
        if vat and vat.isdigit():
            try:
                _logger.info("Starting contact fiscal data request "
                             "of res.partner vat: %s" % vat)
                response = requests.get(
                    'https://api.indexa.do/api/rnc',
                    {'rnc': vat},
                    headers={'x-access-token': 'demotoken'}
                )
            except requests.exceptions.ConnectionError as e:
                _logger.warning('API requests return the following '
                                'error %s' % e)
                return {"status": "error", "data": []}
            try:
                return json.loads(response.text)
            except TypeError:
                _logger.warning(_('No serializable data from API response'))
        return False

    @api.model
    def create(self, vals):
        rnc = False
        company_obj = self.env['res.company'].search([
            ('id', '=', self.env.user.company_id.id)])
        if vals['vat'] and vals['vat'].isdigit() and \
                company_obj.can_validate_rnc:
            rnc = vals['vat']

        if vals['name'].isdigit():
            if company_obj.can_validate_rnc:
                rnc = vals['name']
            else:
                raise UserError(_('Inquiries from RNC / Cedula online are '
                                  'deactivated, please contact your '
                                  'administrator'))

        if rnc:
            partner_search = self.search([('vat', '=', rnc)], limit=1)
            if not partner_search:
                partner = self.env['res.partner'].\
                    get_contact_data(rnc)

                if partner and partner['data']:
                    vals['name'] = partner['data'][0]['business_name']
                    vals['vat'] = rnc
                    if not vals['phone'] and partner['data'][0]['phone']:
                        vals['phone'] = partner['data'][0]['phone']
                    if not vals['street'] and partner['data'][0]['street']:
                        vals['street'] = '%s, #%s, %s' % (
                            partner['data'][0]['street'],
                            partner['data'][0]['street_number'],
                            partner['data'][0]['sector'],
                        )
                    if len(rnc) == 9:
                        vals['is_company'] = True
                    else:
                        vals['is_company'] = False

                else:
                    raise UserError(_('RNC/Cedula %s not exist') % rnc)
            else:
                raise UserError(_('RNC/Cedula %s exist with name %s')
                                % (rnc, partner_search.name))

        res = super(ResPartner, self).create(vals)

        return res
