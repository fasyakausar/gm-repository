/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ReprintReceiptButton } from "@point_of_sale/app/screens/ticket_screen/reprint_receipt_button/reprint_receipt_button";
import { InvoiceButton } from "@point_of_sale/app/screens/ticket_screen/invoice_button/invoice_button";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { CustomNumpadPopUp } from "./custom_numpad_popup";

// ============================================================
// Helper: validasi manager via env.services (aman dipanggil di luar setup)
// ============================================================
async function validateManagerAccess(env, configKey) {
    // Ambil services langsung dari env.services — tidak perlu useService()
    const popup = env.services?.popup;
    const pos   = env.services?.pos;

    if (!popup) {
        console.error("[validateManagerAccess] popup service not found in env.services!");
        return false;
    }

    const config = pos?.config || {};

    console.log("[validateManagerAccess]", {
        configKey,
        manager_validation: config.manager_validation,
        flagValue: config[configKey],
    });

    // Jika manager_validation tidak aktif ATAU flag spesifik tidak aktif → lolos tanpa PIN
    if (!config.manager_validation || !config[configKey]) {
        return true;
    }

    const { confirmed } = await popup.add(CustomNumpadPopUp, {
        title: _t("Enter Manager PIN"),
        body: _t("You need manager access to proceed."),
    });

    return confirmed;
}

// ============================================================
// Patch ReprintReceiptButton
// ============================================================
patch(ReprintReceiptButton.prototype, {
    /**
     * setup() di-patch karena komponen asli TIDAK inject:
     *   - this.orm   (dibutuhkan jika perlu RPC)
     *   - this.popup (dibutuhkan oleh useAsyncLockedMethod di click asli)
     * Tanpa ini, this.popup undefined saat click() dipanggil.
     */
    setup() {
        super.setup();
        this.orm   = useService("orm");
        this.popup = useService("popup");
    },

    async click() {
        const isValidated = await validateManagerAccess(
            this.env,
            "validate_reprint_receipt",
        );
        if (!isValidated) return;

        return super.click(...arguments);
    },
});

// ============================================================
// Patch InvoiceButton
// InvoiceButton asli sudah inject this.orm & this.popup — tidak perlu patch setup()
// ============================================================
patch(InvoiceButton.prototype, {
    async click() {
        const isValidated = await validateManagerAccess(
            this.env,
            "validate_reprint_invoice",
        );
        if (!isValidated) return;

        return super.click(...arguments);
    },
});