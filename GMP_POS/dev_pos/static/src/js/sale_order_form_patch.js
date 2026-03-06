/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { onWillStart, Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";

// ============================================================
// SalePinDialog Component
// ============================================================
class SalePinDialog extends Component {
    static template = "dev_pos.SalePinDialog";
    static props = {
        close: Function,
        confirm: Function,
    };

    setup() {
        this.state = useState({ pin: "", error: "" });
    }

    onInput(ev) {
        this.state.pin = ev.target.value;
        this.state.error = "";
    }

    onConfirm() {
        if (!this.state.pin) {
            this.state.error = _t("PIN tidak boleh kosong.");
            return;
        }
        this.props.confirm(this.state.pin);
        this.props.close();
    }

    onCancel() {
        this.props.close();
    }
}

registry.category("dialogs").add("dev_pos.SalePinDialog", SalePinDialog);

// ============================================================
// Patch FormController
// ============================================================
patch(FormController.prototype, {

    setup() {
        super.setup();
        this._priceValidationConfig = {
            manager_validation: false,
            validate_price_change: false,
        };

        if (this.props.resModel === "sale.order") {
            this.orm = useService("orm");
            this.dialog = useService("dialog");
            this.notification = useService("notification");

            onWillStart(async () => {
                try {
                    const config = await this.orm.call(
                        "sale.order",
                        "check_price_change_config",
                        [[]]
                    );
                    this._priceValidationConfig = config;
                    console.log("✅ Price validation config:", config);
                } catch (e) {
                    console.warn("⚠️ Failed to load price validation config:", e);
                }
            });
        }
    },

    async save(options) {
        if (this.props.resModel !== "sale.order") {
            return super.save(...arguments);
        }

        const { manager_validation, validate_price_change } = this._priceValidationConfig;

        if (!manager_validation || !validate_price_change) {
            return super.save(...arguments);
        }

        const changedLines = this._getChangedPriceLines();
        console.log("🔍 Changed price lines:", changedLines);

        if (changedLines.length === 0) {
            return super.save(...arguments);
        }

        const pin = await this._requestManagerPin();
        if (pin === null || pin === "") {
            this.notification.add(
                _t("Perubahan harga dibatalkan."),
                { type: "warning" }
            );
            return false;
        }

        const orderId = this.model.root.resId;
        for (const line of changedLines) {
            try {
                const result = await this.orm.call(
                    "sale.order",
                    "action_validate_price_change",
                    [[orderId], line.id, line.new_price, pin]
                );

                if (!result.success) {
                    this.notification.add(
                        _t("PIN salah. Perubahan harga dibatalkan."),
                        { type: "danger" }
                    );
                    return false;
                }
            } catch (e) {
                console.error("❌ Error validating price change:", e);
                this.notification.add(
                    _t("Terjadi kesalahan saat validasi PIN."),
                    { type: "danger" }
                );
                return false;
            }
        }

        this._discardPriceChanges(changedLines);

        this.notification.add(
            _t("Harga berhasil diubah."),
            { type: "success" }
        );

        return super.save(...arguments);
    },

    _getChangedPriceLines() {
        const changed = [];
        try {
            const orderlineField = this.model.root.data.order_line;
            if (!orderlineField) return changed;

            const records = orderlineField.records || [];
            for (const line of records) {
                if (line._changes && "price_unit" in line._changes && line.resId) {
                    changed.push({
                        id: line.resId,
                        new_price: line._changes.price_unit,
                        product: line.data?.product_id?.[1] || line.data?.name || "Unknown",
                    });
                }
            }
        } catch (e) {
            console.warn("⚠️ Error reading changed lines:", e);
        }
        return changed;
    },

    _discardPriceChanges(changedLines) {
        try {
            const orderlineField = this.model.root.data.order_line;
            if (!orderlineField) return;

            const changedIds = new Set(changedLines.map(l => l.id));
            const records = orderlineField.records || [];

            for (const line of records) {
                if (changedIds.has(line.resId) && line._changes) {
                    delete line._changes.price_unit;
                    delete line._changes.price_subtotal;
                    delete line._changes.price_total;
                    delete line._changes.price_tax;

                    if (Object.keys(line._changes).length === 0) {
                        line._changes = null;
                    }
                }
            }
        } catch (e) {
            console.warn("⚠️ Error discarding price changes:", e);
        }
    },

    async _requestManagerPin() {
        return new Promise((resolve) => {
            this.dialog.add(SalePinDialog, {
                confirm: (pin) => resolve(pin),
                close: () => resolve(null),
            });
        });
    },
});