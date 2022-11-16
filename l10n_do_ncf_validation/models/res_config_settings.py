from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    ncf_validation_target = fields.Selection(
        related="company_id.ncf_validation_target",
        readonly=False,
        required=True,
    )

    ncf_validation_dgii = fields.Boolean(related="company_id.ncf_validation_dgii", readonly=False)
    validate_ecf = fields.Boolean(related="company_id.validate_ecf", readonly=False)
