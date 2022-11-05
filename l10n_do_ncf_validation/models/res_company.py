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
<<<<<<< HEAD
    ncf_validation_dgii = fields.Boolean()
=======
>>>>>>> 6d958a174b88b1fc5db797540831922cb3e15350
    validate_ecf = fields.Boolean()
