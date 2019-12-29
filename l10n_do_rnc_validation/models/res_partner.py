
import json
import logging
import requests

from odoo import models, api, _
from odoo.exceptions import UserError

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
                api_url = self.env['ir.config_parameter'].sudo().get_param(
                    'rnc.indexa.api.url')
                response = requests.get(
                    api_url, {'rnc': vat},
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
        rnc = ""
        company_id = self.env['res.company'].search([
            ('id', '=', self.env.user.company_id.id)])
        if 'vat' in vals and str(vals['vat']).isdigit() and \
                company_id.can_validate_rnc:
            rnc = vals['vat']

        if vals['name'].isdigit() and len(vals['name']) in (9, 11) and \
                company_id.can_validate_rnc:
            rnc = vals['name']

        if rnc:
            partner_search = self.search([('vat', '=', rnc)], limit=1)
            if not partner_search:
                partner_json = self.get_contact_data(rnc)
                if partner_json and partner_json['data']:
                    data = dict(partner_json['data'][0])
                    vals['name'] = data['business_name']
                    vals['vat'] = rnc
                    if not vals.get('phone') and data['phone']:
                        vals['phone'] = data['phone']
                    if not vals.get('street'):
                        address = ""
                        if data['street']:
                            address += data['street']
                        if data['street_number']:
                            address += ", " + data['street_number']
                        if data['sector']:
                            address += ", " + data['sector']
                        vals['street'] = address

                    if len(rnc) == 9:
                        vals['is_company'] = True
                    else:
                        vals['is_company'] = False

                else:
                    # TODO: here we should request data from DGII WebService
                    partner = super(ResPartner, self).create(vals)
                    partner.sudo().message_post(
                        subject=_("%s vat request" % partner.name),
                        body=_("External service could not find requested "
                               "contact data."))
                    return partner
            else:
                raise UserError(_('RNC/Cédula %s exist with name %s')
                                % (rnc, partner_search.name))
        return super(ResPartner, self).create(vals)
