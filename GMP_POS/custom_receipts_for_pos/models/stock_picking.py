import requests
from datetime import datetime, timedelta
import pytz
from odoo import models, fields, api, SUPERUSER_ID
from odoo.exceptions import UserError
import random
import logging

_logger = logging.getLogger(__name__)

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    # Di class StockPicking
    is_admin_menu_access = fields.Boolean(
        string="Is Admin Menu Access",
        compute="_compute_is_admin_menu_access",
    )

    def _compute_is_admin_menu_access(self):
        is_admin = self.env.user.has_group('custom_receipts_for_pos.group_admin_menu_access')
        for record in self:
            record.is_admin_menu_access = is_admin

from odoo import models, fields
from pytz import timezone, UTC

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        res = super().button_validate()

        for picking in self:
            if picking.picking_type_code != 'incoming':
                continue
            if not picking.scheduled_date:
                continue

            backdate = picking.scheduled_date
            backdate_str = fields.Datetime.to_string(backdate)

            # Update stock moves & lines
            done_moves = picking.move_ids.filtered(lambda m: m.state == 'done')
            done_moves.sudo().write({'date': backdate})
            picking.move_line_ids.sudo().write({'date': backdate})

            # Update date_done pada picking
            picking.sudo().write({'date_done': backdate})

            # Update SVL
            svl_ids = done_moves.mapped('stock_valuation_layer_ids').ids
            if svl_ids:
                self.env.cr.execute(
                    "UPDATE stock_valuation_layer SET create_date=%s, write_date=%s WHERE id=ANY(%s)",
                    (backdate_str, backdate_str, svl_ids)
                )

            # Update journal entry inventory
            local_date = backdate.replace(tzinfo=UTC).astimezone(timezone('Asia/Jakarta')).date()
            for move in done_moves:
                for aml in move.account_move_ids:
                    was_posted = aml.state == 'posted'
                    if was_posted:
                        aml.sudo().button_draft()
                    aml.sudo().write({'date': local_date, 'name': '/'})
                    aml.sudo().line_ids.write({'date': local_date})
                    if was_posted:
                        aml.sudo().action_post()

        return res