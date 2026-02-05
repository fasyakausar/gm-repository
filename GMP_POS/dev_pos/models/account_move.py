import requests
from datetime import datetime, timedelta
import pytz
from odoo import models, fields, api, SUPERUSER_ID
from odoo.exceptions import UserError

class AccountMove(models.Model):
    _inherit = 'account.move'

    is_integrated = fields.Boolean(string="Integrated", default=False, readonly=True, tracking=True)
    vit_trxid = fields.Char(string="Transaction ID", default=False, tracking=True)
    is_payment = fields.Boolean(string="Payment", default=False, tracking=True)
    vit_pos_store = fields.Char(
        string='POS Store Location',
        readonly=True,
        help='Location source from delivery picking (complete name)'
    )
    gm_is_cancel = fields.Boolean(string="Cancel", readonly=True, default=False, tracking=True)