# -*- coding: utf-8 -*-
from odoo import fields, models


class ResUsersInherit(models.Model):
    _inherit = 'res.users'

    gm_warehouse_id = fields.Many2one('stock.warehouse', string="Warehouse")
