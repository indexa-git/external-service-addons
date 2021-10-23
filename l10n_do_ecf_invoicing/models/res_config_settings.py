from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    l10n_do_ecf_service_env = fields.Selection(
        related="company_id.l10n_do_ecf_service_env",
        readonly=False,
    )
    l10n_do_send_ecf_on_payment = fields.Boolean(
        related="company_id.l10n_do_send_ecf_on_payment", readonly=False
    )
