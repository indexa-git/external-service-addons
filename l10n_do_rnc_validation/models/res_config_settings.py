
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    can_validate_rnc = fields.Boolean(
        related="company_id.can_validate_rnc",
        readonly=False,
    )
