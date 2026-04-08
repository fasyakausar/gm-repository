/** @odoo-module */

import { Order, Orderline } from "@point_of_sale/app/store/models";
import { patch } from "@web/core/utils/patch";
// Di bagian atas file, tambahkan import jika belum ada:
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";

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
        const order = this;
        const pos = order.pos;
        const currentPartner = order.get_partner();

        console.group("💰 [GIFT CARD VALIDATION]");
        console.log("Order total (with tax):", order.get_total_with_tax());

        const giftCardRewardLines = order.get_orderlines().filter(line => 
            line.is_reward_line && 
            line.reward_id && 
            pos.reward_by_id[line.reward_id]?.program_id?.program_type === 'gift_card'
        );

        console.log("Gift card reward lines found:", giftCardRewardLines.length);

        if (giftCardRewardLines.length > 0) {
            // Kumpulkan semua coupon_id
            const couponIds = [];
            for (const line of giftCardRewardLines) {
                if (line.coupon_id) {
                    couponIds.push(line.coupon_id);
                }
            }

            if (couponIds.length === 0) {
                console.warn("No coupon IDs found in gift card lines");
                console.groupEnd();
                return super.pay(...arguments);
            }

            // 🔥 FETCH DATA GIFT CARD LANGSUNG DARI SERVER (ORM)
            let giftCards = [];
            try {
                giftCards = await pos.orm.searchRead(
                    'loyalty.card',
                    [['id', 'in', couponIds]],
                    ['id', 'code', 'points', 'partner_id', 'program_id']
                );
                console.log("Fetched gift cards from server:", giftCards);
            } catch (error) {
                console.error("Failed to fetch gift cards from server:", error);
                await pos.popup.add(ErrorPopup, {
                    title: "Error Validasi Gift Card",
                    body: "Gagal mengambil data gift card dari server. Silakan coba lagi.",
                });
                console.groupEnd();
                return;
            }

            if (giftCards.length === 0) {
                console.warn("No gift cards found on server for these coupons");
                console.groupEnd();
                return super.pay(...arguments);
            }

            // Hitung total saldo & kumpulkan partner_id
            let totalGiftCardBalance = 0;
            const partnerIds = new Set();
            let expectedPartnerName = "";

            for (const card of giftCards) {
                totalGiftCardBalance += card.points || 0;
                if (card.partner_id) {
                    const pid = Array.isArray(card.partner_id) ? card.partner_id[0] : card.partner_id;
                    partnerIds.add(Number(pid));
                    // Ambil nama partner jika belum ada
                    if (!expectedPartnerName) {
                        const partner = pos.db.get_partner_by_id(pid);
                        expectedPartnerName = partner ? partner.name : `ID ${pid}`;
                    }
                }
            }

            console.log("Total gift card balance (from server):", totalGiftCardBalance);
            console.log("Partner IDs from gift cards:", Array.from(partnerIds));

            // Validasi customer
            const uniquePartnerIds = Array.from(partnerIds);
            if (uniquePartnerIds.length > 1) {
                await pos.popup.add(ErrorPopup, { 
                    title: "Gift Card Tidak Konsisten", 
                    body: "Gift card yang ditebus berasal dari customer berbeda. Silakan gunakan satu customer saja." 
                });
                console.groupEnd();
                return;
            }

            if (uniquePartnerIds.length === 1) {
                const expectedPartnerId = uniquePartnerIds[0];
                if (!currentPartner || Number(currentPartner.id) !== expectedPartnerId) {
                    await pos.popup.add(ErrorPopup, { 
                        title: "Gift Card Tidak Sesuai", 
                        body: `Gift card ini milik customer: ${expectedPartnerName}.\n\nSilakan pilih customer yang benar.` 
                    });
                    console.groupEnd();
                    return;
                }
            }

            // Validasi total belanja vs saldo gift card
            const orderTotal = order.get_total_with_tax();
            if (orderTotal < totalGiftCardBalance) {
                const fmt = (amt) => pos.format_currency ? pos.format_currency(amt) : `Rp ${amt.toLocaleString('id-ID')}`;
                await pos.popup.add(ErrorPopup, {
                    title: "Total Belanja Kurang",
                    body: `Total belanja (${fmt(orderTotal)}) kurang dari saldo gift card (${fmt(totalGiftCardBalance)}).\nSilakan tambah produk.`,
                });
                console.groupEnd();
                return;
            } else {
                console.log("✅ Order total sufficient for gift card balance");
            }
        } else {
            console.log("No gift card rewards in this order");
        }

        console.log("Total Due:", order.get_total_with_tax());
        console.log("Total Paid:", order.get_total_paid());
        console.groupEnd();

        // Auto rounding
        try { this.applyAutoRounding(); } catch (e) { console.error(e); }

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