from odoo import models, fields, api
from pytz import timezone
from datetime import datetime, timedelta
from odoo.exceptions import ValidationError

class InventoryAdjustment(models.Model):
    _inherit = 'stock.quant'

    doc_num = fields.Many2one(
        'inventory.stock', 
        string="Inventory Counting",
        domain="[('state', '=', 'closed')]"
    )

    @api.onchange('doc_num')
    def _onchange_doc_num(self):
        """Auto-fill inventory_quantity ketika doc_num dipilih"""
        if self.doc_num and self.product_id:
            if self.doc_num.state != 'closed':
                raise ValidationError("Hanya Inventory Counting dengan status 'Closed' yang bisa dipilih.")
            
            inventory_counting_line = self.doc_num.inventory_counting_ids.filtered(
                lambda line: line.product_id.id == self.product_id.id 
                and line.location_id.id == self.location_id.id
                and (line.lot_id.id == self.lot_id.id if self.lot_id else not line.lot_id)
            )
            
            if inventory_counting_line:
                line = inventory_counting_line[0]
                self.inventory_quantity = line.difference_qty
                self.inventory_quantity_set = True

    def action_apply_inventory(self):
        """Override untuk mengisi inventory_quantity dari doc_num"""
        for quant in self:
            if quant.doc_num:
                if quant.doc_num.state != 'closed':
                    raise ValidationError(
                        f"Inventory Counting '{quant.doc_num.doc_num}' harus berstatus 'Closed' "
                        "sebelum dapat diaplikasikan."
                    )
                
                inventory_stock = quant.doc_num
                
                inventory_counting_line = inventory_stock.inventory_counting_ids.filtered(
                    lambda line: line.product_id.id == quant.product_id.id 
                    and line.location_id.id == quant.location_id.id
                    and (line.lot_id.id == quant.lot_id.id if quant.lot_id else not line.lot_id)
                )
                
                if inventory_counting_line:
                    line = inventory_counting_line[0]
                    quant.inventory_quantity = line.difference_qty
                    quant.inventory_quantity_set = True
        
        return super(InventoryAdjustment, self).action_apply_inventory()


