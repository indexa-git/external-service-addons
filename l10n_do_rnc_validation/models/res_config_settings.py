from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    l10_do_can_validate_rnc = fields.Boolean(
        related="company_id.l10_do_can_validate_rnc",
        readonly=False,
    )
