from odoo import models, fields


class ResCompany(models.Model):
    _inherit = "res.company"

    ncf_validation_target = fields.Selection(
        [
            ("none", "None"),
            ("external", "External"),
            ("internal", "Internal"),
            ("both", "Internal & External"),
        ],
        default="external",
        help="-Internal: validates company generated NCF.\n"
        "-External: validates NCF issued by external entity.\n"
        "-Both: validates both cases.",
    )

    ncf_validation_dgii = fields.Boolean()
    validate_ecf = fields.Boolean()