class InventoryStock(models.Model):
    _name = "inventory.stock"
    _description = "Inventory Stock"
    _rec_name = 'doc_num'

    doc_num = fields.Char(string="Internal Reference", readonly=True)
    warehouse_id = fields.Many2one('stock.warehouse', string="Warehouse")
    location_id = fields.Many2one('stock.location', string="Location")
    company_id = fields.Many2one('res.company', string="Company")
    create_date = fields.Datetime(string="Created Date", readonly=True)
    from_date = fields.Datetime(string="From Date")
    to_date = fields.Datetime(string="To Date")
    inventory_date = fields.Datetime(string="Inventory Date")
    total_qty = fields.Float(string="Total Product Quantity", compute='_compute_total_quantity')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('counted', 'Counted'),
        ('closed', 'Closed'),
    ], string='Status', default='draft', required=True, readonly=True, copy=False, tracking=True)
    inventory_counting_ids = fields.One2many(
        'inventory.counting', 
        'inventory_counting_id', 
        string='Inventory Countings', 
        order='sequence desc, id desc'
    )
    barcode_input = fields.Char(string="Scan Barcode", readonly=False)
    is_integrated = fields.Boolean(string="Integrated", default=False, readonly=True, tracking=True)
    vit_notes = fields.Text(string="Keterangan", readonly=False, tracking=True)

    @api.depends('inventory_counting_ids.counted_qty')
    def _compute_total_quantity(self):
        """Compute total quantity dari semua counting lines"""
        for record in self:
            record.total_qty = sum(record.inventory_counting_ids.mapped('counted_qty'))

    def action_apply_to_stock_quant(self):
        """
        Method untuk mengaplikasikan inventory counting ke stock.quant
        """
        self.ensure_one()
        
        if self.state != 'counted':
            raise ValidationError("Inventory harus dalam status 'Counted' sebelum diaplikasikan.")
        
        StockQuant = self.env['stock.quant']
        applied_count = 0
        
        for line in self.inventory_counting_ids:
            # Cari stock.quant yang sesuai
            quant = StockQuant.search([
                ('product_id', '=', line.product_id.id),
                ('location_id', '=', line.location_id.id),
                ('lot_id', '=', line.lot_id.id if line.lot_id else False),
                ('package_id', '=', False),
                ('owner_id', '=', False),
            ], limit=1)
            
            if quant:
                # Update quant yang sudah ada
                quant.write({
                    'doc_num': line.inventory_stock_id.id,
                    'inventory_quantity': line.counted_qty,
                    'inventory_quantity_set': True,
                    'inventory_date': line.inventory_date or fields.Date.today(),
                    'user_id': self.env.user.id,
                })
                applied_count += 1
            else:
                # Buat quant baru dalam inventory mode
                StockQuant.with_context(inventory_mode=True).create({
                    'product_id': line.product_id.id,
                    'location_id': line.location_id.id,
                    'lot_id': line.lot_id.id if line.lot_id else False,
                    'doc_num': line.inventory_stock_id.id,
                    'inventory_quantity': line.counted_qty,
                    'inventory_quantity_set': True,
                    'inventory_date': line.inventory_date or fields.Date.today(),
                    'user_id': self.env.user.id,
                })
                applied_count += 1
        
        # Update status
        self.is_integrated = True
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Berhasil',
                'message': f'Inventory counting berhasil diaplikasikan ke {applied_count} stock quant(s).',
                'type': 'success',
                'sticky': False,
            }
        }

    def _get_next_sequence(self):
        """Get the next highest sequence number"""
        if self.inventory_counting_ids:
            max_seq = max(self.inventory_counting_ids.mapped('sequence') or [0])
            return max_seq + 1
        return 1

    @api.model
    def default_get(self, fields_list):
        """Override default_get to automatically populate certain fields"""
        res = super(InventoryStock, self).default_get(fields_list)
        
        # Set default create_date and inventory_date to current datetime
        current_datetime = fields.Datetime.now()
        if 'create_date' in fields_list:
            res['create_date'] = current_datetime
        if 'inventory_date' in fields_list:
            res['inventory_date'] = current_datetime
        
        # Set default company_id
        if 'company_id' in fields_list:
            res['company_id'] = self.env.company.id
        
        # Set default warehouse
        if 'warehouse_id' in fields_list:
            warehouse = self.env['stock.warehouse'].search([
                ('company_id', '=', self.env.company.id)
            ], limit=1)
            if warehouse:
                res['warehouse_id'] = warehouse.id
                
                if 'location_id' in fields_list and warehouse.view_location_id:
                    stock_location = self.env['stock.location'].search([
                        ('location_id', '=', warehouse.view_location_id.id),
                        ('name', '=', 'Stock')
                    ], limit=1)
                    if stock_location:
                        res['location_id'] = stock_location.id
        
        return res

    @api.onchange('barcode_input')
    def _onchange_barcode_input(self):
        """
        Auto-create inventory.counting record based on scanned barcode
        Langsung menggunakan barcode dari product.product
        """
        if not self.barcode_input:
            return

        barcode_value = self.barcode_input.strip()

        # ✅ Cari produk berdasarkan barcode (langsung dari product.product)
        product = self.env['product.product'].search([
            ('barcode', '=', barcode_value)
        ], limit=1)

        if not product:
            raise ValidationError(f"❌ Produk dengan barcode '{barcode_value}' tidak ditemukan.")

        # Cek apakah sudah ada line dengan produk yang sama
        existing_line = self.inventory_counting_ids.filtered(
            lambda l: l.product_id.id == product.id and l.location_id.id == self.location_id.id
        )

        # Dapatkan sequence tertinggi untuk line baru
        next_seq = self._get_next_sequence()

        if existing_line:
            # ✅ Update existing line: tambah qty dan update sequence agar muncul di atas
            new_commands = []
            
            for line in self.inventory_counting_ids:
                if line.id == existing_line[0].id or (not line.id and line == existing_line[0]):
                    # Update existing line dengan qty baru dan sequence tertinggi
                    if line.id:
                        new_commands.append((1, line.id, {
                            'counted_qty': line.counted_qty + 1.0,
                            'sequence': next_seq,
                        }))
                    else:
                        # Untuk new record (belum disave)
                        line.counted_qty += 1.0
                        line.sequence = next_seq
                        new_commands.append((4, line.id, 0))
                else:
                    # Keep other lines
                    if line.id:
                        new_commands.append((4, line.id, 0))
            
            if new_commands:
                self.inventory_counting_ids = new_commands
        else:
            # ✅ Buat line baru di posisi paling atas
            new_commands = [(0, 0, {
                'product_id': product.id,
                'location_id': self.location_id.id,
                'inventory_date': self.inventory_date,
                'state': 'in_progress',
                'uom_id': product.uom_id.id,
                'counted_qty': 1.0,
                'sequence': next_seq,
            })]
            
            # Tambahkan semua existing lines
            for line in self.inventory_counting_ids:
                if line.id:
                    new_commands.append((4, line.id, 0))
            
            self.inventory_counting_ids = new_commands

        # Reset input
        self.barcode_input = ''

    @api.onchange('location_id')
    def _onchange_location_id(self):
        """Update location_id in all inventory counting lines when parent location changes"""
        if self.location_id:
            for line in self.inventory_counting_ids:
                line.location_id = self.location_id

    def write(self, vals):
        """Override write untuk update create_date saat ada perubahan data"""
        for record in self:
            if record.state != 'draft' and vals:
                if 'state' not in vals or len(vals) > 1:
                    vals['create_date'] = fields.Datetime.now()
        
        return super(InventoryStock, self).write(vals)

    @api.model
    def create(self, vals):
        """Override create method to automatically generate doc_num using sequence"""
        sequence_code = 'inventory.stock.doc.num'
        doc_num_seq = self.env['ir.sequence'].next_by_code(sequence_code)

        inventory_date = vals.get('inventory_date') or fields.Datetime.now()

        # Timezone handling
        user_tz = timezone(self.env.user.tz or 'UTC')
        current_datetime = datetime.strptime(inventory_date, '%Y-%m-%d %H:%M:%S') if isinstance(inventory_date, str) else inventory_date
        current_datetime = current_datetime.astimezone(user_tz)

        date_str = current_datetime.strftime("%Y%m%d")
        time_str = current_datetime.strftime("%H%M%S")

        INC = "INC"

        vals['doc_num'] = f"{INC}/{date_str}/{time_str}/{doc_num_seq}"
        vals['create_date'] = fields.Datetime.now()

        record = super(InventoryStock, self).create(vals)
        return record
    
    @api.onchange('warehouse_id')
    def _onchange_warehouse_id(self):
        """Auto-fill location_id berdasarkan warehouse_id"""
        if self.warehouse_id:
            root_location = self.warehouse_id.view_location_id
            
            if root_location:
                child_locations = self.env['stock.location'].search([
                    ('location_id', '=', root_location.id),
                    ('name', '=', "Stock")
                ])
                self.location_id = child_locations
            else:
                self.location_id = False
        else:
            self.location_id = False

    def action_in_progress(self):
        """Set status to in_progress"""
        for record in self:
            record.state = 'in_progress'
            record.barcode_input = ''
            for line in record.inventory_counting_ids:
                line.write({'state': 'in_progress'})
        
        return {
            'name': 'Inventory Counting',
            'type': 'ir.actions.act_window',
            'res_model': 'inventory.stock',
            'view_mode': 'form',
            'res_id': self.id,
            'context': {'default_focus': 1},
        }

    def action_view_inventory_counting(self):
        """Open inventory.counting records"""
        self.ensure_one()
        domain = [('inventory_stock_id', '=', self.id)]

        return {
            'name': 'Inventory Counting',
            'type': 'ir.actions.act_window',
            'res_model': 'inventory.counting',
            'view_mode': 'tree',
            'domain': domain,
            'context': {'create': False},
        }

    def action_counted(self):
        """
        ✅ SIMPLIFIED: Set status to counted
        Hitung qty_hand dari stock.quant untuk setiap line
        """
        for record in self:
            if record.state != 'in_progress':
                raise ValidationError("Hanya inventory dengan status 'In Progress' yang bisa di-counted.")
            
            record.state = 'counted'
            
            for line in record.inventory_counting_ids:
                line.state = 'counted'
                line.is_edit = False
                line.inventory_date = record.inventory_date
                
                # ✅ Hitung qty_hand dari stock.quant
                quant = self.env['stock.quant'].search([
                    ('product_id', '=', line.product_id.id),
                    ('location_id', '=', line.location_id.id),
                    ('lot_id', '=', line.lot_id.id if line.lot_id else False),
                ], limit=1)
                
                if quant:
                    line.qty_hand = quant.quantity
                else:
                    line.qty_hand = 0.0
        
        return True

    def action_closed(self):
        """Ubah status menjadi closed"""
        for record in self:
            if record.state != 'counted':
                raise ValidationError("Hanya inventory dengan status 'Counted' yang bisa di-closed.")
            
            record.state = 'closed'
            for line in record.inventory_counting_ids:
                line.state = 'closed'
        
        return True


