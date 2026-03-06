from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def write(self, vals):
        if 'price_unit' in vals:
            config = self.env['ir.config_parameter'].sudo()
            manager_validation = config.get_param('pos.manager_validation', 'False') == 'True'
            validate_price_change = config.get_param('pos.validate_price_change', 'False') == 'True'

            if manager_validation and validate_price_change:
                if not self.env.context.get('pin_validated'):
                    raise UserError(
                        "Perubahan harga memerlukan validasi PIN manager. "
                        "Gunakan menu 'Ubah Harga' untuk mengubah harga."
                    )
        return super().write(vals)
    
class SalePricePinWizard(models.TransientModel):
    _name = 'sale.price.pin.wizard'
    _description = 'Wizard Validasi PIN untuk Ubah Harga'

    order_id = fields.Many2one('sale.order', string='Sale Order', required=True)
    order_line_id = fields.Many2one('sale.order.line', string='Order Line', required=True)
    product_id = fields.Many2one(related='order_line_id.product_id', string='Produk', readonly=True)
    current_price = fields.Float(related='order_line_id.price_unit', string='Harga Saat Ini', readonly=True)
    new_price = fields.Float(string='Harga Baru', required=True)
    pin = fields.Char(string='PIN Manager', required=True, password=True)
    note = fields.Char(string='Catatan', readonly=True,
                       default='Masukkan PIN Manager untuk mengubah harga.')

    def action_validate(self):
        self.ensure_one()
        config = self.env['ir.config_parameter'].sudo()

        # Ambil manager
        manager_id = config.get_param('pos.manager_id')
        if not manager_id:
            raise UserError("Manager belum dikonfigurasi di POS Settings.")

        manager = self.env['hr.employee'].browse(int(manager_id))
        if not manager.exists():
            raise UserError("Manager tidak ditemukan.")

        # Validasi PIN
        if str(manager.pin) != str(self.pin):
            raise UserError("PIN salah. Silakan coba lagi.")

        # PIN benar → update harga
        self.order_line_id.with_context(pin_validated=True).write({
            'price_unit': self.new_price,
        })

        _logger.info(
            f"✅ Harga diubah oleh manager '{manager.name}': "
            f"line {self.order_line_id.id} "
            f"{self.current_price} → {self.new_price}"
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Berhasil',
                'message': f'Harga {self.product_id.name} berhasil diubah menjadi {self.new_price}.',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_cancel(self):
        return {'type': 'ir.actions.act_window_close'}
    
class SaleOrder(models.Model):
    _inherit = 'sale.order'

    customer_info = fields.Many2one(
        'res.company',
        string='Customer Company',
        readonly=False,
    )

    @api.onchange('partner_id')
    def _onchange_partner_customer_info(self):
        self.customer_info = self.partner_id.company_id if self.partner_id else False

    def action_open_price_wizard(self):
        """
        Buka wizard ubah harga untuk orderline yang dipilih.
        Dipanggil dari button di form sale.order.
        """
        self.ensure_one()

        # Ambil orderline pertama yang aktif, atau bisa dimodif untuk multi
        # Untuk simplisitas, buka wizard tanpa pre-select line
        return {
            'name': 'Ubah Harga - Validasi PIN',
            'type': 'ir.actions.act_window',
            'res_model': 'sale.price.pin.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_order_id': self.id,
            },
        }