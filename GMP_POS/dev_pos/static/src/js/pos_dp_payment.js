/** @odoo-module **/

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";
import { _t } from "@web/core/l10n/translation";

patch(PaymentScreen.prototype, {

    setup() {
        super.setup(...arguments);

        // ✅ Simpan semua method (termasuk DP) untuk keperluan internal,
        // lalu filter DP keluar dari daftar tombol yang tampil ke kasir.
        this._all_payment_methods_from_config = this.payment_methods_from_config;
        this.payment_methods_from_config = this._all_payment_methods_from_config.filter(
            (method) => !method.gm_is_dp
        );
    },

    async onMounted() {
        await super.onMounted(...arguments);
        await this._autoSelectGiftCardPayment();
    },

    /**
     * Override deletePaymentLine:
     * Blokir penghapusan payment line DP via tombol ×
     */
    deletePaymentLine(cid) {
        const line = this.paymentLines.find((line) => line.cid === cid);
        if (line && line.payment_method && line.payment_method.gm_is_dp) {
            this.popup.add(ErrorPopup, {
                title: _t("Cannot Delete Payment"),
                body: _t(
                    "This payment is automatically added based on gift card redemption and cannot be deleted.\n\n" +
                    "Please remove the gift card from the order if you want to proceed without this payment."
                ),
            });
            return;
        }
        super.deletePaymentLine(cid);
    },

    /**
     * Override selectPaymentLine:
     * Blokir seleksi line DP agar numpad tidak bisa mengubah nominalnya.
     */
    selectPaymentLine(cid) {
        const line = this.paymentLines.find((line) => line.cid === cid);
        if (line && line.payment_method && line.payment_method.gm_is_dp) {
            this.currentOrder.select_paymentline(null);
            this.numberBuffer.reset();
            return;
        }
        super.selectPaymentLine(cid);
    },

    // ─────────────────────────────────────────────────────────────────────────
    // Gift card auto-payment logic
    // ─────────────────────────────────────────────────────────────────────────

    async _autoSelectGiftCardPayment() {
        const order = this.pos.get_order();
        if (!this._hasRedeemedGiftCard(order)) return;

        const dpPaymentMethod = await this._findDpPaymentMethodOnline();
        if (!dpPaymentMethod) return;

        const totalBalance = await this._calculateTotalGiftCardBalance(order);
        if (totalBalance <= 0) return;

        this._addGiftCardPaymentLine(dpPaymentMethod, totalBalance);
    },

    _hasRedeemedGiftCard(order) {
        if (order.couponPointChanges) {
            for (const pe of Object.values(order.couponPointChanges)) {
                const program = this.pos.program_by_id[pe.program_id];
                if (program && program.program_type === 'gift_card') return true;
            }
        }
        if (order.codeActivatedCoupons && order.codeActivatedCoupons.length > 0) {
            for (const coupon of order.codeActivatedCoupons) {
                const program = this.pos.program_by_id[coupon.program_id];
                if (program && program.program_type === 'gift_card') return true;
            }
        }
        for (const line of order.get_orderlines()) {
            if (line.is_reward_line && line.reward_id) {
                const reward = this.pos.reward_by_id[line.reward_id];
                if (reward && reward.program_id && reward.program_id.program_type === 'gift_card') {
                    return true;
                }
            }
        }
        return false;
    },

    async _findDpPaymentMethodOnline() {
        try {
            const configPaymentMethodIds = this.pos.config.payment_method_ids;
            const dpMethodIds = await this.orm.search(
                'pos.payment.method',
                [['id', 'in', configPaymentMethodIds], ['gm_is_dp', '=', true]],
                { limit: 2 }
            );
            if (dpMethodIds.length !== 1) return null;
            // Gunakan _all_payment_methods_from_config agar DP method tetap bisa ditemukan
            return this._all_payment_methods_from_config.find((m) => m.id === dpMethodIds[0]) || null;
        } catch (error) {
            console.error('[ERROR] Failed to find DP payment method:', error);
            return null;
        }
    },

    async _calculateTotalGiftCardBalance(order) {
        let totalBalance = 0;
        const couponIds = [];
        if (order.couponPointChanges) {
            for (const pe of Object.values(order.couponPointChanges)) {
                const program = this.pos.program_by_id[pe.program_id];
                if (program && program.program_type === 'gift_card' && pe.coupon_id > 0) {
                    couponIds.push(pe.coupon_id);
                }
            }
        }
        if (order.codeActivatedCoupons && order.codeActivatedCoupons.length > 0) {
            for (const coupon of order.codeActivatedCoupons) {
                const program = this.pos.program_by_id[coupon.program_id];
                if (program && program.program_type === 'gift_card' && coupon.id > 0) {
                    couponIds.push(coupon.id);
                }
            }
        }
        if (couponIds.length === 0) return 0;
        try {
            const coupons = await this.orm.call('loyalty.card', 'read', [couponIds, ['id', 'points']]);
            for (const coupon of coupons) {
                if (coupon.points) totalBalance += coupon.points;
            }
        } catch (error) {
            console.error('[ERROR] Failed to fetch coupon balances:', error);
        }
        return totalBalance;
    },

    _addGiftCardPaymentLine(paymentMethod, amount) {
        const existingDpPayment = this.paymentLines.find((l) => l.payment_method.gm_is_dp);
        if (existingDpPayment) {
            existingDpPayment.set_amount(amount);
            return;
        }
        const existingLines = [...this.paymentLines];
        for (const line of existingLines) {
            if (!line.payment_method.gm_is_dp) super.deletePaymentLine(line.cid);
        }
        // Panggil add_paymentline langsung di order (bypass semua override)
        const result = this.currentOrder.add_paymentline(paymentMethod);
        if (result) {
            this.numberBuffer.reset();
            const newLine = this.selectedPaymentLine;
            if (newLine) {
                newLine.set_amount(amount);
                this.currentOrder.select_paymentline(null);
            }
        }
        this.numberBuffer.reset();
    },
});