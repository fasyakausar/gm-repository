/** @odoo-module */
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { patch } from "@web/core/utils/patch";

patch(PosStore.prototype, {
    async openCashControl() {
        // Reset opening cash ke 0 sebelum popup muncul
        if (this.pos_session.state === 'opening_control') {
            this.pos_session.cash_register_balance_start = 0;
        }

        // Tetap panggil method asli agar popup tetap muncul normal
        return super.openCashControl(...arguments);
    },
});