/** @odoo-module */

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";

patch(PaymentScreen.prototype, {
    /**
     * Handle back button click - hapus rounding sebelum kembali ke ProductScreen
     */
    onBackClick() {
        console.log('🔙 [PAYMENT SCREEN] Back button clicked');
        
        const currentOrder = this.currentOrder;
        
        if (!currentOrder) {
            console.warn('⚠️ No current order');
            this.pos.showScreen('ProductScreen');
            return;
        }
        
        // ✅ Debug: tampilkan semua orderlines
        const allLines = currentOrder.get_orderlines();
        console.log(`📋 [BACK] Current orderlines (${allLines.length}):`);
        allLines.forEach((line, index) => {
            console.log(`   ${index + 1}. ${line.product?.display_name}`, {
                is_rounding_line: line.is_rounding_line,
                product_id: line.product?.id,
                price: line.get_price_with_tax()
            });
        });
        
        // ✅ Hapus rounding line
        try {
            if (typeof currentOrder.removeRoundingLine === 'function') {
                currentOrder.removeRoundingLine();
            } else {
                console.error('❌ removeRoundingLine method not found');
            }
        } catch (error) {
            console.error('❌ [BACK] Error removing rounding lines:', error);
        }
        
        // ✅ Kembali ke ProductScreen
        this.pos.showScreen('ProductScreen');
        
        console.log('✅ [BACK] Returned to ProductScreen');
    },
});

console.log("✅ [ROUNDING] PaymentScreen back button patch with debug loaded");