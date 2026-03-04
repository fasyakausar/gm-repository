/** @odoo-module */

import { Order } from "@point_of_sale/app/store/models";
import { patch } from "@web/core/utils/patch";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { TextInputPopup } from "@point_of_sale/app/utils/input_popups/text_input_popup";
import { _t } from "@web/core/l10n/translation";

// =====================================================
// PATCH ORDER - Store all custom field state
// =====================================================
patch(Order.prototype, {
    setup() {
        super.setup(...arguments);
        this.gm_invoice_e_commerce = this.gm_invoice_e_commerce || "";
        this.gm_po_customer    = this.gm_po_customer    || "";
        this.gm_nota_manual    = this.gm_nota_manual    || "";
    },

    // --- GM Invoice E-Commerce ---
    getGmInvoiceNumber()  { return this.gm_invoice_e_commerce || ""; },
    setGmInvoiceNumber(v) { this.gm_invoice_e_commerce = v || ""; },

    // --- PO Customer ---
    getGmPoCustomer()     { return this.gm_po_customer || ""; },
    setGmPoCustomer(v)    { this.gm_po_customer = v || ""; },

    // --- Nota Manual ---
    getGmNotaManual()     { return this.gm_nota_manual || ""; },
    setGmNotaManual(v)    { this.gm_nota_manual = v || ""; },

    // --- Serialization ---
    export_as_JSON() {
        const json = super.export_as_JSON(...arguments);
        // Use Python field names so Odoo ORM stores them directly
        json.gm_invoice_e_commerce = this.gm_invoice_e_commerce || "";
        json.gm_po_customer        = this.gm_po_customer    || "";
        json.gm_nota_manual        = this.gm_nota_manual    || "";
        return json;
    },

    init_from_JSON(json) {
        super.init_from_JSON(...arguments);
        this.gm_invoice_e_commerce = json.gm_invoice_e_commerce || "";
        this.gm_po_customer    = json.gm_po_customer        || "";
        this.gm_nota_manual    = json.gm_nota_manual        || "";
    },
});

console.log("✅ [GM FIELDS] Order patch loaded");

// =====================================================
// PATCH PaymentScreen - Edit helpers for badges
// =====================================================
patch(PaymentScreen.prototype, {

    async editInvoiceNumber() {
        const order = this.currentOrder;
        const { confirmed, payload } = await this.popup.add(TextInputPopup, {
            title: _t("E-Commerce Invoice Number"),
            placeholder: _t("Enter invoice number (optional)"),
            startingValue: order.getGmInvoiceNumber?.() || "",
        });
        if (confirmed) order.setGmInvoiceNumber(payload.trim());
    },

    async editPoCustomer() {
        const order = this.currentOrder;
        const { confirmed, payload } = await this.popup.add(TextInputPopup, {
            title: _t("PO Customer"),
            placeholder: _t("Enter PO Customer number (optional)"),
            startingValue: order.getGmPoCustomer?.() || "",
        });
        if (confirmed) order.setGmPoCustomer(payload.trim());
    },

    async editNotaManual() {
        const order = this.currentOrder;
        const { confirmed, payload } = await this.popup.add(TextInputPopup, {
            title: _t("Nota Manual"),
            placeholder: _t("Enter Nota Manual number (optional)"),
            startingValue: order.getGmNotaManual?.() || "",
        });
        if (confirmed) order.setGmNotaManual(payload.trim());
    },
});

console.log("✅ [GM FIELDS] PaymentScreen patch loaded");