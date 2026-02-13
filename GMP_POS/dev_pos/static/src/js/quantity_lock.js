/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { Orderline } from "@point_of_sale/app/store/models";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { _t } from "@web/core/l10n/translation";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";

// ============================================================
// Helper: cek apakah selected orderline adalah gm_is_dp
// ============================================================
function isSelectedLineDP(pos) {
    return pos?.get_order()?.get_selected_orderline()?.product?.gm_is_dp === true;
}

// ============================================================
// Patch Orderline: blokir set_quantity jika gm_is_dp = True
// ============================================================
patch(Orderline.prototype, {
    set_quantity(quantity, keep_price) {
        if (this.product?.gm_is_dp) {
            return false;
        }
        return super.set_quantity(quantity, keep_price);
    },
});

// ============================================================
// Patch ProductScreen
// ============================================================
patch(ProductScreen.prototype, {

    /**
     * Override _setValue:
     * Ini adalah titik akhir sebelum data dikirim ke model.
     * Blokir semua perubahan quantity (termasuk "remove" dari Backspace)
     * jika produk adalah gm_is_dp.
     */
    _setValue(val) {
        const { numpadMode } = this.pos;

        if (numpadMode === "quantity" && isSelectedLineDP(this.pos)) {
            // Reset buffer agar tidak ada nilai yang tersimpan
            this.numberBuffer.reset();

            this.popup.add(ErrorPopup, {
                title: _t("Tidak Dapat Mengubah Quantity"),
                body: _t("Item Down Payment tidak dapat diubah atau dihapus jumlahnya."),
            });
            return; // stop, jangan teruskan ke super
        }

        return super._setValue(val);
    },

    /**
     * Override updateSelectedOrderline:
     * Tangkap lebih awal sebelum buffer dikirim,
     * khususnya untuk kasus angka yang diketik user.
     */
    async updateSelectedOrderline({ buffer, key }) {
        if (this.pos.numpadMode === "quantity" && isSelectedLineDP(this.pos)) {
            // Reset buffer agar angka yang diketik tidak tersimpan
            this.numberBuffer.reset();

            this.popup.add(ErrorPopup, {
                title: _t("Tidak Dapat Mengubah Quantity"),
                body: _t("Item Down Payment tidak dapat diubah atau dihapus jumlahnya."),
            });
            return;
        }

        return super.updateSelectedOrderline({ buffer, key });
    },
});