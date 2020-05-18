#  Copyright (c) 2018 - Indexa SRL. (https://www.indexa.do) <info@indexa.do>
#  See LICENSE file for full licensing details.

from odoo import models, fields


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    rate = fields.Float(
        # Deprecated.
        # Do not forwardport to v14.
    )