class InventoryCounting(models.Model):
    _name = "inventory.counting"
    _description = "Inventory Counting"
    _order = 'sequence desc, id desc'

    inventory_counting_id = fields.Many2one('inventory.stock', string="Inventory Counting")
    inventory_stock_id = fields.Many2one('inventory.stock', string="Inventory Stock", ondelete='cascade')
    product_id = fields.Many2one('product.product', string="Product")
    location_id = fields.Many2one('stock.location', string="Location")
    inventory_date = fields.Datetime(string="Inventory Date")
    lot_id = fields.Many2one('stock.lot', string="Lot/Serial Number")
    expiration_date = fields.Datetime(string="Expiration Date")
    qty_hand = fields.Float(string="On Hand", store=True)
    counted_qty = fields.Float(string="Counted", store=True)
    difference_qty = fields.Float(string="Difference", compute='_compute_difference_qty', store=True)
    uom_id = fields.Many2one('uom.uom', string="UOM")
    state = fields.Selection([
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('counted', 'Counted'),
        ('closed', 'Closed'),
    ], string='Status', default='draft', required=True, readonly=True, copy=False, tracking=True)
    is_edit = fields.Boolean(string="Edit")
    sequence = fields.Integer(string="Sequence", default=0)

    @api.onchange('product_id')
    def _onchange_product_id(self):
        """Auto-set location_id dan uom_id dari parent inventory.stock"""
        if self.product_id and self.inventory_counting_id:
            if self.inventory_counting_id.location_id:
                self.location_id = self.inventory_counting_id.location_id
                self.uom_id = self.product_id.uom_id.id

    @api.depends('qty_hand', 'counted_qty')
    def _compute_difference_qty(self):
        for record in self:
            record.difference_qty = record.counted_qty - record.qty_hand