#  Copyright (c) 2020 - Indexa SRL. (https://www.indexa.do) <info@indexa.do>
#  See LICENSE file for full licensing details.

from odoo import models, fields


class ResCompany(models.Model):
    _inherit = "res.company"

    l10n_do_ecf_deferred_submissions = fields.Boolean(
        "Deferred submissions",
        help="Identify taxpayers who have been previously authorized "
             "to have sales through offline mobile devices such as "
             "sales with Handheld, enter others."
    )
