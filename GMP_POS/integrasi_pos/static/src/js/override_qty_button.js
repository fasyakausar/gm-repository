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
// Patch Orderline
// ============================================================
patch(Orderline.prototype, {
    set_quantity(quantity, keep_price) {
        if (this.product?.gm_is_dp) {
            const alreadyHasQty = this.quantity !== undefined && this.quantity !== 0;
            if (alreadyHasQty) {
                console.warn("[gm_is_dp] set_quantity BLOCKED:", this.product?.display_name, "current:", this.quantity, "new:", quantity);
                return false;
            }
            console.log("[gm_is_dp] set_quantity ALLOWED (initial):", this.product?.display_name, "qty:", quantity);
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

        // ✅ Override triggerAtInput setelah super.setup() selesai
        // Ini menimpa binding asli Odoo sehingga updateSelectedOrderline
        // versi patch kita yang akan dipanggil
        this.numberBuffer.use({
            triggerAtInput: (...args) => {
                if (!this.pos.tempScreenIsShown) {
                    this.updateSelectedOrderline(...args);
                }
            },
            useWithBarcode: true,
        });
    },

    async validateManagerAccess(mode, product = null) {
        const config = this.pos.config || {};

        console.log("🔍 validateManagerAccess:", {
            mode,
            manager_validation: config.manager_validation,
            validate_price_change: config.validate_price_change,
            validate_add_remove_quantity: config.validate_add_remove_quantity,
            validate_discount: config.validate_discount,
            validate_order_line_deletion: config.validate_order_line_deletion,
            product_name: product?.display_name,
        });

        const restrictedModes = {
            quantity: "validate_add_remove_quantity",
            discount: "validate_discount",
            price: "validate_price_change",
            delete: "validate_order_line_deletion",
        };

        if (!config.manager_validation || !restrictedModes[mode] || !config[restrictedModes[mode]]) {
            return true;
        }

        const { confirmed } = await this.popup.add(CustomNumpadPopUp, {
            title: _t("Enter Manager PIN"),
            body: _t("Please enter the manager's PIN to proceed."),
        });
        return confirmed;
    },

    getProductFromSelectedLine() {
        const selectedLine = this.currentOrder?.get_selected_orderline();
        if (!selectedLine) return null;
        return selectedLine.product || null;
    },

    // ============================================================
    // updateSelectedOrderline: titik intercept utama
    // ============================================================
    async updateSelectedOrderline({ buffer, key }) {
        console.log("🔴 updateSelectedOrderline CALLED", { buffer, key, mode: this.pos.numpadMode });

        const mode = this.pos.numpadMode;
        const selectedLine = this.currentOrder?.get_selected_orderline();

        // ── Guard: DP line ────────────────────────────────────────
        if (mode === "quantity" && isSelectedLineDP(this.pos)) {
            this.numberBuffer.reset();
            if (key === "Backspace") {
                removeSelectedDPLine(this.pos);
            } else {
                this.popup.add(ErrorPopup, {
                    title: _t("Tidak Dapat Mengubah Quantity"),
                    body: _t("Quantity item Down Payment tidak dapat diubah."),
                });
            }
            return;
        }

        // ── Guard: Backspace / delete line ───────────────────────
        if (key === "Backspace" && (buffer === null || buffer === "")) {
            const isValidated = await this.validateManagerAccess("delete");
            if (!isValidated) {
                this.numberBuffer.reset();
                return;
            }
            return super.updateSelectedOrderline({ buffer, key });
        }

        // ── Guard: input angka untuk quantity / discount / price ──
        if (["quantity", "discount", "price"].includes(mode) && key !== "Backspace") {
            const product = this.getProductFromSelectedLine();
            const isValidated = await this.validateManagerAccess(mode, product);
            if (!isValidated) {
                this.numberBuffer.reset();
                return;
            }

            if (!selectedLine) {
                this.numberBuffer.reset();
                return;
            }

            try {
                const result = await this.popup.add(InputNumberPopUpQty, {
                    title: _t(`Enter ${mode}`),
                    body: _t("Masukkan nilai yang diinginkan."),
                    contextType: mode,
                });

                if (!result || result.input === undefined || result.input === null) {
                    this.numberBuffer.reset();
                    return;
                }

                const value = parseFloat(result.input);
                if (isNaN(value) || value < 0) {
                    this.numberBuffer.reset();
                    return;
                }

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
                return;
            } catch (error) {
                console.error("❌ Error in updateSelectedOrderline popup:", error);
                this.numberBuffer.reset();
                return;
            }
        }

        // ── Default: jalankan logic asli Odoo ────────────────────
        return super.updateSelectedOrderline({ buffer, key });
    },

    // ============================================================
    // _setValue: safety net untuk DP line
    // ============================================================
    _setValue(val) {
        const { numpadMode } = this.pos;

        if (numpadMode === "quantity" && isSelectedLineDP(this.pos)) {
            this.numberBuffer.reset();
            return;
        }

        return super._setValue(val);
    },
});