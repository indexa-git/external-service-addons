from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    ncf_validation_target = fields.Selection(
        related="company_id.ncf_validation_target",
        readonly=False,
        required=True,
    )
<<<<<<< HEAD
    ncf_validation_dgii = fields.Boolean(related="company_id.ncf_validation_dgii", readonly=False)
=======
>>>>>>> 6d958a174b88b1fc5db797540831922cb3e15350
    validate_ecf = fields.Boolean(related="company_id.validate_ecf", readonly=False)
