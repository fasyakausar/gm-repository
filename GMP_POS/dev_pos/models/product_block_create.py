import logging

from odoo import api, models, _
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

GROUP = 'custom_receipts_for_pos.group_admin_menu_access'

MSG_PRODUCT = "Anda tidak diizinkan membuat atau mengubah produk."
MSG_PARTNER = "Anda tidak diizinkan membuat atau mengubah kontak / partner."
MSG_DOC_PRODUCT = "Anda tidak diizinkan memakai produk baru buatan Anda sendiri di %s.\nProduk: %s"
MSG_DOC_PARTNER = "Anda tidak diizinkan memakai partner baru buatan Anda sendiri di %s.\nPartner: %s"

# Context untuk melewati blokir dari kode internal (mis. integrasi),
# contoh: record.with_context(skip_product_block=True).write({...})
SKIP_KEY = 'skip_product_block'


def _is_allowed(env):
    """True jika user boleh create / write produk & partner."""
    return env.su or env.context.get(SKIP_KEY) or env.user.has_group(GROUP)


def _check_access(env, action, model_label, message):
    if _is_allowed(env):
        return
    _logger.info("BLOCK %s | user=%s | action=%s", model_label, env.user.login, action)
    raise AccessError(_(message))


def _check_product(env, action):
    _check_access(env, action, 'PRODUCT', MSG_PRODUCT)


def _check_partner(env, action, partners=None):
    # User tetap boleh mengubah partner miliknya sendiri (Preferences / profil),
    # karena res.users.write meneruskan perubahan ke res.partner.
    if partners is not None and partners and partners == env.user.partner_id:
        return
    _check_access(env, action, 'PARTNER', MSG_PARTNER)


def _check_document_records(env, records, doc_label, message):
    """Tolak save dokumen jika ada record (produk / partner) yang dibuat oleh user itu sendiri."""
    if _is_allowed(env):
        return
    own_records = records.filtered(lambda r: r.create_uid.id == env.uid)
    if own_records:
        _logger.info("BLOCK DOCUMENT | user=%s | doc=%s | model=%s | ids=%s",
                     env.user.login, doc_label, own_records._name, own_records.ids)
        raise UserError(_(message) % (
            doc_label, ", ".join(own_records.mapped('display_name'))
        ))


def _check_document_products(env, products, doc_label):
    _check_document_records(env, products, doc_label, MSG_DOC_PRODUCT)


def _check_document_partners(env, partners, doc_label):
    _check_document_records(env, partners, doc_label, MSG_DOC_PARTNER)


# ══════════════════════════════════════════════════════════
# PRODUCT TEMPLATE
# ══════════════════════════════════════════════════════════
class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model
    def default_get(self, fields_list):       # klik New / Create and edit
        _check_product(self.env, 'new')
        return super().default_get(fields_list)

    @api.model_create_multi
    def create(self, vals_list):               # save produk baru
        _check_product(self.env, 'create')
        return super().create(vals_list)

    def write(self, vals):                     # update produk
        _check_product(self.env, 'write')
        return super().write(vals)


# ══════════════════════════════════════════════════════════
# PRODUCT VARIANT
# ══════════════════════════════════════════════════════════
class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model
    def default_get(self, fields_list):
        _check_product(self.env, 'new')
        return super().default_get(fields_list)

    @api.model_create_multi
    def create(self, vals_list):
        _check_product(self.env, 'create')
        return super().create(vals_list)

    def write(self, vals):
        _check_product(self.env, 'write')
        return super().write(vals)


# ══════════════════════════════════════════════════════════
# PARTNER / KONTAK
# ══════════════════════════════════════════════════════════
class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def default_get(self, fields_list):       # klik New / Create and edit
        _check_partner(self.env, 'new')
        return super().default_get(fields_list)

    @api.model_create_multi
    def create(self, vals_list):               # save partner baru / quick create
        _check_partner(self.env, 'create')
        return super().create(vals_list)

    def write(self, vals):                     # update partner
        _check_partner(self.env, 'write', partners=self)
        return super().write(vals)


# ══════════════════════════════════════════════════════════
# SALE ORDER
# ══════════════════════════════════════════════════════════
class SaleOrderBlockProduct(models.Model):
    _inherit = 'sale.order'

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        _check_document_products(self.env, orders.order_line.product_id, "Sale Order")
        _check_document_partners(self.env, orders.partner_id, "Sale Order")
        return orders

    def write(self, vals):
        res = super().write(vals)
        if 'order_line' in vals:
            _check_document_products(self.env, self.order_line.product_id, "Sale Order")
        if 'partner_id' in vals:
            _check_document_partners(self.env, self.partner_id, "Sale Order")
        return res


# ══════════════════════════════════════════════════════════
# STOCK PICKING (Transfer)
# ══════════════════════════════════════════════════════════
class StockPickingBlockProduct(models.Model):
    _inherit = 'stock.picking'

    @api.model_create_multi
    def create(self, vals_list):
        pickings = super().create(vals_list)
        _check_document_products(self.env, pickings.move_ids.product_id, "Transfer")
        _check_document_partners(self.env, pickings.partner_id, "Transfer")
        return pickings

    def write(self, vals):
        res = super().write(vals)
        if 'move_ids' in vals or 'move_ids_without_package' in vals:
            _check_document_products(self.env, self.move_ids.product_id, "Transfer")
        if 'partner_id' in vals:
            _check_document_partners(self.env, self.partner_id, "Transfer")
        return res