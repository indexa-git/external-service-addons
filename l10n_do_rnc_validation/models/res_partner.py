
import json
import logging
import requests

from odoo import models, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    from stdnum.do import rnc, cedula
except (ImportError, IOError) as err:
    _logger.debug(err)


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
    def validate_rnc_cedula(self, number, model='partner'):

        company_id = self.env['res.company'].search([
            ('id', '=', self.env.user.company_id.id)])

        if number and str(number).isdigit() and len(number) in (9, 11) and \
                company_id.can_validate_rnc:
            result, dgii_vals = {}, False
            # TODO use context instead of adding a parameter to the function
            model = 'res.partner' if model == 'partner' else 'res.company'

            self_id = self.id if self.id else 0
            # Considering multi-company scenarios
            domain = [
                ('vat', '=', number),
                ('id', '!=', self_id),
                ('parent_id', '=', False)
            ]
            if self.sudo().env.ref('base.res_partner_rule').active:
                domain.extend([('company_id', '=',
                                self.env.user.company_id.id)])
            contact = self.search(domain)

            if contact:
                name = contact.name if len(contact) == 1 else ", ".join(
                    [x.name for x in contact if x.name])
                raise UserError(_('RNC/Cédula %s is already assigned to %s')
                                % (number, name))

            try:
                is_rnc = len(number) == 9
                rnc.validate(number) if is_rnc else cedula.validate(number)
            except Exception:
                _logger.warning(
                    "RNC/Ced is invalid for partner {}".format(self.name))

            partner_json = self.get_contact_data(number)
            if partner_json and partner_json['data']:
                data = dict(partner_json['data'][0])
                result['name'] = data['business_name']
                result['vat'] = number
                if not result.get('phone') and data['phone']:
                    result['phone'] = data['phone']
                if not result.get('street'):
                    address = ""
                    if data['street']:
                        address += data['street']
                    if data['street_number']:
                        address += ", " + data['street_number']
                    if data['sector']:
                        address += ", " + data['sector']
                    result['street'] = address

                if model == 'res.partner':
                    result['is_company'] = True if is_rnc else False

            else:
                dgii_vals = rnc.check_dgii(number)
                if dgii_vals is None:
                    if is_rnc:
                        self.sudo().message_post(
                            subject=_("%s vat request" % self.name),
                            body=_("External service could not find requested "
                                   "contact data."))
                    result['vat'] = number
                    # TODO this has to be done in l10n_do
                    # result['sale_fiscal_type'] = "final"
                else:
                    result['name'] = dgii_vals.get('name', False)
                    result['vat'] = dgii_vals.get('rnc')

                    if model == 'res.partner':
                        result['is_company'] = True if is_rnc else False
                        # TODO this has to be done in l10n_do
                        # result['sale_fiscal_type'] = "fiscal"
            return result

    @api.onchange('name')
    def _onchange_partner_name(self):
        self.validate_vat_onchange(self.name)

    @api.onchange('vat')
    def _onchange_partner_vat(self):
        self.validate_vat_onchange(self.vat)

    @api.model
    def validate_vat_onchange(self, vat):
        if vat:
            result = self.validate_rnc_cedula(vat)
            if result:
                self.name = result.get('name')
                self.vat = result.get('vat')
                if not self.phone:
                    self.phone = result.get('phone')
                if not self.street:
                    self.street = result.get('street')
                self.is_company = result.get('is_company', False)
                # # TODO this has to be done in l10n_do
                # self.sale_fiscal_type = result.get('sale_fiscal_type')

    @api.model
    def name_create(self, name):
        if self._context.get('install_mode', False):
            return super(ResPartner, self).name_create(name)
        if self._rec_name:
            if name.isdigit():
                partner = self.search([('vat', '=', name)])
                if partner:
                    return partner.name_get()[0]
                else:
                    new_partner = self.create({"vat": name})
                    return new_partner.name_get()[0]
            else:
                return super(ResPartner, self).name_create(name)
