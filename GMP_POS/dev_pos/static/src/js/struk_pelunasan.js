/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { Order } from "@point_of_sale/app/models/models";

/**
 * Patch Order model untuk filter produk pelunasan dari struk
 */
patch(Order.prototype, {
    /**
     * Override export_for_printing untuk filter gm_is_pelunasan
     */
    export_for_printing() {
        const result = super.export_for_printing(...arguments);
        
        // ✅ Filter orderlines: buang yang gm_is_pelunasan = true
        if (result.orderlines && Array.isArray(result.orderlines)) {
            const originalLength = result.orderlines.length;
            
            result.orderlines = result.orderlines.filter(line => {
                // Get product dari database
                const product = this.pos.db.get_product_by_id(
                    line.product_id?.[0] || line.product_id
                );
                
                // Filter out jika gm_is_pelunasan = true
                const isPelunasan = product?.gm_is_pelunasan === true;
                
                if (isPelunasan) {
                    console.log(
                        `🚫 Hiding pelunasan product from receipt: ${product.display_name} (ID: ${product.id})`
                    );
                }
                
                return !isPelunasan;
            });
            
            const filteredCount = originalLength - result.orderlines.length;
            if (filteredCount > 0) {
                console.log(
                    `✅ Filtered ${filteredCount} pelunasan products from receipt. ` +
                    `Showing ${result.orderlines.length}/${originalLength} items.`
                );
            }
        }
        
        return result;
    },
    
    /**
     * Helper untuk mengecek apakah order punya produk pelunasan
     */
    hasPelunasanProducts() {
        return this.orderlines.some(line => {
            const product = this.pos.db.get_product_by_id(
                line.product_id?.[0] || line.product_id
            );
            return product?.gm_is_pelunasan === true;
        });
    },
    
    /**
     * Get total tanpa produk pelunasan
     */
    get_total_without_pelunasan() {
        return this.orderlines
            .filter(line => {
                const product = this.pos.db.get_product_by_id(
                    line.product_id?.[0] || line.product_id
                );
                return product?.gm_is_pelunasan !== true;
            })
            .reduce((sum, line) => sum + line.get_display_price(), 0);
    },
});