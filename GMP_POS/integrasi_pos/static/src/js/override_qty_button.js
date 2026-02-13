/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { Orderline } from "@point_of_sale/app/store/models";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { SetPricelistButton } from "@point_of_sale/app/screens/product_screen/control_buttons/pricelist_button/pricelist_button";
import { _t } from "@web/core/l10n/translation";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";
import { CustomNumpadPopUp } from "./custom_numpad_popup";
import { InputNumberPopUpQty } from "./input_number_popup_qty";

// ============================================================
// Helper
// ============================================================
function isSelectedLineDP(pos) {
    return pos?.get_order()?.get_selected_orderline()?.product?.gm_is_dp === true;
}

function removeSelectedDPLine(pos) {
    const order = pos.get_order();
    const selectedLine = order?.get_selected_orderline();
    if (selectedLine) {
        order.removeOrderline(selectedLine);
    }
}

// ============================================================
// Patch Orderline: blokir set_quantity HANYA jika orderline
// sudah ada di order (quantity sudah ter-set sebelumnya).
// Saat pertama kali add product, quantity belum ter-set
// sehingga set_quantity(1) harus tetap berjalan normal.
// ============================================================
patch(Orderline.prototype, {
    set_quantity(quantity, keep_price) {
        if (this.product?.gm_is_dp) {
            // Izinkan jika ini adalah set_quantity pertama kali
            // (quantity belum ada / masih undefined / 0)
            // Tandanya: this.quantity belum ter-assign atau masih 0
            const alreadyHasQty = this.quantity !== undefined && this.quantity !== 0;
            if (alreadyHasQty) {
                console.warn("[gm_is_dp] set_quantity BLOCKED (already has qty):", this.product?.display_name, "current:", this.quantity, "new:", quantity);
                return false;
            }
            // Pertama kali set → izinkan (ini dari add_product)
            console.log("[gm_is_dp] set_quantity ALLOWED (initial set):", this.product?.display_name, "qty:", quantity);
        }
        return super.set_quantity(quantity, keep_price);
    },
});

// ============================================================
// Patch SetPricelistButton
// ============================================================
patch(SetPricelistButton.prototype, {
    async click() {
        const config = this.pos.config || {};
        if (config.manager_validation && config.validate_pricelist) {
            const { confirmed } = await this.popup.add(CustomNumpadPopUp, {
                title: _t("Enter Manager PIN"),
                body: _t("You need manager access to change the pricelist."),
            });
            if (!confirmed) return;
        }
        return super.click(...arguments);
    },
});

