from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════
# 1. res.users — allowed warehouses
# ══════════════════════════════════════════════════════════
class ResUsers(models.Model):
    _inherit = 'res.users'

    allowed_warehouse_ids = fields.Many2many(
        comodel_name='stock.warehouse',
        relation='res_users_warehouse_rel',
        column1='user_id',
        column2='warehouse_id',
        string='Allowed Warehouses',
        help='Daftar gudang yang boleh dipakai user ini saat membuat Sale Order. '
             'Kosongkan jika user boleh mengakses semua warehouse.',
    )


# ══════════════════════════════════════════════════════════
# 2. Wizard: pilih warehouse
# ══════════════════════════════════════════════════════════
class SaleWarehouseWizard(models.TransientModel):
    _name = 'sale.warehouse.wizard'
    _description = 'Pilih Warehouse untuk Sale Order Baru'

    warehouse_id = fields.Many2one(
        comodel_name='stock.warehouse',
        string='Warehouse',
        required=True,
    )
    allowed_warehouse_ids = fields.Many2many(
        comodel_name='stock.warehouse',
        string='Allowed Warehouses',
    )

    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        allowed = self.env.user.sudo().allowed_warehouse_ids.filtered(
            lambda w: w.company_id.id == self.env.company.id
        )
        warehouses = allowed if allowed else self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)]
        )
        if warehouses:
            res['allowed_warehouse_ids'] = [(6, 0, warehouses.ids)]
            res['warehouse_id'] = warehouses[0].id
        return res

    def action_confirm(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sale Order Baru'),
            'res_model': 'sale.order',
            'view_mode': 'form',
            'views': [(self.env.ref('sale.view_order_form').id, 'form')],
            'target': 'current',
            'context': {
                **self.env.context,
                'default_warehouse_id': self.warehouse_id.id,
            },
        }

    def action_cancel(self):
        return {'type': 'ir.actions.act_window_close'}


