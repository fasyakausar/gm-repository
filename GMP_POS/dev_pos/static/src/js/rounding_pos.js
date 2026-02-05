/** @odoo-module */

import { Order, Orderline } from "@point_of_sale/app/store/models";
import { patch } from "@web/core/utils/patch";

// =====================================================
// PATCH ORDERLINE - Set flag saat dibuat
// =====================================================
patch(Orderline.prototype, {
    /**
     * Override init untuk detect rounding product
     */
    init_from_JSON(json) {
        super.init_from_JSON(...arguments);
        
        // Check if this is a rounding product
        if (this.order?.pos?.config?.rounding_product_id && 
            this.product?.id === this.order.pos.config.rounding_product_id) {
            this.is_rounding_line = true;
            console.log('🎯 [ROUNDING FLAG] Set via init_from_JSON:', this.product.display_name);
        }
    },
});

// =====================================================
// PATCH ORDER - Auto rounding logic
// =====================================================
patch(Order.prototype, {
    setup() {
        super.setup(...arguments);
        this._rounding_applied = false;
        this._rounding_amount = 0;
    },

    pay() {
        try {
            this.applyAutoRounding();
        } catch (error) {
            console.error('❌ Error applying auto rounding:', error);
        }
        return super.pay(...arguments);
    },

    applyAutoRounding() {
        if (!this.pos || !this.pos.config) {
            console.warn('⚠️ POS or config not available');
            return;
        }

        const config = this.pos.config;
        
        if (!config.enable_auto_rounding) {
            console.log('ℹ️ Auto rounding is disabled');
            return;
        }

        const validation = this.pos.isRoundingConfigured();
        if (!validation.valid) {
            console.warn(`⚠️ Rounding not configured: ${validation.reason}`);
            return;
        }

        const roundingConfig = validation.config;

        console.group('🔄 APPLYING AUTO ROUNDING v6');
        console.log('Rounding config:', roundingConfig);

        this.removeRoundingLine();

        const currentTotal = this.get_total_with_tax();
        const roundingValue = roundingConfig.value;
        const roundedTotal = Math.round(currentTotal / roundingValue) * roundingValue;
        const roundingAmount = roundedTotal - currentTotal;

        console.log('Calculation:', {
            currentTotal,
            roundingValue,
            roundedTotal,
            roundingAmount,
        });

        if (Math.abs(roundingAmount) < 0.01) {
            console.log('✅ No rounding needed');
            this._rounding_amount = 0;
            console.groupEnd();
            return;
        }

        const roundingProduct = this.pos.db.get_product_by_id(roundingConfig.product_id);
        
        if (!roundingProduct) {
            console.error('❌ Rounding product not found');
            console.groupEnd();
            return;
        }

        console.log(`📦 Using rounding product: ${roundingProduct.display_name} (ID: ${roundingProduct.id})`);

        try {
            // ✅ CRITICAL: Mark product as rounding BEFORE adding
            roundingProduct.is_rounding_line = true;
            
            const roundingLine = this.add_product(roundingProduct, {
                price: roundingAmount,
                quantity: 1,
                merge: false,
                extras: {
                    price_type: 'manual',
                },
            });

            if (roundingLine) {
                // ✅ FORCE SET FLAGS - Multiple approaches
                roundingLine.is_rounding_line = true;
                
                if (roundingLine.product) {
                    roundingLine.product.is_rounding_line = true;
                }
                
                // ✅ Also set a custom property that we can check
                roundingLine.gm_is_rounding = true;
                
                this._rounding_applied = true;
                this._rounding_amount = roundingAmount;
                
                console.log('✅ Rounding line added with flags:');
                console.log('   Line CID:', roundingLine.cid);
                console.log('   line.is_rounding_line:', roundingLine.is_rounding_line);
                console.log('   line.gm_is_rounding:', roundingLine.gm_is_rounding);
                console.log('   product.is_rounding_line:', roundingLine.product?.is_rounding_line);
                console.log('   product.id:', roundingLine.product?.id);
                console.log('   config.rounding_product_id:', this.pos.config.rounding_product_id);
                console.log('   Amount:', roundingAmount);
                
                // ✅ VERIFY FLAGS IMMEDIATELY
                const verification = this.verifyRoundingLine(roundingLine);
                console.log('   Verification:', verification);
                
            } else {
                console.error('❌ Failed to add rounding line');
            }
        } catch (error) {
            console.error('❌ Error adding rounding line:', error);
        }

        console.groupEnd();
    },

    /**
     * Verify if a line is a rounding line using multiple methods
     */
    verifyRoundingLine(line) {
        const methods = {
            byFlag: line.is_rounding_line === true,
            byGmFlag: line.gm_is_rounding === true,
            byProductFlag: line.product?.is_rounding_line === true,
            byProductId: line.product?.id === this.pos?.config?.rounding_product_id,
        };
        
        const isRounding = Object.values(methods).some(v => v === true);
        
        return {
            isRounding,
            methods,
            productId: line.product?.id,
            configProductId: this.pos?.config?.rounding_product_id,
        };
    },

    removeRoundingLine() {
        try {
            const allLines = this.get_orderlines();
            
            console.log('🔍 [REMOVE ROUNDING] Checking orderlines:', allLines.length);
            
            const roundingLines = allLines.filter(line => {
                const verification = this.verifyRoundingLine(line);
                if (verification.isRounding) {
                    console.log(`🔍 [REMOVE ROUNDING] Found rounding line:`, verification);
                }
                return verification.isRounding;
            });
            
            if (roundingLines.length > 0) {
                console.log(`🗑️ [REMOVE ROUNDING] Removing ${roundingLines.length} rounding line(s)`);
                roundingLines.forEach((line) => {
                    console.log(`   - Removing:`, {
                        product: line.product?.display_name,
                        amount: line.get_price_with_tax(),
                    });
                    this.removeOrderline(line);
                });
                this._rounding_applied = false;
                this._rounding_amount = 0;
            } else {
                console.log('ℹ️ [REMOVE ROUNDING] No rounding lines found');
            }
        } catch (error) {
            console.error('❌ Error removing rounding line:', error);
        }
    },

    export_as_JSON() {
        const json = super.export_as_JSON(...arguments);
        json._rounding_applied = this._rounding_applied || false;
        json._rounding_amount = this._rounding_amount || 0;
        return json;
    },

    init_from_JSON(json) {
        super.init_from_JSON(...arguments);
        this._rounding_applied = json._rounding_applied || false;
        this._rounding_amount = json._rounding_amount || 0;
    },
});

console.log("✅ [AUTO ROUNDING v6] Loaded with aggressive flag setting");