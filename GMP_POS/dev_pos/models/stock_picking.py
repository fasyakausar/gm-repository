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
        if self.picking_type_id and self.picking_type_id.code == 'outgoing' and 'TSOUT' in self.picking_type_id.name:
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
        if vals.get('picking_type_id'):
            picking_type = self.env['stock.picking.type'].browse(vals['picking_type_id'])
            if picking_type and picking_type.code == 'outgoing' and 'TSOUT' in picking_type.name:
                transit_location = self.env['stock.location'].search([
                    ('usage', '=', 'transit'),
                    ('company_id', '=', vals.get('company_id', self.env.company.id))
                ], limit=1)
                
                if transit_location:
                    vals['location_dest_id'] = transit_location.id
                    _logger.info(f"TSOUT Create: Set destination to transit location: {transit_location.name}")
        
        picking = super(StockPicking, self).create(vals)
        
        if picking.picking_type_id.code == 'outgoing' and 'TSOUT' in picking.picking_type_id.name:
            transit_location = self.env['stock.location'].search([
                ('usage', '=', 'transit'),
                ('company_id', '=', picking.company_id.id)
            ], limit=1)
            
            if transit_location and picking.location_dest_id.id != transit_location.id:
                _logger.warning(f"TSOUT location_dest_id was changed! Forcing back to transit...")
                picking.with_context(skip_location_check=True).write({
                    'location_dest_id': transit_location.id
                })
                for move in picking.move_ids_without_package:
                    move.write({'location_dest_id': transit_location.id})
                _logger.info(f"TSOUT Create: FORCED destination to transit location: {transit_location.name}")
        
        return picking
    
    def write(self, vals):
        """
        Override write to prevent location_dest_id from being changed for TSOUT
        """
        res = super(StockPicking, self).write(vals)
        
        for picking in self:
            if picking.picking_type_id.code == 'outgoing' and 'TSOUT' in picking.picking_type_id.name:
                transit_location = self.env['stock.location'].search([
                    ('usage', '=', 'transit'),
                    ('company_id', '=', picking.company_id.id)
                ], limit=1)
                
                if transit_location and picking.location_dest_id.id != transit_location.id:
                    if not self.env.context.get('skip_location_check'):
                        _logger.warning(f"TSOUT destination changed to {picking.location_dest_id.name}, reverting to transit...")
                        super(StockPicking, picking).write({
                            'location_dest_id': transit_location.id
                        })
                        for move in picking.move_ids_without_package:
                            move.write({'location_dest_id': transit_location.id})
        
        return res

    def _get_transit_location_from_target(self):
        """
        Helper: Ambil location_transit dari warehouse milik target_location.
        - Ambil warehouse_id dari target_location
        - Ambil field location_transit dari warehouse tersebut
        - Fallback ke pencarian usage='transit' jika location_transit tidak diisi
        """
        self.ensure_one()

        if not self.target_location:
            raise UserError("Target Location belum diisi.")

        target_warehouse = self.target_location.warehouse_id

        if not target_warehouse:
            raise UserError(
                f"Target Location '{self.target_location.name}' tidak memiliki warehouse. "
                f"Pastikan location sudah terhubung ke warehouse."
            )

        _logger.info(f"Target Warehouse: {target_warehouse.name} (ID: {target_warehouse.id})")

        # ✅ Gunakan field custom location_transit dari warehouse
        transit_location = target_warehouse.location_transit

        if transit_location:
            _logger.info(f"Transit Location (dari field location_transit): {transit_location.name} (ID: {transit_location.id})")
            return transit_location

        # Fallback: cari stock.location dengan usage='transit' di bawah warehouse tersebut
        _logger.warning(
            f"Warehouse '{target_warehouse.name}' tidak memiliki location_transit. "
            f"Mencari fallback transit location..."
        )
        transit_location = self.env['stock.location'].search([
            ('usage', '=', 'transit'),
            ('company_id', '=', self.company_id.id),
        ], limit=1)

        if not transit_location:
            raise UserError(
                f"Transit Location tidak ditemukan untuk warehouse '{target_warehouse.name}'.\n\n"
                f"Silakan isi field 'Transit Location' di konfigurasi warehouse tersebut."
            )

        _logger.warning(f"Using fallback transit location: {transit_location.name}")
        return transit_location

    def button_validate(self):
        # =====================================================
        # VALIDASI ALLOWED WAREHOUSE
        # =====================================================
        current_user = self.env.user
        
        if current_user.allowed_warehouse_ids:
            allowed_ids = current_user.allowed_warehouse_ids.ids
            for picking in self:
                picking_warehouse = picking.picking_type_id.warehouse_id
                if not picking_warehouse:
                    continue
                if picking_warehouse.id not in allowed_ids:
                    raise UserError(
                        f"Anda tidak memiliki akses untuk memvalidasi transfer di warehouse "
                        f"'{picking_warehouse.name}'.\n\n"
                        f"Warehouse yang diizinkan: "
                        f"{', '.join(current_user.allowed_warehouse_ids.mapped('name'))}"
                    )

        # =====================================================
        # VALIDASI & SET TRANSIT LOCATION UNTUK TSOUT
        # =====================================================
        for picking in self:
            _logger.info(f"=== Button Validate called for {picking.name} ===")
            _logger.info(f"Picking Type: {picking.picking_type_id.name} (code: {picking.picking_type_id.code})")

            if picking.picking_type_id.code == 'internal':
                if picking.location_id.id == picking.location_dest_id.id:
                    raise UserError(
                        "Cannot validate this operation: "
                        "Source and destination locations are the same."
                    )

            is_tsout = (
                picking.picking_type_id.code == 'outgoing'
                and 'TSOUT' in picking.picking_type_id.name
            )

            if is_tsout:
                _logger.info("=== TSOUT Detected ===")

                if not picking.target_location:
                    raise UserError("Target Location harus diisi sebelum memvalidasi TSOUT.")

                transit_location = picking._get_transit_location_from_target()

                _logger.info(
                    f"TSOUT {picking.name}: Set location_dest_id → "
                    f"{transit_location.name} (ID: {transit_location.id})"
                )

                picking.with_context(skip_location_check=True).write({
                    'location_dest_id': transit_location.id
                })
                for move in picking.move_ids_without_package:
                    move.write({'location_dest_id': transit_location.id})

                _logger.info("location_dest_id updated successfully")

        # =====================================================
        # PATCH: Skip message_subscribe jika dipanggil dari API
        # =====================================================
        if self.env.context.get('skip_subscribe'):
            # Patch sementara: pastikan env.user.partner_id valid
            # Jika tidak valid (False), skip subscribe dengan monkey-patch context
            self = self.with_context(
                skip_sanity_check=False,
            )
            # Override message_subscribe sementara agar tidak error
            original_message_subscribe = self.__class__.message_subscribe

            def _safe_message_subscribe(self_inner, partner_ids=None, subtype_ids=None):
                # Filter out falsy partner_ids (False, None, 0)
                if partner_ids:
                    partner_ids = [pid for pid in partner_ids if pid]
                if not partner_ids:
                    return True
                return original_message_subscribe(self_inner, partner_ids=partner_ids, subtype_ids=subtype_ids)

            self.__class__.message_subscribe = _safe_message_subscribe
            try:
                res = super(StockPicking, self).button_validate()
            finally:
                # Restore original method
                self.__class__.message_subscribe = original_message_subscribe
        else:
            res = super(StockPicking, self).button_validate()

        # =====================================================
        # AUTO CREATE TSIN SETELAH TSOUT VALIDATED
        # =====================================================
        for picking in self:
            is_tsout = (
                picking.picking_type_id.code == 'outgoing'
                and 'TSOUT' in picking.picking_type_id.name
            )
            if is_tsout and picking.target_location and picking.state == 'done':
                _logger.info(f"Creating TSIN for validated TSOUT {picking.name}...")
                try:
                    picking._create_ts_in_transfer()
                except Exception as e:
                    _logger.error(f"Failed to create TSIN: {str(e)}")
                    raise UserError(f"TSOUT validated but failed to create TSIN: {str(e)}")

        return res

    def _create_ts_in_transfer(self):
        """
        Create TSIN transfer automatically from TSOUT.
        - location_id      = location_transit dari warehouse target_location (= location_dest_id TSOUT)
        - location_dest_id = target_location dari TSOUT
        """
        self.ensure_one()
        
        _logger.info(f"=== Creating TSIN for TSOUT {self.name} ===")
        
        if not self.target_location:
            raise UserError("Target Location harus diisi sebelum membuat TSIN.")

        # Transit location sudah di-set ke location_dest_id saat button_validate
        transit_location = self.location_dest_id
        _logger.info(f"Source TSIN (Transit)     : {transit_location.name} (ID: {transit_location.id})")
        _logger.info(f"Destination TSIN (Target) : {self.target_location.name} (ID: {self.target_location.id})")

        # Ambil warehouse dari target_location untuk mencari operation type TSIN
        target_warehouse = self.target_location.warehouse_id
        if not target_warehouse:
            raise UserError(
                f"Target Location '{self.target_location.name}' tidak memiliki warehouse."
            )

        _logger.info(f"Target Warehouse: {target_warehouse.name} (ID: {target_warehouse.id})")

        # Cari operation type TSIN di warehouse target
        domain = [
            ('code', '=', 'incoming'),
            ('name', 'ilike', 'TSIN'),
            ('warehouse_id', '=', target_warehouse.id),
        ]
        ts_in_type = self.env['stock.picking.type'].search(domain, limit=1)

        # Fallback tanpa filter warehouse
        if not ts_in_type:
            _logger.warning("TSIN not found with warehouse filter, searching without warehouse...")
            ts_in_type = self.env['stock.picking.type'].search([
                ('code', '=', 'incoming'),
                ('name', 'ilike', 'TSIN'),
            ], limit=1)

        if not ts_in_type:
            raise UserError(
                f"Operation type TSIN tidak ditemukan.\n\n"
                f"Pastikan sudah ada operation type dengan:\n"
                f"- Code: Incoming\n"
                f"- Nama mengandung 'TSIN'\n"
                f"- Warehouse: {target_warehouse.name}"
            )

        _logger.info(f"TSIN Operation Type: {ts_in_type.name} (ID: {ts_in_type.id})")

        # Buat picking TSIN
        picking_vals = {
            'picking_type_id': ts_in_type.id,
            'location_id': transit_location.id,       # Transit dari warehouse target
            'location_dest_id': self.target_location.id,  # Target location TSOUT
            'origin': self.name,
            'scheduled_date': fields.Datetime.now(),
            'stock_type': self.stock_type.id if self.stock_type else False,
            'target_location': False,
            'related_picking_id': self.id,
        }

        new_picking = self.env['stock.picking'].create(picking_vals)
        _logger.info(f"TSIN created: {new_picking.name} (ID: {new_picking.id})")

        # Buat move lines dari TSOUT
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
            self.env['stock.move'].create(move_vals)
            _logger.info(f"Move created: {move.product_id.name} - Qty: {move.product_uom_qty}")

        # Confirm & assign
        new_picking.action_confirm()
        _logger.info(f"TSIN state after confirm: {new_picking.state}")
        new_picking.action_assign()
        _logger.info(f"TSIN state after assign: {new_picking.state}")

        # Link balik ke TSOUT
        self.related_picking_id = new_picking.id
        _logger.info(f"=== TSIN {new_picking.name} created successfully ===")

        self.env.cr.commit()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'TSIN Created',
                'message': (
                    f'Dokumen TSIN {new_picking.name} berhasil dibuat '
                    f'di {new_picking.location_dest_id.name}'
                ),
                'type': 'success',
                'sticky': True,
            }
        }


class StockMove(models.Model):
    _inherit = 'stock.move'

    vit_line_number_sap = fields.Integer(string='Line Number SAP')