# ══════════════════════════════════════════════════════════
# 3. sale.order
# ══════════════════════════════════════════════════════════
class SaleOrder(models.Model):
    _inherit = 'sale.order'

    customer_info = fields.Many2one(
        comodel_name='res.company',
        string='Customer Company',
        readonly=False,
    )
    is_cashier = fields.Boolean(
        string='Is Cashier',
        compute='_compute_is_cashier',
    )

    # DUMMY FIELD untuk menghindari error jika modul mrp tidak terinstal
    mrp_production_count = fields.Integer(
        string='Manufacturing Orders',
        compute='_compute_mrp_production_count_safe',
        store=False,
    )

    # ── helper untuk mencari pos.config berdasarkan warehouse (dengan sudo) ──
    def _get_pos_config_by_warehouse(self, warehouse=None):
        """
        Mencari pos.config yang terhubung dengan warehouse tertentu.
        Menggunakan sudo() agar user non-admin bisa membaca pos.config.
        Urutan pencarian:
        1. Berdasarkan warehouse_id eksak.
        2. Berdasarkan nama/kode warehouse dari pos_config.warehouse_id.
        3. Berdasarkan nama pos_config yang cocok dengan code/nama warehouse.
        4. Berdasarkan operation type (picking_type_id.name).
        Returns: pos.config record atau False.
        """
        if not warehouse and self.warehouse_id:
            warehouse = self.warehouse_id
        if not warehouse:
            return False

        PosConfig = self.env['pos.config'].sudo()

        # 1. Cari berdasarkan warehouse_id eksak
        pos_config = PosConfig.search([
            ('warehouse_id', '=', warehouse.id),
            ('company_id', '=', self.company_id.id),
            ('active', '=', True),
        ], limit=1)
        if pos_config:
            return pos_config

        wh_name = (warehouse.name or '').strip().lower()
        wh_code = (warehouse.code or '').strip().lower()

        # 2. Cari berdasarkan nama/kode warehouse dari pos_config.warehouse_id
        all_configs = PosConfig.search([
            ('company_id', '=', self.company_id.id),
            ('active', '=', True),
        ])
        for pc in all_configs:
            wh = pc.warehouse_id
            if wh:
                pc_wh_name = (wh.name or '').strip().lower()
                pc_wh_code = (wh.code or '').strip().lower()
                if pc_wh_name == wh_name or pc_wh_code == wh_code:
                    _logger.warning(
                        "Fallback (by warehouse name/code): warehouse '%s' (id=%d) menggunakan pos.config '%s' (warehouse_id=%d)",
                        warehouse.name, warehouse.id, pc.name, pc.warehouse_id.id
                    )
                    return pc

        # 3. Cari berdasarkan nama pos_config yang cocok dengan code warehouse atau nama warehouse
        for pc in all_configs:
            pc_name = (pc.name or '').strip().lower()
            if pc_name == wh_code or pc_name == wh_name or (wh_code and pc_name == wh_code) or (wh_name and wh_name in pc_name):
                _logger.warning(
                    "Fallback (by pos_config name): warehouse '%s' (id=%d) menggunakan pos.config '%s' (warehouse_id=%d)",
                    warehouse.name, warehouse.id, pc.name, pc.warehouse_id.id
                )
                return pc

        # 4. Cari berdasarkan operation type (picking_type_id) yang namanya cocok dengan warehouse code/name
        for pc in all_configs:
            picking_type = pc.picking_type_id
            if picking_type:
                pt_name = (picking_type.name or '').strip().lower()
                if (wh_code and wh_code in pt_name) or (wh_name and wh_name in pt_name):
                    _logger.warning(
                        "Fallback (by picking type): warehouse '%s' (id=%d) menggunakan pos.config '%s' via picking type '%s'",
                        warehouse.name, warehouse.id, pc.name, picking_type.name
                    )
                    return pc

        _logger.warning("Tidak ada pos.config untuk warehouse '%s' (id=%d)", warehouse.name, warehouse.id)
        return False

    @api.depends_context('uid')
    def _compute_is_cashier(self):
        is_cashier = self.env.user.has_group('dev_pos.group_sale_cashier')
        for order in self:
            order.is_cashier = is_cashier

    def _compute_mrp_production_count_safe(self):
        """Set nilai 0 jika modul mrp tidak aktif, atau biarkan method asli jika ada."""
        if hasattr(super(SaleOrder, self), '_compute_mrp_production_count'):
            try:
                super(SaleOrder, self)._compute_mrp_production_count()
            except Exception:
                for order in self:
                    order.mrp_production_count = 0
        else:
            for order in self:
                order.mrp_production_count = 0

    # ── helper mapping tax ────────────────────────────────
    def _get_mapping_tax_for_warehouse(self, warehouse):
        if not warehouse:
            return False
        return self.env['mapping.tax'].search([
            ('gm_warehouse_id', '=', warehouse.id)
        ], limit=1)

    def _validate_bp_tax_vs_mapping(self, partner, warehouse):
        if not partner or not warehouse:
            return None, False, ''

        mapping = self._get_mapping_tax_for_warehouse(warehouse)
        if not mapping:
            return None, False, ''

        mapping_tax = mapping.gm_tax_code
        if not mapping_tax:
            return None, False, ''

        return True, mapping_tax, ''

    # ── validasi untuk create/write ───────────────────────
    def _check_line_tax_vs_mapping(self, partner_id, warehouse_id, order_lines_vals):
        partner = self.env['res.partner'].browse(partner_id) if partner_id else False
        warehouse = self.env['stock.warehouse'].browse(warehouse_id) if warehouse_id else False

        valid, mapping_tax, message = self._validate_bp_tax_vs_mapping(partner, warehouse)

        if valid is False:
            raise UserError(message)

        if valid is None:
            return

        for cmd in (order_lines_vals or []):
            if cmd[0] not in (0, 1):
                continue
            line_vals = cmd[2] if len(cmd) > 2 else {}
            tax_ids_cmd = line_vals.get('tax_id')
            if not tax_ids_cmd:
                continue

            tax_ids = set()
            for tc in tax_ids_cmd:
                if tc[0] == 6:
                    tax_ids.update(tc[2])
                elif tc[0] == 4:
                    tax_ids.add(tc[1])

            if tax_ids and mapping_tax.id not in tax_ids:
                tax_names = self.env['account.tax'].browse(list(tax_ids)).mapped('name')
                raise UserError(_(
                    "Tax order line tidak sesuai mapping!\n\n"
                    "Tax diisi   : %s\n"
                    "Tax expected: %s\n\n"
                    "Warehouse   : %s\n"
                    "BP Tax '%s' : %s\n\n"
                    "Silakan sesuaikan tax order line dengan mapping warehouse."
                ) % (
                    ', '.join(tax_names) or '-',
                    mapping_tax.name,
                    warehouse.name,
                    partner.name,
                    partner.gm_bp_tax.name,
                ))

    # ── pricelist dari partner ────────────────────────────
    def _get_partner_pricelist(self, partner):
        if partner:
            return partner.property_product_pricelist
        return False

    # ── onchange ──────────────────────────────────────────
    @api.onchange('partner_id')
    def _onchange_partner_customer_info(self):
        self.customer_info = self.partner_id.company_id if self.partner_id else False

    @api.onchange('partner_id')
    def _onchange_partner_pricelist(self):
        if self.partner_id:
            pricelist = self._get_partner_pricelist(self.partner_id)
            if pricelist:
                self.pricelist_id = pricelist
            else:
                self.pricelist_id = self.env.company.default_pricelist_id

    @api.onchange('partner_id', 'warehouse_id')
    def _onchange_apply_mapping_tax(self):
        if not self.partner_id or not self.warehouse_id:
            return

        valid, mapping_tax, message = self._validate_bp_tax_vs_mapping(
            self.partner_id, self.warehouse_id
        )

        if valid is False:
            return {'warning': {
                'title': _('Tax Partner Tidak Sesuai Mapping Warehouse'),
                'message': message,
            }}

        if valid is None:
            return

        updated_lines = []
        for line in self.order_line:
            if line.tax_id.ids != [mapping_tax.id]:
                line.tax_id = [(6, 0, [mapping_tax.id])]
                updated_lines.append(line.product_id.name or '-')

        if updated_lines:
            return {'warning': {
                'title': _('Tax Order Line Diperbarui'),
                'message': _(
                    "Tax pada %d order line diperbarui ke '%s' "
                    "sesuai mapping warehouse '%s'.\n\n"
                    "Produk yang diperbarui:\n- %s"
                ) % (
                    len(updated_lines),
                    mapping_tax.name,
                    self.warehouse_id.name,
                    '\n- '.join(updated_lines),
                ),
            }}

    @api.onchange('pricelist_id')
    def _onchange_pricelist_id_check_cashier(self):
        if self.env.user.has_group('dev_pos.group_sale_cashier') and self.pricelist_id:
            if self._origin and self._origin.pricelist_id != self.pricelist_id:
                return {
                    'warning': {
                        'title': _('Tidak Diizinkan'),
                        'message': _('Anda tidak memiliki izin mengubah Pricelist.'),
                    },
                    'value': {'pricelist_id': self._origin.pricelist_id.id}
                }

    # ── compute & crud ────────────────────────────────────
    @api.depends('user_id', 'company_id')
    def _compute_warehouse_id(self):
        allowed_all = self.env.user.sudo().allowed_warehouse_ids

        for order in self:
            company_id = order.company_id.id
            allowed = allowed_all.filtered(lambda w: w.company_id.id == company_id)

            if not allowed:
                super(SaleOrder, order)._compute_warehouse_id()
                continue

            if order.warehouse_id and order.warehouse_id.id in allowed.ids:
                continue

            order.warehouse_id = allowed[0]

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'pricelist_id' in fields_list:
            partner_id = self.env.context.get('default_partner_id')
            if partner_id:
                partner = self.env['res.partner'].browse(partner_id)
                pricelist = self._get_partner_pricelist(partner)
                if pricelist:
                    res['pricelist_id'] = pricelist.id
        allowed = self.env.user.sudo().allowed_warehouse_ids.filtered(
            lambda w: w.company_id.id == self.env.company.id
        )
        if allowed and len(allowed) == 1 and 'warehouse_id' in fields_list:
            res['warehouse_id'] = allowed.id
        return res

    @api.model
    def get_allowed_warehouse_ids_for_current_user(self):
        allowed = self.env.user.sudo().allowed_warehouse_ids.filtered(
            lambda w: w.company_id.id == self.env.company.id
        )
        return allowed.ids

    def action_new_sale_with_warehouse(self):
        allowed = self.env.user.sudo().allowed_warehouse_ids.filtered(
            lambda w: w.company_id.id == self.env.company.id
        )
        if not allowed:
            return self._open_new_so_form()
        if len(allowed) == 1:
            return self._open_new_so_form(warehouse_id=allowed.id)
        return {
            'name': _('Pilih Warehouse'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.warehouse.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }

    def _open_new_so_form(self, warehouse_id=None):
        ctx = dict(self.env.context)
        if warehouse_id:
            ctx['default_warehouse_id'] = warehouse_id
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sale Order Baru'),
            'res_model': 'sale.order',
            'view_mode': 'form',
            'views': [(self.env.ref('sale.view_order_form').id, 'form')],
            'target': 'current',
            'context': ctx,
        }

    @api.model_create_multi
    def create(self, vals_list):
        user_is_cashier = self.env.user.has_group('dev_pos.group_sale_cashier')
        processed_vals_list = []

        for vals in vals_list:
            partner_id = vals.get('partner_id')
            if partner_id:
                partner = self.env['res.partner'].browse(partner_id)
                expected_pricelist = self._get_partner_pricelist(partner)

                if user_is_cashier:
                    if 'pricelist_id' in vals:
                        if expected_pricelist and vals['pricelist_id'] != expected_pricelist.id:
                            raise UserError(_("Anda tidak diizinkan memilih Pricelist. Pricelist akan otomatis dari customer."))
                    if expected_pricelist and 'pricelist_id' not in vals:
                        vals['pricelist_id'] = expected_pricelist.id
                else:
                    if expected_pricelist and 'pricelist_id' not in vals:
                        vals['pricelist_id'] = expected_pricelist.id

            allowed = self.env.user.sudo().allowed_warehouse_ids.filtered(
                lambda w: w.company_id.id == self.env.company.id
            )
            if allowed:
                allowed_ids = set(allowed.ids)
                wh_id = vals.get('warehouse_id')
                if wh_id and wh_id not in allowed_ids:
                    raise UserError(_(
                        "Anda tidak memiliki akses ke warehouse yang dipilih. "
                        "Silakan pilih warehouse yang diizinkan untuk akun Anda."
                    ))

            self._check_line_tax_vs_mapping(
                partner_id=vals.get('partner_id'),
                warehouse_id=vals.get('warehouse_id'),
                order_lines_vals=vals.get('order_line', []),
            )
            processed_vals_list.append(vals)

        return super().create(processed_vals_list)

    def write(self, vals):
        user_is_cashier = self.env.user.has_group('dev_pos.group_sale_cashier')
        if user_is_cashier and 'pricelist_id' in vals:
            for order in self:
                if order.pricelist_id.id != vals['pricelist_id']:
                    raise UserError(_("Anda tidak memiliki izin mengubah Pricelist."))

        locked_map = self.env.context.get('_locked_warehouse_map')
        if locked_map and 'warehouse_id' in vals:
            for order in self:
                if order.id in locked_map:
                    vals = dict(vals)
                    vals.pop('warehouse_id')
                    break

        if 'order_line' in vals or 'partner_id' in vals or 'warehouse_id' in vals:
            for order in self:
                partner_id = vals.get('partner_id', order.partner_id.id)
                warehouse_id = vals.get('warehouse_id', order.warehouse_id.id)
                order_lines_vals = vals.get('order_line', [])
                order._check_line_tax_vs_mapping(
                    partner_id=partner_id,
                    warehouse_id=warehouse_id,
                    order_lines_vals=order_lines_vals,
                )

        return super().write(vals)

    def action_open_price_wizard(self):
        self.ensure_one()
        return {
            'name': _('Ubah Harga - Validasi PIN'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.price.pin.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_order_id': self.id},
        }


# ══════════════════════════════════════════════════════════
# 4. sale.order.line
# ══════════════════════════════════════════════════════════
class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.onchange('product_id')
    def _onchange_product_bp_tax(self):
        if not self.product_id:
            return

        partner = self.order_id.partner_id
        warehouse = self.order_id.warehouse_id

        if not partner or not warehouse:
            return

        valid, mapping_tax, _msg = self.order_id._validate_bp_tax_vs_mapping(
            partner, warehouse
        )

        if valid is True and mapping_tax:
            self.tax_id = [(6, 0, [mapping_tax.id])]
            return

        if partner.gm_bp_tax:
            self.tax_id = [(6, 0, [partner.gm_bp_tax.id])]

    @api.onchange('tax_id')
    def _onchange_tax_id_check_mapping(self):
        if not self.tax_id:
            return

        partner = self.order_id.partner_id
        warehouse = self.order_id.warehouse_id

        if not partner or not warehouse:
            return

        valid, mapping_tax, message = self.order_id._validate_bp_tax_vs_mapping(
            partner, warehouse
        )

        if valid is not True or not mapping_tax:
            return

        if mapping_tax.id not in self.tax_id.ids:
            self.tax_id = [(6, 0, [mapping_tax.id])]
            return {'warning': {
                'title': _('Tax Tidak Sesuai Mapping'),
                'message': _(
                    "Tax yang dipilih tidak diizinkan!\n\n"
                    "Tax expected : %s\n"
                    "Warehouse    : %s\n\n"
                    "Tax dikembalikan ke '%s'."
                ) % (
                    mapping_tax.name,
                    warehouse.name,
                    mapping_tax.name,
                ),
            }}

    def write(self, vals):
        if 'price_unit' in vals:
            order = self.order_id
            if order:
                pos_config = order._get_pos_config_by_warehouse()
                if pos_config:
                    manager_validation = pos_config.manager_validation
                    validate_price_change = pos_config.validate_price_change
                else:
                    manager_validation = False
                    validate_price_change = False
            else:
                manager_validation = False
                validate_price_change = False

            if manager_validation and validate_price_change:
                if not self.env.context.get('pin_validated'):
                    is_system_process = (
                        self.env.context.get('from_confirm') or
                        self.env.context.get('mail_notrack') or
                        self.env.su
                    )
                    if not is_system_process:
                        for line in self:
                            if line.price_unit != vals.get('price_unit'):
                                raise UserError(_(
                                    "Perubahan harga memerlukan validasi PIN manager. "
                                    "Gunakan menu 'Ubah Harga' untuk mengubah harga."
                                ))
        return super().write(vals)


# ══════════════════════════════════════════════════════════
# 5. Wizard: validasi PIN untuk ubah harga (dengan info manager)
# ══════════════════════════════════════════════════════════
class SalePricePinWizard(models.TransientModel):
    _name = 'sale.price.pin.wizard'
    _description = 'Wizard Validasi PIN untuk Ubah Harga'

    order_id = fields.Many2one('sale.order', string='Sale Order', required=True)
    order_line_id = fields.Many2one('sale.order.line', string='Order Line', required=True)
    product_id = fields.Many2one(related='order_line_id.product_id', string='Produk', readonly=True)
    current_price = fields.Float(related='order_line_id.price_unit', string='Harga Saat Ini', readonly=True)
    new_price = fields.Float(string='Harga Baru', required=True)
    pin = fields.Char(string='PIN Manager', required=True, password=True)
    note = fields.Char(
        string='Catatan', readonly=True,
        default='Masukkan PIN Manager untuk mengubah harga.',
    )
    manager_id = fields.Many2one('hr.employee', string='Manager', readonly=True)

    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        order_id = self.env.context.get('default_order_id')
        if order_id and 'manager_id' in fields_list:
            order = self.env['sale.order'].browse(order_id)
            if order:
                pos_config = order._get_pos_config_by_warehouse()
                if pos_config and pos_config.manager_id:
                    res['manager_id'] = pos_config.manager_id.id
        return res

    def action_validate(self):
        self.ensure_one()
        order = self.order_id
        if not order:
            raise UserError(_("Sale Order tidak ditemukan."))

        pos_config = order._get_pos_config_by_warehouse()
        if not pos_config:
            raise UserError(_(
                "Tidak ditemukan konfigurasi POS untuk warehouse '%s'. "
                "Pastikan warehouse sudah dihubungkan dengan POS Config."
            ) % (order.warehouse_id.name if order.warehouse_id else '-'))

        if not pos_config.manager_validation or not pos_config.validate_price_change:
            raise UserError(_(
                "Fitur validasi harga tidak diaktifkan di POS Config untuk warehouse '%s'."
            ) % order.warehouse_id.name)

        manager = pos_config.manager_id
        if not manager:
            raise UserError(_(
                "Manager belum dikonfigurasi di POS Settings untuk warehouse '%s'. "
                "Silakan isi field 'Manager' pada POS Config yang terhubung dengan warehouse ini."
            ) % order.warehouse_id.name)

        if str(manager.pin) != str(self.pin):
            raise UserError(_("PIN salah. Silakan coba lagi."))

        self.order_line_id.with_context(pin_validated=True).write({
            'price_unit': self.new_price,
        })

        _logger.info(
            "Harga diubah oleh manager '%s' (warehouse %s): line %s  %.2f → %.2f",
            manager.name, order.warehouse_id.name, self.order_line_id.id, self.current_price, self.new_price,
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Berhasil'),
                'message': _(
                    'Harga %(product)s berhasil diubah menjadi %(price)s.',
                    product=self.product_id.name,
                    price=self.new_price,
                ),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_cancel(self):
        return {'type': 'ir.actions.act_window_close'}