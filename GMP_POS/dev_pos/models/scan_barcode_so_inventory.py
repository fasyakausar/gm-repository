from odoo import models, fields, api
from odoo.exceptions import ValidationError

class SaleOrder(models.Model):
    _inherit = 'sale.order'
    
    barcode_input = fields.Char(string="Scan Barcode", readonly=False)
    
    def _get_next_sequence(self):
        """Get the next highest sequence number"""
        if self.order_line:
            max_seq = max(self.order_line.mapped('sequence') or [0])
            return max_seq + 1
        return 1
    
    @api.onchange('barcode_input')
    def _onchange_barcode_input(self):
        """
        Auto-create sale.order.line based on scanned barcode
        """
        if not self.barcode_input:
            return
        
        # Validasi: hanya bisa scan saat state draft atau sent
        if self.state not in ['draft', 'sent']:
            raise ValidationError("Barcode scanning hanya diperbolehkan pada status Draft atau Quotation Sent.")
        
        barcode_value = self.barcode_input.strip()
        
        # ✅ Cari produk berdasarkan barcode
        product = self.env['product.product'].search([
            ('barcode', '=', barcode_value),
            ('sale_ok', '=', True)
        ], limit=1)
        
        if not product:
            raise ValidationError(f"❌ Produk dengan barcode '{barcode_value}' tidak ditemukan atau tidak tersedia untuk dijual.")
        
        # Cek apakah sudah ada line dengan produk yang sama
        existing_line = self.order_line.filtered(
            lambda l: l.product_id.id == product.id and not l.display_type
        )
        
        # Dapatkan sequence tertinggi untuk line baru
        next_seq = self._get_next_sequence()
        
        if existing_line:
            # ✅ Update existing line: tambah qty dan update sequence agar muncul di atas
            new_commands = []
            
            for line in self.order_line:
                if line.id == existing_line[0].id or (not line.id and line == existing_line[0]):
                    # Update existing line dengan qty baru dan sequence tertinggi
                    if line.id:
                        new_commands.append((1, line.id, {
                            'product_uom_qty': line.product_uom_qty + 1.0,
                            'sequence': next_seq,
                        }))
                    else:
                        # Untuk new record (belum disave)
                        line.product_uom_qty += 1.0
                        line.sequence = next_seq
                        new_commands.append((4, line.id, 0))
                else:
                    # Keep other lines
                    if line.id:
                        new_commands.append((4, line.id, 0))
                    else:
                        new_commands.append((4, line.id, 0))
            
            if new_commands:
                self.order_line = new_commands
        else:
            # ✅ Buat line baru di posisi paling atas
            new_commands = [(0, 0, {
                'product_id': product.id,
                'product_uom_qty': 1.0,
                'product_uom': product.uom_id.id,
                'price_unit': product.list_price,
                'sequence': next_seq,
            })]
            
            # Tambahkan semua existing lines
            for line in self.order_line:
                if line.id:
                    new_commands.append((4, line.id, 0))
                else:
                    new_commands.append((4, line.id, 0))
            
            self.order_line = new_commands
        
        # Reset input
        self.barcode_input = ''

class StockPicking(models.Model):
    _inherit = 'stock.picking'
    
    barcode_input = fields.Char(string="Scan Barcode", readonly=False)
    
    def _get_next_sequence(self):
        """Get the next highest sequence number"""
        if self.move_ids_without_package:
            max_seq = max(self.move_ids_without_package.mapped('sequence') or [0])
            return max_seq + 1
        return 1
    
    @api.onchange('barcode_input')
    def _onchange_barcode_input(self):
        """
        Auto-create stock.move based on scanned barcode
        Hanya untuk operation type dengan name TSOUT atau TSIN
        """
        if not self.barcode_input:
            return
        
        # ✅ Validasi: hanya untuk operation type dengan name TSOUT atau TSIN
        if not self.picking_type_id or self.picking_type_id.name not in ['TSOUT', 'TSIN']:
            raise ValidationError("Barcode scanning hanya diperbolehkan untuk Operation Type TSOUT atau TSIN.")
        
        # Validasi: hanya bisa scan saat state draft, waiting, confirmed, atau assigned
        if self.state not in ['draft', 'waiting', 'confirmed', 'assigned']:
            raise ValidationError("Barcode scanning hanya diperbolehkan pada status Draft, Waiting, Confirmed, atau Ready.")
        
        barcode_value = self.barcode_input.strip()
        
        # ✅ Cari produk berdasarkan barcode
        product = self.env['product.product'].search([
            ('barcode', '=', barcode_value)
        ], limit=1)
        
        if not product:
            raise ValidationError(f"❌ Produk dengan barcode '{barcode_value}' tidak ditemukan.")
        
        # Cek apakah sudah ada move dengan produk yang sama
        existing_move = self.move_ids_without_package.filtered(
            lambda m: m.product_id.id == product.id
        )
        
        # Dapatkan sequence tertinggi untuk move baru
        next_seq = self._get_next_sequence()
        
        if existing_move:
            # ✅ Update existing move: tambah qty dan update sequence agar muncul di atas
            new_commands = []
            
            for move in self.move_ids_without_package:
                if move.id == existing_move[0].id or (not move.id and move == existing_move[0]):
                    # Update existing move dengan qty baru dan sequence tertinggi
                    if move.id:
                        new_commands.append((1, move.id, {
                            'product_uom_qty': move.product_uom_qty + 1.0,
                            'sequence': next_seq,
                        }))
                    else:
                        # Untuk new record (belum disave)
                        move.product_uom_qty += 1.0
                        move.sequence = next_seq
                        new_commands.append((4, move.id, 0))
                else:
                    # Keep other moves
                    if move.id:
                        new_commands.append((4, move.id, 0))
                    else:
                        new_commands.append((4, move.id, 0))
            
            if new_commands:
                self.move_ids_without_package = new_commands
        else:
            # ✅ Buat move baru di posisi paling atas
            new_commands = [(0, 0, {
                'name': product.name,
                'product_id': product.id,
                'product_uom_qty': 1.0,
                'product_uom': product.uom_id.id,
                'location_id': self.location_id.id,
                'location_dest_id': self.location_dest_id.id,
                'picking_id': self.id,
                'sequence': next_seq,
            })]
            
            # Tambahkan semua existing moves
            for move in self.move_ids_without_package:
                if move.id:
                    new_commands.append((4, move.id, 0))
                else:
                    new_commands.append((4, move.id, 0))
            
            self.move_ids_without_package = new_commands
        
        # Reset input
        self.barcode_input = ''