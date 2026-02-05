/** @odoo-module **/

import { PaymentScreenPaymentLines } from "@point_of_sale/app/screens/payment_screen/payment_lines/payment_lines";
import { patch } from "@web/core/utils/patch";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";
import { _t } from "@web/core/l10n/translation";

patch(PaymentScreenPaymentLines.prototype, {
    /**
     * Check if payment line can be deleted
     * Block deletion for payment methods with gm_is_dp = true
     */
    canDeleteLine(line) {
        // ✅ Block deletion if payment method has gm_is_dp = true
        if (line.payment_method && line.payment_method.gm_is_dp === true) {
            console.log(`🚫 [DELETE BLOCKED] DP payment line cannot be deleted:`, {
                method: line.payment_method.name,
                amount: line.amount,
                gm_is_dp: line.payment_method.gm_is_dp
            });
            return false;
        }
        
        // ✅ Also block if payment status is done or reversed (existing logic)
        if (line.payment_status && ['done', 'reversed'].includes(line.payment_status)) {
            return false;
        }
        
        return true;
    },
    
    /**
     * Override delete line handler with validation
     */
    async handleDeleteLine(cid) {
        const line = this.props.paymentLines.find(l => l.cid === cid);
        
        if (!line) {
            console.warn('⚠️ Payment line not found:', cid);
            return;
        }
        
        // ✅ Check if line can be deleted
        if (!this.canDeleteLine(line)) {
            // Show error popup if it's a DP payment
            if (line.payment_method && line.payment_method.gm_is_dp === true) {
                await this.popup.add(ErrorPopup, {
                    title: _t("Cannot Delete Payment"),
                    body: _t(
                        "Down Payment (DP) payment lines cannot be deleted. " +
                        "Please contact your manager if you need to modify this payment."
                    ),
                });
                
                console.log('❌ [DELETE DENIED] DP payment line deletion blocked');
                return;
            }
        }
        
        // ✅ If allowed, proceed with deletion
        this.props.deleteLine(cid);
    },
});

console.log("✅ [PAYMENT LINES] DP payment protection loaded");