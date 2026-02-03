/** @odoo-module **/
import { Order } from "@point_of_sale/app/store/models";
import { patch } from "@web/core/utils/patch";

patch(Order.prototype, {
    setup() {
        super.setup(...arguments);

        // Pastikan flag terdefinisi
        this.is_refund_order = this.is_refund_order || false;

        // ✅ Set default partner dengan multiple fallback
        this._setDefaultCustomerIfNeeded();
    },

    /**
     * ✅ NEW METHOD: Set default customer dengan multiple fallback mechanisms
     */
    _setDefaultCustomerIfNeeded() {
        // Skip jika:
        // 1. Sudah ada partner
        // 2. Adalah refund order
        // 3. Tidak ada config default partner
        if (this.partner || this.is_refund_order || !this.pos.config.default_partner_id) {
            return;
        }

        const defaultCustomerId = Array.isArray(this.pos.config.default_partner_id) 
            ? this.pos.config.default_partner_id[0] 
            : this.pos.config.default_partner_id;

        console.group("🔍 LOADING DEFAULT CUSTOMER");
        console.log("Default customer ID:", defaultCustomerId);

        // ✅ FALLBACK 1: Try db.get_partner_by_id
        let partner = null;
        try {
            if (this.pos.db && this.pos.db.get_partner_by_id) {
                partner = this.pos.db.get_partner_by_id(defaultCustomerId);
                if (partner) {
                    console.log("✅ Found in db.get_partner_by_id:", partner.name);
                }
            }
        } catch (e) {
            console.warn("⚠️ db.get_partner_by_id failed:", e.message);
        }

        // ✅ FALLBACK 2: Try pos.partners array
        if (!partner && this.pos.partners) {
            partner = this.pos.partners.find(p => p.id === defaultCustomerId);
            if (partner) {
                console.log("✅ Found in pos.partners array:", partner.name);
            }
        }

        // ✅ FALLBACK 3: Try db.partner_by_id direct access
        if (!partner && this.pos.db && this.pos.db.partner_by_id) {
            partner = this.pos.db.partner_by_id[defaultCustomerId];
            if (partner) {
                console.log("✅ Found in db.partner_by_id:", partner.name);
            }
        }

        // ✅ FALLBACK 4: Search in all db partners
        if (!partner && this.pos.db && this.pos.db.partner_by_id) {
            const allPartners = Object.values(this.pos.db.partner_by_id);
            partner = allPartners.find(p => p.id === defaultCustomerId);
            if (partner) {
                console.log("✅ Found in db.partner_by_id (searched):", partner.name);
            }
        }

        // Set partner jika ditemukan
        if (partner) {
            this.set_partner(partner);
            console.log("✅ Default customer set successfully:", partner.name);
            console.groupEnd();
        } else {
            console.error("❌ DEFAULT CUSTOMER NOT FOUND!");
            console.error("Available debug info:", {
                defaultCustomerId: defaultCustomerId,
                hasDb: !!this.pos.db,
                dbPartnerCount: this.pos.db ? Object.keys(this.pos.db.partner_by_id || {}).length : 0,
                partnersArrayCount: this.pos.partners ? this.pos.partners.length : 0,
                configDefaultPartner: this.pos.config.default_partner_id,
                samplePartners: this.pos.partners ? this.pos.partners.slice(0, 3).map(p => ({id: p.id, name: p.name})) : []
            });
            console.groupEnd();
        }
    },

    set_is_refund_order(is_refund) {
        this.is_refund_order = is_refund;
    },

    add_orderline(line) {
        const result = super.add_orderline(...arguments);
        if (line && line.quantity < 0 && !this.is_refund_order) {
            this.set_is_refund_order(true);
        }
        return result;
    },

    async add_product(product, options = {}) {
        const result = await super.add_product(...arguments);
        const qty = options.quantity ?? 1;
        if (qty < 0 && !this.is_refund_order) {
            this.set_is_refund_order(true);
        }
        return result;
    },

    init_from_JSON(json) {
        super.init_from_JSON(...arguments);
        const hasNegativeLines = json.lines?.some((line) => line[2]?.qty < 0);
        this.is_refund_order = !!hasNegativeLines;
    },
});