/** @odoo-module **/

import { TextInputPopup } from "@point_of_sale/app/utils/input_popups/text_input_popup";
import { _t } from "@web/core/l10n/translation";
import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";

// =====================================================
// BUTTON 1: GM Invoice E-Commerce
// =====================================================
export class GmInvoiceButton extends Component {
    static template = "GmInvoiceButton";
    static props = { label: { type: String, optional: true } };

    setup() {
        this.popup = useService("popup");
        this.pos = usePos();
        this.label = this.props.label || _t("Nota Online");
    }

    async onClick() {
        const currentOrder = this.pos.get_order();
        if (!currentOrder) return;

        const existing = currentOrder.getGmInvoiceNumber?.() || "";

        const { confirmed, payload } = await this.popup.add(TextInputPopup, {
            title: _t("E-Commerce Invoice Number"),
            placeholder: _t("Enter invoice number (optional)"),
            startingValue: existing,
        });

        if (confirmed) {
            currentOrder.setGmInvoiceNumber(payload.trim());
            console.log("📝 [GM INVOICE] Set:", payload.trim());
        }
    }
}

// =====================================================
// BUTTON 2: PO Customer
// =====================================================
export class PoCustomerButton extends Component {
    static template = "PoCustomerButton";
    static props = { label: { type: String, optional: true } };

    setup() {
        this.popup = useService("popup");
        this.pos = usePos();
        this.label = this.props.label || _t("PO Customer");
    }

    async onClick() {
        const currentOrder = this.pos.get_order();
        if (!currentOrder) return;

        const existing = currentOrder.getGmPoCustomer?.() || "";

        const { confirmed, payload } = await this.popup.add(TextInputPopup, {
            title: _t("PO Customer"),
            placeholder: _t("Enter PO Customer number (optional)"),
            startingValue: existing,
        });

        if (confirmed) {
            currentOrder.setGmPoCustomer(payload.trim());
            console.log("📝 [PO CUSTOMER] Set:", payload.trim());
        }
    }
}

// =====================================================
// BUTTON 3: Nota Manual
// =====================================================
export class NotaManualButton extends Component {
    static template = "NotaManualButton";
    static props = { label: { type: String, optional: true } };

    setup() {
        this.popup = useService("popup");
        this.pos = usePos();
        this.label = this.props.label || _t("Nota Manual");
    }

    async onClick() {
        const currentOrder = this.pos.get_order();
        if (!currentOrder) return;

        const existing = currentOrder.getGmNotaManual?.() || "";

        const { confirmed, payload } = await this.popup.add(TextInputPopup, {
            title: _t("Nota Manual"),
            placeholder: _t("Enter Nota Manual number (optional)"),
            startingValue: existing,
        });

        if (confirmed) {
            currentOrder.setGmNotaManual(payload.trim());
            console.log("📝 [NOTA MANUAL] Set:", payload.trim());
        }
    }
}

// =====================================================
// Register all buttons on ProductScreen
// =====================================================
ProductScreen.addControlButton({
    component: GmInvoiceButton,
    condition: () => true,
    position: ["before", "SetPriceButton"],
});

ProductScreen.addControlButton({
    component: PoCustomerButton,
    condition: () => true,
    position: ["before", "SetPriceButton"],
});

ProductScreen.addControlButton({
    component: NotaManualButton,
    condition: () => true,
    position: ["before", "SetPriceButton"],
});