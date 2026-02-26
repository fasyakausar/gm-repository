/** @odoo-module */
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { CashOpeningPopup } from "@point_of_sale/app/store/cash_opening_popup/cash_opening_popup";
import { patch } from "@web/core/utils/patch";

patch(PosStore.prototype, {
    async openCashControl() {
        if (this.pos_session.state === 'opening_control') {
            this.pos_session.cash_register_balance_start = 0;
        }
        return super.openCashControl(...arguments);
    },
});

patch(CashOpeningPopup.prototype, {

    _formatWithSeparator(value) {
        let raw = value.replace(/[^\d.,]/g, "");

        const decimalPoint = this.env.utils.formatCurrency(1.5, false).includes(",") ? "," : ".";
        const thousandSep = decimalPoint === "," ? "." : ",";

        let [intPart, ...decParts] = raw.split(decimalPoint);
        const decPart = decParts.join(decimalPoint);

        intPart = intPart.replace(/[.,]/g, "");
        intPart = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, thousandSep);

        return decPart !== undefined && decParts.length > 0
            ? `${intPart}${decimalPoint}${decPart}`
            : intPart;
    },

    _parseFormattedValue(value) {
        const decimalPoint = this.env.utils.formatCurrency(1.5, false).includes(",") ? "," : ".";
        const thousandSep = decimalPoint === "," ? "." : ",";

        return parseFloat(
            value
                .replace(new RegExp(`\\${thousandSep}`, "g"), "")
                .replace(decimalPoint, ".")
        ) || 0;
    },

    handleInputChange() {
        const raw = this.state.openingCash;
        if (!raw) return;

        const formatted = this._formatWithSeparator(raw);
        if (formatted !== raw) {
            this.state.openingCash = formatted;
        }

        this.state.notes = "";
    },

    async confirm() {
        const numericValue = this._parseFormattedValue(this.state.openingCash);

        this.pos.pos_session.state = "opened";
        this.orm.call("pos.session", "set_cashbox_pos", [
            this.pos.pos_session.id,
            numericValue,
            this.state.notes,
        ]);

        super.confirm();
    },
});