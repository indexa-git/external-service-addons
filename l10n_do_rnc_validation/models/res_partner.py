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
    _inherit = "res.partner"

    @api.model
    def name_search(self, name, args=None, operator="ilike", limit=100):
        res = super(ResPartner, self).name_search(
            name, args=args, operator=operator, limit=100
        )
        if not res and name:
            if len(name) in (9, 11):
                partners = self.search([("vat", "=", name)])
            else:
                partners = self.search([("vat", "ilike", name)])
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
                _logger.info(
                    "Starting contact fiscal data request "
                    "of res.partner vat: %s" % vat
                )
                api_url = (
                    self.env["ir.config_parameter"]
                    .sudo()
                    .get_param("rnc.indexa.api.url")
                )
                token = (
                    self.env["ir.config_parameter"]
                    .sudo()
                    .get_param("rnc.indexa.api.token")
                )
                response = requests.get(
                    api_url, {"rnc": vat}, headers={"x-access-token": token}
                )
            except requests.exceptions.ConnectionError as e:
                _logger.warning("API requests return the following " "error %s" % e)
                return {"status": "error", "data": []}
            try:
                return json.loads(response.text)
            except TypeError:
                _logger.warning(_("No serializable data from API response"))
        return False

    @api.model
    def validate_rnc_cedula(self, number):

        company_id = self.env.user.company_id

        if (
            number
            and str(number).isdigit()
            and len(number) in (9, 11)
            and company_id.l10_do_can_validate_rnc
        ):
            result, dgii_vals = {}, False
            model = self.env.context.get("model")

            if model == "res.partner" and self:
                self_id = [self.id, self.parent_id.id]
            else:
                self_id = [company_id.id]

            # Considering multi-company scenarios
            domain = [
                ("vat", "=", number),
                ("id", "not in", self_id),
                ("parent_id", "=", False),
            ]
            if self.sudo().env.ref("base.res_partner_rule").active:
                domain.extend([("company_id", "=", company_id.id)])
            contact = self.search(domain)

            if contact:
                name = (
                    contact.name
                    if len(contact) == 1
                    else ", ".join([x.name for x in contact if x.name])
                )
                raise UserError(
                    _("RNC/Cédula %s is already assigned to %s") % (number, name)
                )

            is_rnc = len(number) == 9
            try:
                rnc.validate(number) if is_rnc else cedula.validate(number)
            except Exception:
                _logger.warning("RNC/Ced is invalid for partner {}".format(self.name))

            partner_json = self.get_contact_data(number)
            if partner_json and partner_json.get("data"):
                data = dict(partner_json["data"][0])
                result["name"] = data["business_name"]
                result["ref"] = data.get("tradename")
                result["vat"] = number
                if not result.get("phone") and data.get("phone"):
                    result["phone"] = data["phone"]
                if not result.get("street"):
                    address = ""
                    if data.get("street") and not data.get("street").isspace():
                        address += data["street"]
                    if (
                        data.get("street_number")
                        and not data.get("street_number").isspace()
                    ):
                        address += ", " + data["street_number"]
                    if data.get("sector") and not data.get("sector").isspace():
                        address += ", " + data["sector"]
                    result["street"] = address

                if model == "res.partner":
                    result["is_company"] = True if is_rnc else False

            else:
                try:
                    dgii_vals = rnc.check_dgii(number)
                except Exception:
                    pass
                if not bool(dgii_vals):
                    result["vat"] = number
                else:
                    result["name"] = dgii_vals.get("name", False)
                    result["vat"] = dgii_vals.get("rnc")
                    if model == "res.partner":
                        result["is_company"] = is_rnc
            return result

    def _get_updated_vals(self, vals):
        new_vals = {}
        if any([val in vals for val in ["name", "vat"]]):
            vat = vals["vat"] if vals.get("vat") else vals.get("name")
            result = self.with_context(model=self._name).validate_rnc_cedula(vat)
            if result is not None:
                if "name" in result:
                    new_vals["name"] = result.get("name")
                new_vals["vat"] = result.get("vat")
                new_vals["ref"] = result.get("ref")
                new_vals["is_company"] = result.get("is_company", False)
                new_vals["company_type"] = (
                    "company" if new_vals["is_company"] else "person"
                )
                if not vals.get("phone"):
                    new_vals["phone"] = result.get("phone")
                if not vals.get("street"):
                    new_vals["street"] = result.get("street")
        return new_vals

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.update(self._get_updated_vals(vals))
        return super(ResPartner, self).create(vals_list)

    @api.model
    def name_create(self, name):
        if self._context.get("install_mode", False):
            return super(ResPartner, self).name_create(name)
        if self._rec_name:
            if name.isdigit():
                partner = self.search([("vat", "=", name)])
                if partner:
                    return partner.name_get()[0]
                else:
                    new_partner = self.create({"vat": name})
                    return new_partner.name_get()[0]
            else:
                return super(ResPartner, self).name_create(name)
