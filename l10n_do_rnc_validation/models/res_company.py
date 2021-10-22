from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    l10_do_can_validate_rnc = fields.Boolean(
        "Validate RNC",
        default=True,
    )
