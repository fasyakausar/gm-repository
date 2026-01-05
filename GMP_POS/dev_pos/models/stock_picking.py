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

    is_integrated = fields.Boolean(string="Integrated", default=False, readonly=True, tracking=True)
    is_closed = fields.Boolean(string="Closed", default=False, readonly=True, tracking=True)
    vit_trxid = fields.Char(string="Transaction ID", default=False, tracking=True)
    target_location = fields.Many2one('stock.location', string="Target Location")
    stock_type = fields.Many2one('master.type', string="Stock Type")
    related_picking_id = fields.Many2one('stock.picking', string="Related Transfer", readonly=True, tracking=True)
    gm_type_transfer = fields.Selection([
        ('ts_out', 'TSOUT'),
        ('ts_in', 'TSIN'),
    ], string="Transfer Type", compute="_compute_gm_type_transfer", store=True, tracking=True)

    @api.depends('location_id', 'location_dest_id', 'location_id.usage', 'location_dest_id.usage')
    def _compute_gm_type_transfer(self):
        """
        Automatically determine transfer type based on Transit location:
        - If destination location usage is 'transit' -> TSOUT
        - If source location usage is 'transit' -> TSIN
        """
        for record in self:
            gm_type = False
            
            # Check if destination location usage is 'transit'
            if record.location_dest_id and record.location_dest_id.usage == 'transit':
                gm_type = 'ts_out'
            # Check if source location usage is 'transit'
            elif record.location_id and record.location_id.usage == 'transit':
                gm_type = 'ts_in'
            
            record.gm_type_transfer = gm_type

    @api.onchange('picking_type_id')
    def _onchange_picking_type_id_set_transit(self):
        """
        Auto-fill destination location with transit location when operation type is TSOUT
        Override default customer location from outgoing operation type
        """
        # Cek apakah picking type ini adalah TSOUT (outgoing)
        if self.picking_type_id and self.picking_type_id.code == 'outgoing' and 'TSOUT' in self.picking_type_id.name:
            # Cari lokasi dengan usage 'transit' - OVERRIDE default customer location
            transit_location = self.env['stock.location'].search([
                ('usage', '=', 'transit'),
                ('company_id', '=', self.company_id.id)
            ], limit=1)
            
            if transit_location:
                self.location_dest_id = transit_location.id
                _logger.info(f"TSOUT: Auto-set destination to transit location: {transit_location.name}")

    @api.model
    def create(self, vals):
        """
        Override create to auto-set destination location for TSOUT
        """
        # Cek apakah ini TSOUT
        if vals.get('picking_type_id'):
            picking_type = self.env['stock.picking.type'].browse(vals['picking_type_id'])
            if picking_type and picking_type.code == 'outgoing' and 'TSOUT' in picking_type.name:
                # Cari lokasi dengan usage transit
                transit_location = self.env['stock.location'].search([
                    ('usage', '=', 'transit'),
                    ('company_id', '=', vals.get('company_id', self.env.company.id))
                ], limit=1)
                
                if transit_location:
                    # FORCE override destination location ke transit
                    vals['location_dest_id'] = transit_location.id
                    _logger.info(f"TSOUT Create: Set destination to transit location: {transit_location.name}")
        
        return super(StockPicking, self).create(vals)

    def button_validate(self):
        """
        Override button_validate to create TSIN automatically when validating TSOUT
        """
        for picking in self:
            _logger.info(f"=== Button Validate called for {picking.name} ===")
            _logger.info(f"Picking Type: {picking.picking_type_id.name} (code: {picking.picking_type_id.code})")
            _logger.info(f"Picking Type Name contains TSOUT: {'TSOUT' in picking.picking_type_id.name}")
            _logger.info(f"Target Location: {picking.target_location.name if picking.target_location else 'NOT SET'}")
            _logger.info(f"Destination Location: {picking.location_dest_id.name if picking.location_dest_id else 'NOT SET'}")
            _logger.info(f"Destination Usage: {picking.location_dest_id.usage if picking.location_dest_id else 'NOT SET'}")
            
            # Check if the operation type is 'Internal Transfers'
            if picking.picking_type_id.code == 'internal':
                # Check if the source and destination locations are the same
                if picking.location_id.id == picking.location_dest_id.id:
                    raise UserError("Cannot validate this operation: Source and destination locations are the same.")
            
            # 🔥 Auto create TSIN when validating TSOUT
            is_tsout = picking.picking_type_id.code == 'outgoing' and 'TSOUT' in picking.picking_type_id.name
            
            _logger.info(f"Is TSOUT: {is_tsout}")
            
            if is_tsout:
                _logger.info("=== TSOUT Detected ===")
                
                # Validasi target_location harus diisi
                if not picking.target_location:
                    raise UserError("Target Location must be set before validating TSOUT.")
                
                _logger.info(f"Target Location found: {picking.target_location.name}")
                _logger.info(f"Will create TSIN from {picking.location_dest_id.name} to {picking.target_location.name}")
        
        # Validate semua picking first
        _logger.info("Calling super().button_validate()...")
        res = super(StockPicking, self).button_validate()
        _logger.info("super().button_validate() completed")
        
        # Setelah validate, create TSIN untuk yang TSOUT
        for picking in self:
            is_tsout = picking.picking_type_id.code == 'outgoing' and 'TSOUT' in picking.picking_type_id.name
            
            if is_tsout and picking.target_location and picking.state == 'done':
                _logger.info(f"Creating TSIN for validated TSOUT {picking.name}...")
                try:
                    picking._create_ts_in_transfer()
                except Exception as e:
                    _logger.error(f"Failed to create TSIN: {str(e)}")
                    # Tetap tampilkan error ke user
                    raise UserError(f"TSOUT validated but failed to create TSIN: {str(e)}")
        
        return res

    def _create_ts_in_transfer(self):
        """
        Create TSIN transfer automatically from TSOUT
        location_id = Transit location (from TSOUT location_dest_id)
        location_dest_id = target_location (from TSOUT)
        """
        self.ensure_one()
        
        _logger.info(f"=== Creating TSIN for TSOUT {self.name} ===")
        
        # Validasi: pastikan target_location sudah diisi
        if not self.target_location:
            raise UserError("Target Location must be set before validating TSOUT.")
        
        _logger.info(f"Source (Transit): {self.location_dest_id.name} (ID: {self.location_dest_id.id})")
        _logger.info(f"Destination (Target): {self.target_location.name} (ID: {self.target_location.id})")
        
        # Ambil warehouse dari target_location
        target_warehouse = None
        if self.target_location.warehouse_id:
            target_warehouse = self.target_location.warehouse_id
            _logger.info(f"Target Warehouse from location: {target_warehouse.name} (ID: {target_warehouse.id})")
        else:
            _logger.warning(f"Target location {self.target_location.name} has no warehouse!")
        
        # Find TSIN operation type (incoming) berdasarkan warehouse dari target_location
        domain = [
            ('code', '=', 'incoming'),
            ('name', 'ilike', 'TSIN'),
        ]
        
        # Cari TSIN dengan warehouse dari target_location
        if target_warehouse:
            domain.append(('warehouse_id', '=', target_warehouse.id))
            _logger.info(f"Searching TSIN with warehouse filter: {target_warehouse.name}")
        
        ts_in_type = self.env['stock.picking.type'].search(domain, limit=1)
        
        # Jika tidak ketemu, coba cari tanpa warehouse filter
        if not ts_in_type:
            _logger.warning("TSIN not found with warehouse filter, searching without warehouse...")
            ts_in_type = self.env['stock.picking.type'].search([
                ('code', '=', 'incoming'),
                ('name', 'ilike', 'TSIN'),
            ], limit=1)
        
        if not ts_in_type:
            error_msg = "TSIN operation type not found. Please create an operation type with:\n"
            error_msg += "- Code: Incoming\n"
            error_msg += "- Name: (contains 'TSIN')\n"
            if target_warehouse:
                error_msg += f"- Warehouse: {target_warehouse.name}"
            _logger.error(error_msg)
            raise UserError(error_msg)
        
        _logger.info(f"TSIN Operation Type found: {ts_in_type.name} (ID: {ts_in_type.id})")
        
        # Prepare picking values
        picking_vals = {
            'picking_type_id': ts_in_type.id,
            'location_id': self.location_dest_id.id,  # Transit location dari destination TSOUT
            'location_dest_id': self.target_location.id,  # Target Location dari TSOUT
            'origin': self.name,  # Reference ke TSOUT document
            'scheduled_date': fields.Datetime.now(),
            'stock_type': self.stock_type.id if self.stock_type else False,
            'target_location': False,  # TSIN tidak butuh target_location
            'related_picking_id': self.id,  # Link kembali ke TSOUT
        }
        
        _logger.info(f"Creating new picking with vals: {picking_vals}")
        
        # Create new picking
        new_picking = self.env['stock.picking'].create(picking_vals)
        _logger.info(f"TSIN created: {new_picking.name} (ID: {new_picking.id})")
        
        # Create move lines berdasarkan TSOUT moves
        move_count = 0
        for move in self.move_ids_without_package:
            move_vals = {
                'name': move.product_id.name,
                'product_id': move.product_id.id,
                'product_uom_qty': move.product_uom_qty,
                'product_uom': move.product_uom.id,
                'quantity': move.product_uom_qty,
                'picking_id': new_picking.id,
                'location_id': new_picking.location_id.id,
                'location_dest_id': new_picking.location_dest_id.id,
                'vit_line_number_sap': move.vit_line_number_sap if hasattr(move, 'vit_line_number_sap') else False,
            }
            new_move = self.env['stock.move'].create(move_vals)
            move_count += 1
            _logger.info(f"Created move line {move_count}: {move.product_id.name} - Qty: {move.product_uom_qty} (Move ID: {new_move.id})")
        
        # Confirm the picking to make it ready
        _logger.info("Confirming TSIN...")
        new_picking.action_confirm()
        _logger.info(f"TSIN state after confirm: {new_picking.state}")
        
        _logger.info("Assigning TSIN...")
        new_picking.action_assign()
        _logger.info(f"TSIN state after assign: {new_picking.state}")
        
        # Store reference to TSIN in TSOUT
        self.related_picking_id = new_picking.id
        _logger.info(f"=== TSIN {new_picking.name} created successfully ===")
        
        # Commit untuk memastikan data tersimpan
        self.env.cr.commit()
        
        # Return notification
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'TSIN Created',
                'message': f'TSIN document {new_picking.name} has been created automatically at {new_picking.location_dest_id.name}',
                'type': 'success',
                'sticky': True,
            }
        }


class StockMove(models.Model):
    _inherit = 'stock.move'

    vit_line_number_sap = fields.Integer(string='Line Number SAP')