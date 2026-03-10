/** @odoo-module */

import { Order, Orderline } from "@point_of_sale/app/store/models";
import { patch } from "@web/core/utils/patch";

// =====================================================
// PATCH ORDERLINE - Set flag saat dibuat
// =====================================================
patch(Orderline.prototype, {
    init_from_JSON(json) {
        super.init_from_JSON(...arguments);

        if (this.order?.pos?.config?.rounding_product_id &&
            this.product?.id === this.order.pos.config.rounding_product_id) {
            this.is_rounding_line = true;
            console.log('🎯 [ROUNDING FLAG] Set via init_from_JSON:', this.product.display_name);
        }
    },
});

// =====================================================
// PATCH ORDER - Auto rounding + GM Fields
// =====================================================
patch(Order.prototype, {

    // --------------------------------------------------
    // Setup: inisialisasi semua state
    // --------------------------------------------------
    setup() {
        super.setup(...arguments);
        this._rounding_applied = false;
        this._rounding_amount = 0;
        this.gm_invoice_number = this.gm_invoice_number || "";
        this.gm_po_customer    = this.gm_po_customer    || "";
        this.gm_nota_manual    = this.gm_nota_manual    || "";
    },

    // --------------------------------------------------
    // GM Invoice: getter & setter
    // --------------------------------------------------
    getGmInvoiceNumber()  { return this.gm_invoice_number || ""; },
    setGmInvoiceNumber(v) { this.gm_invoice_number = v || ""; },

    // --------------------------------------------------
    // PO Customer: getter & setter
    // --------------------------------------------------
    getGmPoCustomer()     { return this.gm_po_customer || ""; },
    setGmPoCustomer(v)    { this.gm_po_customer = v || ""; },

    // --------------------------------------------------
    // Nota Manual: getter & setter
    // --------------------------------------------------
    getGmNotaManual()     { return this.gm_nota_manual || ""; },
    setGmNotaManual(v)    { this.gm_nota_manual = v || ""; },

    // --------------------------------------------------
    // pay(): rounding only → lanjut ke Payment Screen
    // --------------------------------------------------
    async pay() {
        // Auto rounding
        try {
            this.applyAutoRounding();
        } catch (error) {
            console.error('❌ Error applying auto rounding:', error);
        }

        return super.pay(...arguments);
    },

    // --------------------------------------------------
    // Auto rounding logic
    // --------------------------------------------------
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
        const roundedTotal = Math.ceil(currentTotal / roundingValue) * roundingValue;
        const roundingAmount = roundedTotal - currentTotal;

        console.log('Calculation:', { currentTotal, roundingValue, roundedTotal, roundingAmount });

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
            roundingProduct.is_rounding_line = true;

            const roundingLine = this.add_product(roundingProduct, {
                price: roundingAmount,
                quantity: 1,
                merge: false,
                extras: { price_type: 'manual' },
            });

            if (roundingLine) {
                roundingLine.is_rounding_line = true;
                if (roundingLine.product) {
                    roundingLine.product.is_rounding_line = true;
                }
                roundingLine.gm_is_rounding = true;

                this._rounding_applied = true;
                this._rounding_amount = roundingAmount;

                console.log('✅ Rounding line added:', {
                    cid: roundingLine.cid,
                    amount: roundingAmount,
                    verification: this.verifyRoundingLine(roundingLine),
                });
            } else {
                console.error('❌ Failed to add rounding line');
            }
        } catch (error) {
            console.error('❌ Error adding rounding line:', error);
        }

        console.groupEnd();
    },

    verifyRoundingLine(line) {
        const methods = {
            byFlag: line.is_rounding_line === true,
            byGmFlag: line.gm_is_rounding === true,
            byProductFlag: line.product?.is_rounding_line === true,
            byProductId: line.product?.id === this.pos?.config?.rounding_product_id,
        };
        const isRounding = Object.values(methods).some(v => v === true);
        return { isRounding, methods, productId: line.product?.id, configProductId: this.pos?.config?.rounding_product_id };
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

    // --------------------------------------------------
    // Serialization: simpan semua state ke JSON
    // --------------------------------------------------
    export_as_JSON() {
        const json = super.export_as_JSON(...arguments);
        json._rounding_applied     = this._rounding_applied || false;
        json._rounding_amount      = this._rounding_amount  || 0;
        // Gunakan nama field Python agar Odoo ORM langsung mengenali dan menyimpannya
        json.gm_invoice_e_commerce = this.gm_invoice_number || "";
        json.gm_po_customer        = this.gm_po_customer    || "";
        json.gm_nota_manual        = this.gm_nota_manual    || "";
        return json;
    },

    init_from_JSON(json) {
        super.init_from_JSON(...arguments);
        this._rounding_applied = json._rounding_applied     || false;
        this._rounding_amount  = json._rounding_amount      || 0;
        this.gm_invoice_number = json.gm_invoice_e_commerce || "";
        this.gm_po_customer    = json.gm_po_customer        || "";
        this.gm_nota_manual    = json.gm_nota_manual        || "";
    },
});

console.log("✅ [AUTO ROUNDING v6 + GM FIELDS] Loaded");