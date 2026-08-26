from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_round
import copy
import math
import logging

_logger = logging.getLogger(__name__)

class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    qty_on_hand = fields.Float(
        string="On Hand",
        related='move_id.qty_on_hand',
        readonly=True,
    )