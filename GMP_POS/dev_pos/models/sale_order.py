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
# 2. Wizard: pilih warehouse (muncul hanya jika >1 pilihan)
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
        # Diisi via default_get, bukan computed,
        # supaya domain pada warehouse_id bisa membaca nilainya saat form dibuka
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

    @api.onchange('partner_id')
    def _onchange_partner_customer_info(self):
        self.customer_info = self.partner_id.company_id if self.partner_id else False

    @api.onchange('partner_id')
    def _onchange_partner_bp_tax(self):
        """Auto set tax pada order lines yang sudah ada jika partner punya gm_bp_tax"""
        if self.partner_id and self.partner_id.gm_bp_tax:
            for line in self.order_line:
                line.tax_id = [(6, 0, [self.partner_id.gm_bp_tax.id])]

    @api.depends('user_id', 'company_id')
    def _compute_warehouse_id(self):
        """
        Override _compute_warehouse_id dari sale_stock.

        Per order, filter allowed_warehouse_ids berdasarkan company order
        agar tidak terjadi cross-company access error di lingkungan multi-company.

          - Tidak ada allowed restriction        → native Odoo (per company)
          - Ada allowed, sudah diset & valid     → pertahankan
          - Ada allowed, belum diset / tidak valid → pakai allowed pertama
            yang sesuai company; jika tidak ada → fallback native Odoo
        """
        # Baca dengan sudo() agar tidak terkena multi-company access rule
        # saat user berada di company yang berbeda dengan warehouse yang diassign
        allowed_all = self.env.user.sudo().allowed_warehouse_ids

        for order in self:
            # Filter allowed sesuai company order ini (tanpa sudo sudah aman
            # karena kita hanya pakai .ids dan .filtered, tidak baca field sensitif)
            company_id = order.company_id.id
            allowed = allowed_all.filtered(lambda w: w.company_id.id == company_id)

            if not allowed:
                # Tidak ada restriction untuk company ini → perilaku native Odoo
                super(SaleOrder, order)._compute_warehouse_id()
                continue

            # Warehouse sudah diset dan masih dalam allowed list → pertahankan
            if order.warehouse_id and order.warehouse_id.id in allowed.ids:
                continue

            # Belum diset atau di luar allowed → pakai yang pertama
            order.warehouse_id = allowed[0]

    @api.model
    def default_get(self, fields_list):
        """
        Atur warehouse default berdasarkan allowed_warehouse_ids user.

          * 0 restriction -> default Odoo (warehouse perusahaan user)
          * 1 warehouse   -> langsung set tanpa wizard
          * >1 warehouse  -> pakai context default_warehouse_id jika ada
                             (dikirim dari wizard), atau fallback ke index 0
        """
        res = super().default_get(fields_list)

        # sudo() untuk menghindari multi-company access error
        allowed = self.env.user.sudo().allowed_warehouse_ids.filtered(
            lambda w: w.company_id.id == self.env.company.id
        )

        if not allowed:
            return res

        if len(allowed) == 1:
            res['warehouse_id'] = allowed.id
            return res

        # >1 warehouse: warehouse dipilih via wizard (JS intercept tombol New).
        # Wizard mengirim default_warehouse_id lewat context action.
        # default_get akan otomatis membaca context tersebut via Odoo framework.
        return res

    @api.model
    def get_allowed_warehouse_ids_for_current_user(self):
        """
        Dipanggil dari JS (tombol New) untuk mendapatkan daftar warehouse
        yang diizinkan untuk user saat ini, difilter by active company.
        Menggunakan sudo() agar tidak kena multi-company access rule.
        """
        allowed = self.env.user.sudo().allowed_warehouse_ids.filtered(
            lambda w: w.company_id.id == self.env.company.id
        )
        return allowed.ids

    def action_new_sale_with_warehouse(self):
        """
        Dipanggil dari server action / tombol custom di list view.
        Ini entry point yang benar untuk kasus >1 warehouse,
        menggantikan keterbatasan default_get yang tidak bisa
        return action (hanya bisa return dict nilai field).
        """
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

    def action_confirm(self):
        """
        - Tambahkan context from_confirm agar write() pada order line
          tidak meminta PIN saat proses konfirmasi SO.
        - Lock warehouse_id via context agar tidak di-reset selama proses confirm.
        """
        # Bawa warehouse_id semua order ke context agar write() bisa memproteksinya
        warehouse_map = {order.id: order.warehouse_id.id for order in self}
        return super(
            SaleOrder,
            self.with_context(from_confirm=True, _locked_warehouse_map=warehouse_map)
        ).action_confirm()

    def write(self, vals):
        """
        Proteksi warehouse_id selama proses konfirmasi SO.
        _compute_warehouse_id sudah menangani proteksi di level onchange/compute,
        write() ini hanya memastikan tidak ada proses backend yang
        menimpa pilihan warehouse user saat action_confirm berjalan.
        """
        locked_map = self.env.context.get('_locked_warehouse_map')
        if locked_map and 'warehouse_id' in vals:
            for order in self:
                if order.id in locked_map:
                    vals = dict(vals)
                    vals.pop('warehouse_id')
                    break

        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        """Safety-net: validasi warehouse saat create (termasuk via API)."""
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
        return super().create(vals_list)

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
# 4. sale.order.line — PIN validation on price change + BP Tax
# ══════════════════════════════════════════════════════════
class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.onchange('product_id')
    def _onchange_product_bp_tax(self):
        """
        Override tax_id dengan gm_bp_tax dari partner setelah
        onchange product_id native Odoo mengisi tax default produk.
        """
        if self.order_id.partner_id and self.order_id.partner_id.gm_bp_tax:
            self.tax_id = [(6, 0, [self.order_id.partner_id.gm_bp_tax.id])]

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

        manager = self.env['hr.employee'].browse(int(manager_id))
        if not manager.exists():
            raise UserError(_("Manager tidak ditemukan."))

        if str(manager.pin) != str(self.pin):
            raise UserError(_("PIN salah. Silakan coba lagi."))

        self.order_line_id.with_context(pin_validated=True).write({
            'price_unit': self.new_price,
        })

        _logger.info(
            "✅ Harga diubah oleh manager '%s': line %s  %.2f → %.2f",
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