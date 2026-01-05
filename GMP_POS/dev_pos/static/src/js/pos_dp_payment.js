/** @odoo-module **/

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";
import { _t } from "@web/core/l10n/translation";

patch(PaymentScreen.prototype, {
    async onMounted() {
        await super.onMounted(...arguments);
        await this._autoSelectGiftCardPayment();
    },

    /**
     * Override addNewPaymentLine to block manual selection of DP payment method
     */
    addNewPaymentLine(paymentMethod) {
        if (paymentMethod && paymentMethod.gm_is_dp) {
            this.popup.add(ErrorPopup, {
                title: _t("Payment Method Locked"),
                body: _t(
                    "This payment method is reserved for automatic gift card redemption and cannot be manually selected."
                ),
            });
            return;
        }
        // Default Odoo behavior
        return super.addNewPaymentLine(paymentMethod);
    },

    /**
     * Override selectPaymentLine to block DP payment selection
     */
    selectPaymentLine(cid) {
        const line = this.paymentLines.find((line) => line.cid === cid);
        if (line && line.payment_method && line.payment_method.gm_is_dp) {
            this.popup.add(ErrorPopup, {
                title: _t("Cannot Modify Payment"),
                body: _t(
                    "This payment method is automatically set based on gift card balance and cannot be modified.\n\n" +
                    "Current amount: %s",
                    this.env.utils.formatCurrency(line.amount)
                ),
            });
            this.currentOrder.select_paymentline(null);
            this.numberBuffer.reset();
            return;
        }
        super.selectPaymentLine(cid);
    },

    /**
     * Override updateSelectedPaymentline to block DP payment update
     */
    updateSelectedPaymentline(amount = false) {
        const paymentLine = this.selectedPaymentLine;
        if (paymentLine && paymentLine.payment_method && paymentLine.payment_method.gm_is_dp) {
            this.popup.add(ErrorPopup, {
                title: _t("Cannot Modify Payment Amount"),
                body: _t(
                    "This payment method is automatically set based on gift card balance and cannot be modified.\n\n" +
                    "Current amount: %s",
                    this.env.utils.formatCurrency(paymentLine.amount)
                ),
            });
            this.numberBuffer.reset();
            return;
        }
        super.updateSelectedPaymentline(amount);
    },

    /**
     * Override deletePaymentLine to block DP payment deletion
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

    async _autoSelectGiftCardPayment() {
        const order = this.pos.get_order();
        const hasRedeemedGiftCard = this._hasRedeemedGiftCard(order);
        if (!hasRedeemedGiftCard) return;

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
                if (program && program.program_type === 'gift_card') {
                    return true;
                }
            }
        }
        if (order.codeActivatedCoupons && order.codeActivatedCoupons.length > 0) {
            for (const coupon of order.codeActivatedCoupons) {
                const program = this.pos.program_by_id[coupon.program_id];
                if (program && program.program_type === 'gift_card') {
                    return true;
                }
            }
        }
        const orderlines = order.get_orderlines();
        for (const line of orderlines) {
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
            const dpMethod = this.payment_methods_from_config.find(
                (method) => method.id === dpMethodIds[0]
            );
            return dpMethod;
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
        const existingDpPayment = this.paymentLines.find((line) => line.payment_method.gm_is_dp);
        if (existingDpPayment) {
            existingDpPayment.set_amount(amount);
            return;
        }
        const existingLines = [...this.paymentLines];
        for (const line of existingLines) {
            if (!line.payment_method.gm_is_dp) super.deletePaymentLine(line.cid);
        }
        const result = this.addNewPaymentLine(paymentMethod);
        if (result) {
            const newLine = this.selectedPaymentLine;
            if (newLine) {
                newLine.set_amount(amount);
                this.currentOrder.select_paymentline(null);
            }
        }
        this.numberBuffer.reset();
    },
});