// ============================================================
// Patch ProductScreen
// ============================================================
patch(ProductScreen.prototype, {

    setup() {
        super.setup();
        this._originalKeydownHandler = this._onKeyDown?.bind(this);
    },

    async validateManagerAccess(mode, product = null) {
        const config = this.pos.config || {};
        const restrictedModes = {
            quantity: "validate_add_remove_quantity",
            discount: "validate_discount",
            price: "validate_price_change",
            delete: "validate_order_line_deletion",
        };
        if (!config.manager_validation || !restrictedModes[mode] || !config[restrictedModes[mode]]) {
            return true;
        }
        if (mode === "price") {
            if (!product?.is_fixed_price) return true;
        }
        const { confirmed } = await this.popup.add(CustomNumpadPopUp, {
            title: _t("Enter Manager PIN"),
            body: _t("Please enter the manager's PIN to proceed."),
        });
        return confirmed;
    },

    getProductFromSelectedLine() {
        const selectedLine = this.currentOrder.get_selected_orderline();
        if (!selectedLine) return null;
        if (selectedLine.product) return selectedLine.product;
        if (typeof selectedLine.get_product === "function") return selectedLine.get_product();
        if (selectedLine.product_id) {
            const productId = Array.isArray(selectedLine.product_id)
                ? selectedLine.product_id[0]
                : selectedLine.product_id;
            return this.pos.db.get_product_by_id(productId);
        }
        return null;
    },

    // ============================================================
    // Keyboard fisik
    // ============================================================
    async _onKeyDown(ev) {
        const key = ev.key;
        const mode = this.pos.numpadMode;

        if (mode === "quantity" && isSelectedLineDP(this.pos)) {
            ev.preventDefault();
            ev.stopPropagation();

            if (key === "Backspace") {
                // ✅ Hapus line langsung
                this.numberBuffer.reset();
                removeSelectedDPLine(this.pos);
            } else {
                // ❌ Blokir angka
                this.popup.add(ErrorPopup, {
                    title: _t("Tidak Dapat Mengubah Quantity"),
                    body: _t("Quantity item Down Payment tidak dapat diubah."),
                });
            }
            return;
        }

        if (key === "Backspace") {
            const isValidated = await this.validateManagerAccess("delete");
            if (!isValidated) {
                ev.preventDefault();
                ev.stopPropagation();
                return;
            }
        }

        if (/^[0-9.]$/.test(key) && ["quantity", "discount", "price"].includes(mode)) {
            const product = this.getProductFromSelectedLine();
            const isValidated = await this.validateManagerAccess(mode, product);
            if (!isValidated) {
                ev.preventDefault();
                ev.stopPropagation();
                return;
            }
        }

        if (key === "Enter" && ["quantity", "discount", "price"].includes(mode)) {
            const product = this.getProductFromSelectedLine();
            const isValidated = await this.validateManagerAccess(mode, product);
            if (!isValidated) {
                ev.preventDefault();
                ev.stopPropagation();
                return;
            }
        }

        if (this._originalKeydownHandler) {
            return this._originalKeydownHandler(ev);
        } else if (super._onKeyDown) {
            return super._onKeyDown(ev);
        }
    },

    // ============================================================
    // Numpad UI
    // ============================================================
    async onNumpadClick(buttonValue) {
        const keyAlias = { Backspace: "⌫" };
        const resolvedKey = keyAlias[buttonValue] || buttonValue;
        const numberKeys = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", ".", "+/-", "⌫"];
        const mode = this.pos.numpadMode;

        // Mode switching
        if (["quantity", "discount", "price"].includes(resolvedKey)) {
            this.numberBuffer.capture();
            this.numberBuffer.reset();
            this.pos.numpadMode = resolvedKey;
            return;
        }

        if (mode === "quantity" && isSelectedLineDP(this.pos)) {
            if (resolvedKey === "⌫") {
                // ✅ Hapus line langsung
                this.numberBuffer.reset();
                removeSelectedDPLine(this.pos);
            } else {
                // ❌ Blokir angka dan +/-
                this.numberBuffer.reset();
                this.popup.add(ErrorPopup, {
                    title: _t("Tidak Dapat Mengubah Quantity"),
                    body: _t("Quantity item Down Payment tidak dapat diubah."),
                });
            }
            return;
        }

        // Handle ⌫ normal
        if (resolvedKey === "⌫") {
            const isValidated = await this.validateManagerAccess("delete");
            if (!isValidated) return;
            this.numberBuffer.sendKey("Backspace");
            return;
        }

        // Handle angka normal
        if (numberKeys.includes(resolvedKey)) {
            const selectedLine = this.currentOrder.get_selected_orderline();
            const product = this.getProductFromSelectedLine();
            const isValidated = await this.validateManagerAccess(mode, product);
            if (!isValidated) return;

            try {
                const result = await this.popup.add(InputNumberPopUpQty, {
                    title: _t(`Enter ${mode}`),
                    body: _t("Masukkan nilai yang diinginkan."),
                    contextType: mode,
                });

                if (!result || result.input === undefined || result.input === null) return;
                const value = parseFloat(result.input);
                if (isNaN(value) || value < 0) return;
                if (!selectedLine) return;

                if (mode === "quantity") {
                    if (value === 0) {
                        this.currentOrder.remove_orderline(selectedLine);
                    } else {
                        selectedLine.set_quantity(value);
                    }
                } else if (mode === "discount") {
                    selectedLine.set_discount(Math.min(Math.max(value, 0), 100));
                } else if (mode === "price") {
                    selectedLine.set_unit_price(value);
                    selectedLine.price_type = "manual";
                }

                this.numberBuffer.reset();
            } catch (error) {
                console.error("Error in onNumpadClick:", error);
            }
            return;
        }

        if (super.onNumpadClick) {
            return super.onNumpadClick(resolvedKey);
        }
    },

    // ============================================================
    // _setValue: safety net
    // ============================================================
    _setValue(val) {
        const { numpadMode } = this.pos;

        if (numpadMode === "quantity" && isSelectedLineDP(this.pos)) {
            // Semua sudah dihandle di onNumpadClick/_onKeyDown
            this.numberBuffer.reset();
            return;
        }

        return super._setValue(val);
    },

    // ============================================================
    // updateSelectedOrderline: safety net
    // ============================================================
    async updateSelectedOrderline({ buffer, key }) {
        if (this.pos.numpadMode === "quantity" && isSelectedLineDP(this.pos)) {
            this.numberBuffer.reset();
            return;
        }
        return super.updateSelectedOrderline({ buffer, key });
    },
});