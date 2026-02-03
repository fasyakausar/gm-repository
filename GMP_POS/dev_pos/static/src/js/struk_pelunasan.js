/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { Order, Orderline } from "@point_of_sale/app/store/models";

/**
 * 🎯 PELUNASAN Filter v3.0
 * Fixed: Works with display data format from getDisplayData()
 */

// =====================================================
// PATCH 1: Override getDisplayData di Orderline
// =====================================================
patch(Orderline.prototype, {
    /**
     * Override getDisplayData untuk menambahkan flag isPelunasan
     * Ini akan digunakan di template untuk filter
     */
    getDisplayData() {
        const data = super.getDisplayData(...arguments);
        
        // Tambahkan flag isPelunasan ke display data
        try {
            const product = this.get_product();
            data.isPelunasan = product?.gm_is_pelunasan === true;
            
            if (data.isPelunasan) {
                console.log(
                    `🏷️ [PELUNASAN] Marked as pelunasan: ${product.display_name} ` +
                    `(gm_is_pelunasan: ${product.gm_is_pelunasan})`
                );
            }
        } catch (e) {
            console.error('[PELUNASAN] Error in getDisplayData:', e);
            data.isPelunasan = false;
        }
        
        return data;
    },
});

// =====================================================
// PATCH 2: Filter di export_for_printing
// =====================================================
patch(Order.prototype, {
    /**
     * Override export_for_printing untuk filter pelunasan
     * Bekerja dengan data yang sudah di-transform ke display format
     */
    export_for_printing() {
        const result = super.export_for_printing(...arguments);
        
        console.log('🔍 [PELUNASAN] Starting receipt filter v3...');
        
        // Safety check
        if (!result.orderlines || !Array.isArray(result.orderlines)) {
            console.warn('⚠️ [PELUNASAN] No orderlines found');
            return result;
        }
        
        const originalCount = result.orderlines.length;
        console.log(`📊 [PELUNASAN] Total orderlines: ${originalCount}`);
        
        // Filter berdasarkan flag isPelunasan yang sudah di-set di getDisplayData
        const filteredLines = result.orderlines.filter((line, index) => {
            // Check flag isPelunasan
            const isPelunasan = line.isPelunasan === true;
            
            if (isPelunasan) {
                console.log(
                    `🚫 [PELUNASAN] Filtering line ${index + 1}: ${line.productName} ` +
                    `(isPelunasan: ${isPelunasan})`
                );
                return false; // Filter out
            } else {
                console.log(
                    `✅ [PELUNASAN] Keeping line ${index + 1}: ${line.productName} ` +
                    `(isPelunasan: ${isPelunasan || false})`
                );
                return true; // Keep
            }
        });
        
        // Update result
        result.orderlines = filteredLines;
        
        const filteredCount = originalCount - filteredLines.length;
        console.log('📊 [PELUNASAN] Filter summary:');
        console.log(`   Original: ${originalCount}`);
        console.log(`   Filtered: ${filteredCount}`);
        console.log(`   Final: ${filteredLines.length}`);
        
        // Safety: prevent complete wipeout
        if (filteredLines.length === 0 && originalCount > 0) {
            console.error('❌ [PELUNASAN] ERROR: All lines filtered!');
            console.error('   Reverting to original data');
            
            // Revert - gunakan original data tanpa filter
            const originalResult = super.export_for_printing(...arguments);
            return originalResult;
        }
        
        return result;
    },
});

console.log("✅ [PELUNASAN] Receipt filter v3.0 loaded (works with display data)");