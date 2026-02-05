# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    qty_on_hand = fields.Float(
        string='Qty On Hand',
        compute='_compute_qty_on_hand',
        store=False,
        digits='Product Unit of Measure',
        help='Quantity available in the warehouse specified in the sales order'
    )

    @api.depends('product_id', 'order_id.warehouse_id')
    def _compute_qty_on_hand(self):
        """Compute available quantity based on warehouse in sales order"""
        for line in self:
            if line.product_id and line.order_id.warehouse_id:
                # Get stock location from warehouse
                location = line.order_id.warehouse_id.lot_stock_id
                
                # Calculate on hand quantity
                qty_available = line.product_id.with_context(
                    location=location.id
                ).qty_available
                
                line.qty_on_hand = qty_available
            else:
                line.qty_on_hand = 0.0


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    # Optional: add field at header level if needed
    show_qty_on_hand = fields.Boolean(
        string='Show Qty On Hand',
        compute='_compute_show_qty_on_hand',
        help='Show qty on hand only for TSOUT operation type'
    )

    @api.depends('picking_type_id')
    def _compute_show_qty_on_hand(self):
        """Determine if qty on hand should be shown based on operation type"""
        for picking in self:
            # Adjust this condition based on your TSOUT operation type identifier
            # Option 1: by code
            picking.show_qty_on_hand = picking.picking_type_id.code == 'outgoing'
            
            # Option 2: by name (if your TSOUT has specific name)
            # picking.show_qty_on_hand = 'TSOUT' in (picking.picking_type_id.name or '')
            
            # Option 3: by sequence code
            # picking.show_qty_on_hand = picking.picking_type_id.sequence_code == 'TSOUT'


class StockMove(models.Model):
    _inherit = 'stock.move'

    qty_on_hand = fields.Float(
        string='Qty On Hand',
        compute='_compute_qty_on_hand',
        store=False,
        digits='Product Unit of Measure',
        help='Quantity available in the source location'
    )

    @api.depends('product_id', 'location_id', 'picking_id.picking_type_id')
    def _compute_qty_on_hand(self):
        """Compute available quantity based on source location"""
        for move in self:
            # Only calculate for TSOUT operations
            if move.picking_id and move.picking_id.picking_type_id.code == 'outgoing':
                if move.product_id and move.location_id:
                    # Calculate on hand quantity at source location
                    qty_available = move.product_id.with_context(
                        location=move.location_id.id
                    ).qty_available
                    
                    move.qty_on_hand = qty_available
                else:
                    move.qty_on_hand = 0.0
            else:
                move.qty_on_hand = 0.0

    # Optional: Add validation method if blocking is needed in the future
    def _check_qty_on_hand_blocking(self):
        """
        Validation method to block TSOUT when qty is insufficient
        Currently inactive - can be activated by calling this method
        in appropriate trigger (e.g., button_validate)
        """
        for move in self:
            if move.picking_id.picking_type_id.code == 'outgoing':
                if move.qty_on_hand < move.product_uom_qty:
                    raise ValidationError(
                        f"Insufficient stock for product {move.product_id.display_name}!\n"
                        f"Required: {move.product_uom_qty} {move.product_uom.name}\n"
                        f"Available: {move.qty_on_hand} {move.product_uom.name}"
                    )

    # Uncomment below to activate blocking on validate
    # def _action_confirm(self, merge=True, merge_into=False):
    #     self._check_qty_on_hand_blocking()
    #     return super()._action_confirm(merge=merge, merge_into=merge_into)


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    qty_on_hand = fields.Float(
        string='Qty On Hand',
        compute='_compute_qty_on_hand',
        store=False,
        digits='Product Unit of Measure',
        help='Quantity available in the source location'
    )

    @api.depends('product_id', 'location_id', 'picking_id.picking_type_id')
    def _compute_qty_on_hand(self):
        """Compute available quantity based on source location"""
        for move_line in self:
            # Only calculate for TSOUT operations
            if move_line.picking_id and move_line.picking_id.picking_type_id.code == 'outgoing':
                if move_line.product_id and move_line.location_id:
                    # Calculate on hand quantity at source location
                    qty_available = move_line.product_id.with_context(
                        location=move_line.location_id.id
                    ).qty_available
                    
                    move_line.qty_on_hand = qty_available
                else:
                    move_line.qty_on_hand = 0.0
            else:
                move_line.qty_on_hand = 0.0