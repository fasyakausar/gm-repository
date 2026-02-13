# -*- coding: utf-8 -*-
# Inherit stock.return.picking wizard to handle backorder quantity update
# upon returning a validated receipt.
#
# Scenario:
#   PO: Item A=50, Item B=60
#   Receipt (done): Item A=40, Item B=60  → Backorder created: Item A=10 (state='assigned')
#   Return on done receipt: e.g. Item A=10
#   → After return is confirmed, Backorder Item A qty is increased by 10 (becomes 20).

from odoo import models
from odoo.tools.float_utils import float_is_zero


class ReturnPicking(models.TransientModel):
    _inherit = 'stock.return.picking'

    def _create_returns(self):
        """
        Override to update the product_uom_qty on related backorder move(s)
        after a return is created from a validated receipt.

        Logic:
        - For each return line, find the original move (move_id).
        - Look for a backorder picking linked to the original picking
          (picking_id.backorder_ids) whose move is in a non-done/non-cancel state
          and refers to the same product.
        - Increase that move's product_uom_qty by the returned quantity.
        - Re-run action_assign so the backorder reflects updated demand.
        """
        new_picking_id, picking_type_id = super()._create_returns()

        self._update_backorder_quantities()

        return new_picking_id, picking_type_id

    def _update_backorder_quantities(self):
        """
        Find backorder moves for the original picking and increase their
        demanded quantity by the amount being returned.
        """
        original_picking = self.picking_id

        # Collect all backorder pickings (direct and recursive)
        backorder_pickings = self._get_all_backorders(original_picking)

        if not backorder_pickings:
            return

        for return_line in self.product_return_moves:
            returned_qty = return_line.quantity
            if float_is_zero(returned_qty,
                             precision_rounding=return_line.uom_id.rounding):
                continue

            product = return_line.product_id

            # Find the matching move in any backorder that is still open
            backorder_moves = backorder_pickings.mapped('move_ids').filtered(
                lambda m: (
                    m.product_id == product
                    and m.state not in ('done', 'cancel')
                )
            )

            for bo_move in backorder_moves:
                bo_move.write({
                    'product_uom_qty': bo_move.product_uom_qty + returned_qty,
                })

        # Re-assign availability on updated backorders
        backorders_to_reassign = backorder_pickings.filtered(
            lambda p: p.state not in ('done', 'cancel')
        )
        if backorders_to_reassign:
            backorders_to_reassign.action_assign()

    @staticmethod
    def _get_all_backorders(picking):
        """
        Recursively collect all backorder pickings derived from `picking`.
        Returns a recordset of stock.picking.
        """
        result = picking.env['stock.picking']
        to_process = list(picking.backorder_ids)
        while to_process:
            bo = to_process.pop()
            if bo not in result:
                result |= bo
                to_process.extend(bo.backorder_ids)
        return result