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

    # ── helper ────────────────────────────────────────────

    def _get_mapping_tax_for_warehouse(self, warehouse):
        """Kembalikan mapping.tax record untuk warehouse, atau False."""
        if not warehouse:
            return False
        return self.env['mapping.tax'].search([
            ('gm_warehouse_id', '=', warehouse.id)
        ], limit=1)

    def _validate_bp_tax_vs_mapping(self, partner, warehouse):
        """
        Validasi bp_tax partner vs mapping tax warehouse.

        Return (valid, mapping_tax, message):
          - valid=True  → bp_tax cocok dengan mapping, mapping_tax = tax yg harus dipakai
          - valid=False → tidak cocok, message berisi penjelasan
          - valid=None  → tidak ada bp_tax atau mapping, lewati validasi
        """
        if not partner or not warehouse:
            return None, False, ''

        bp_tax = partner.gm_bp_tax
        if not bp_tax:
            return None, False, ''

        mapping = self._get_mapping_tax_for_warehouse(warehouse)
        if not mapping:
            return None, False, ''

        # Tentukan tax mapping berdasarkan kondisi bp_tax partner
        if bp_tax.amount == 0:
            mapping_tax = mapping.gm_tax_code_0
            label = 'Tax 0% (gm_tax_code_0)'
        else:
            mapping_tax = mapping.gm_tax_code
            label = 'Tax normal (gm_tax_code)'

        if not mapping_tax:
            return None, False, ''

        # bp_tax partner harus sama persis dengan mapping_tax WH
        if bp_tax.id != mapping_tax.id:
            message = _(
                "BP Tax partner tidak sesuai mapping warehouse!\n\n"
                "Partner     : %s\n"
                "BP Tax      : %s\n"
                "Warehouse   : %s\n"
                "Tax Mapping : %s (%s)\n\n"
                "Gunakan partner dengan BP Tax '%s' "
                "atau pilih warehouse yang sesuai."
            ) % (
                partner.name,
                bp_tax.name,
                warehouse.name,
                mapping_tax.name,
                label,
                mapping_tax.name,
            )
            return False, mapping_tax, message

        return True, mapping_tax, ''

    # ── validasi untuk create/write ───────────────────────

    def _check_line_tax_vs_mapping(self, partner_id, warehouse_id, order_lines_vals):
        """
        Safety net di create() dan write().
        Blokir jika bp_tax partner tidak sesuai mapping WH,
        atau jika tax di order line tidak sesuai mapping.
        """
        partner = self.env['res.partner'].browse(partner_id) if partner_id else False
        warehouse = self.env['stock.warehouse'].browse(warehouse_id) if warehouse_id else False

        valid, mapping_tax, message = self._validate_bp_tax_vs_mapping(partner, warehouse)

        # Tidak cocok → hard block
        if valid is False:
            raise UserError(message)

        # Tidak ada mapping/bp_tax → lewati
        if valid is None:
            return

        # Cocok → cek tax di setiap order line harus sama dengan mapping_tax
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

    # ── onchange ──────────────────────────────────────────

    @api.onchange('partner_id')
    def _onchange_partner_customer_info(self):
        self.customer_info = self.partner_id.company_id if self.partner_id else False

    @api.onchange('partner_id', 'warehouse_id')
    def _onchange_apply_mapping_tax(self):
        """
        Validasi bp_tax partner vs mapping tax warehouse.
        - Tidak cocok → warning (tidak update line, tidak block save di onchange)
        - Cocok       → apply tax ke semua order line yang berbeda
        """
        if not self.partner_id or not self.warehouse_id:
            return

        valid, mapping_tax, message = self._validate_bp_tax_vs_mapping(
            self.partner_id, self.warehouse_id
        )

        # Tidak cocok → tampilkan warning, jangan ubah apapun
        if valid is False:
            return {'warning': {
                'title': _('Tax Partner Tidak Sesuai Mapping Warehouse'),
                'message': message,
            }}

        # Tidak ada mapping/bp_tax → lewati
        if valid is None:
            return

        # Cocok → apply tax ke semua order line yang taxnya berbeda
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
        allowed = self.env.user.sudo().allowed_warehouse_ids.filtered(
            lambda w: w.company_id.id == self.env.company.id
        )
        if not allowed:
            return res
        if len(allowed) == 1:
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
        allowed = self.env.user.sudo().allowed_warehouse_ids.filtered(
            lambda w: w.company_id.id == self.env.company.id
        )
        if allowed:
            allowed_ids = set(allowed.ids)
            for vals in vals_list:
                wh_id = vals.get('warehouse_id')
                if wh_id and wh_id not in allowed_ids:
                    raise UserError(_(
                        "Anda tidak memiliki akses ke warehouse yang dipilih. "
                        "Silakan pilih warehouse yang diizinkan untuk akun Anda."
                    ))

        for vals in vals_list:
            self._check_line_tax_vs_mapping(
                partner_id=vals.get('partner_id'),
                warehouse_id=vals.get('warehouse_id'),
                order_lines_vals=vals.get('order_line', []),
            )

        return super().create(vals_list)

    def write(self, vals):
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
        """
        Saat produk dipilih, terapkan tax dari mapping WH jika bp_tax
        partner cocok. Fallback ke gm_bp_tax partner jika tidak ada mapping.
        """
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
        """
        Saat user mengubah tax di order line, cek apakah sesuai mapping.
        Jika tidak sesuai → kembalikan paksa ke mapping_tax + warning.
        """
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
            config = self.env['ir.config_parameter'].sudo()
            manager_validation = config.get_param('pos.manager_validation', 'False') == 'True'
            validate_price_change = config.get_param('pos.validate_price_change', 'False') == 'True'

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
# 5. Wizard: validasi PIN untuk ubah harga
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

    def action_validate(self):
        self.ensure_one()
        config = self.env['ir.config_parameter'].sudo()

        manager_id = config.get_param('pos.manager_id')
        if not manager_id:
            raise UserError(_("Manager belum dikonfigurasi di POS Settings."))

        manager = self.env['hr.employee'].sudo().browse(int(manager_id))
        if not manager.exists():
            raise UserError(_("Manager tidak ditemukan."))

        if str(manager.pin) != str(self.pin):
            raise UserError(_("PIN salah. Silakan coba lagi."))

        self.order_line_id.with_context(pin_validated=True).write({
            'price_unit': self.new_price,
        })

        _logger.info(
            "Harga diubah oleh manager '%s': line %s  %.2f → %.2f",
            manager.name, self.order_line_id.id, self.current_price, self.new_price,
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