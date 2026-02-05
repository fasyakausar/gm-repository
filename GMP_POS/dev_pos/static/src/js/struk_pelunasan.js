/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { Order, Orderline } from "@point_of_sale/app/store/models";

/**
 * 🎯 PELUNASAN & ROUNDING Filter v6.0
 * FIXED: Multiple detection methods for rounding
 */

patch(Orderline.prototype, {
    getDisplayData() {
        const data = super.getDisplayData(...arguments);
        
        try {
            const product = this.get_product();
            
            // Check pelunasan
            data.isPelunasan = product?.gm_is_pelunasan === true;
            
            // ✅ MULTIPLE DETECTION METHODS for rounding
            const detectionMethods = {
                byFlag: this.is_rounding_line === true,
                byGmFlag: this.gm_is_rounding === true,
                byProductFlag: product?.is_rounding_line === true,
                byProductId: this.order?.pos?.config?.rounding_product_id && 
                           product?.id === this.order.pos.config.rounding_product_id,
                byProductName: product?.display_name?.includes('ROUNDING'),
            };
            
            data.isRounding = Object.values(detectionMethods).some(v => v === true);
            
            if (data.isRounding) {
                data.roundingAmount = this.get_price_with_tax();
                console.log(`💰 [ROUNDING DETECTED] Product: ${product.display_name}`);
                console.log('   Detection methods:', detectionMethods);
                console.log('   Amount:', data.roundingAmount);
                console.log('   Product ID:', product?.id);
                console.log('   Config Rounding Product ID:', this.order?.pos?.config?.rounding_product_id);
            }
            
            if (data.isPelunasan) {
                console.log(`🏷️ [PELUNASAN] Detected: ${product.display_name}`);
            }
        } catch (e) {
            console.error('[RECEIPT FILTER] Error in getDisplayData:', e);
            data.isPelunasan = false;
            data.isRounding = false;
            data.roundingAmount = 0;
        }
        
        return data;
    },
});

patch(Order.prototype, {
    export_for_printing() {
        const result = super.export_for_printing(...arguments);
        
        console.log('🔍 [RECEIPT FILTER v6.0] Starting...');
        
        if (!result.orderlines || !Array.isArray(result.orderlines)) {
            console.warn('⚠️ [RECEIPT FILTER] No orderlines found');
            return result;
        }
        
        const originalCount = result.orderlines.length;
        console.log(`📊 [RECEIPT FILTER] Original orderlines: ${originalCount}`);
        
        let pelunasanFiltered = 0;
        let roundingFiltered = 0;
        let roundingAmount = 0;
        
        const filteredLines = result.orderlines.filter((line, index) => {
            const isPelunasan = line.isPelunasan === true;
            const isRounding = line.isRounding === true;
            
            console.log(`🔍 Line ${index + 1}: ${line.productName}`, {
                isPelunasan,
                isRounding,
                roundingAmount: line.roundingAmount,
            });
            
            if (isPelunasan) {
                pelunasanFiltered++;
                console.log(`🚫 [PELUNASAN] Filtered: ${line.productName}`);
                return false;
            }
            
            if (isRounding) {
                roundingFiltered++;
                roundingAmount = line.roundingAmount || line.price_with_tax || line.price || 0;
                console.log(`💰 [ROUNDING] Filtered: ${line.productName}, Amount: ${roundingAmount}`);
                return false;
            }
            
            console.log(`✅ [KEEP] ${line.productName}`);
            return true;
        });
        
        result.orderlines = filteredLines;
        
        // Store rounding amount
        if (roundingFiltered > 0 && Math.abs(roundingAmount) >= 0.01) {
            result.rounding_amount = roundingAmount;
            console.log(`✅ [ROUNDING] Stored amount: ${roundingAmount}`);
        } else {
            result.rounding_amount = 0;
        }
        
        console.log('📊 [RECEIPT FILTER] Summary:', {
            original: originalCount,
            pelunasanFiltered,
            roundingFiltered,
            final: filteredLines.length,
            rounding_amount: result.rounding_amount
        });
        
        return result;
    },
});

console.log("✅ [RECEIPT FILTER v6.0] Loaded with enhanced detection");