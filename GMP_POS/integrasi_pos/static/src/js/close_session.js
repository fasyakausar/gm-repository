/** @odoo-module */

import { ClosePosPopup } from "@point_of_sale/app/navbar/closing_popup/closing_popup";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { ConnectionLostError } from "@web/core/network/rpc_service";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";
import { useEffect } from "@odoo/owl";

patch(ClosePosPopup.prototype, {
    setup() {
        super.setup();

        if (!this.popup) this.popup = useService("popup");
        if (!this.rpc) this.rpc = useService("rpc");
        this.orm = useService("orm");

        useEffect(() => {
            // Bersihkan semua section yang tidak diperlukan
            this._hideUnusedSections();
            
            // Format semua input yang nilainya bisa diubah (termasuk yang 0)
            this._setupInputFormatting();
        });
    },

    _hideUnusedSections() {
        const popup = document.querySelector(".close-pos-popup");
        if (!popup) return;

        // Sembunyikan semua tbody dengan class cash-overview atau mengandung text tertentu
        popup.querySelectorAll("tbody").forEach((tbody) => {
            if (
                tbody.classList.contains("cash-overview") ||
                tbody.innerText.includes("Opening") ||
                tbody.innerText.includes("Payments in")
            ) {
                tbody.style.display = "none";
            }
        });

        // Sembunyikan row individual
        popup.querySelectorAll("tr").forEach((tr) => {
            const text = tr.innerText || "";
            if (text.includes("Opening") || text.includes("Payments in")) {
                tr.style.display = "none";
            }
        });
    },

    _setupInputFormatting() {
        const popup = document.querySelector(".close-pos-popup");
        if (!popup) return;

        const inputs = popup.querySelectorAll("input");
        
        inputs.forEach((input) => {
            const newInput = input.cloneNode(true);
            input.parentNode.replaceChild(newInput, input);
            
            newInput.addEventListener("blur", (ev) => {
                let value = ev.target.value;
                
                // ✅ Izinkan digit, titik, dan koma — lalu bersihkan koma (thousand separator lama)
                value = value.replace(/,/g, '');  // hapus koma dulu
                value = value.replace(/[^\d.]/g, '');  // hapus selain digit dan titik

                // Pastikan hanya ada satu titik desimal
                const parts = value.split('.');
                if (parts.length > 2) {
                    value = parts[0] + '.' + parts.slice(1).join('');
                }
                
                if (value && value !== '') {
                    const num = parseFloat(value);  // ✅ parseFloat, bukan parseInt
                    
                    if (!isNaN(num)) {
                        // ✅ Format dengan desimal (maksimal 2 digit)
                        const formatted = num.toLocaleString('en-US', {
                            minimumFractionDigits: 0,
                            maximumFractionDigits: 2,
                        });
                        ev.target.value = formatted;
                        
                        const pmId = ev.target.dataset.pmId || 
                                    ev.target.closest('[data-pm-id]')?.dataset.pmId;
                        
                        if (pmId && this.state.payments[pmId]) {
                            this.state.payments[pmId].counted = formatted;
                        }
                    }
                }
            });

            if (newInput.value && newInput.value !== '0') {
                setTimeout(() => {
                    const event = new Event('blur', { bubbles: true });
                    newInput.dispatchEvent(event);
                }, 100);
            }
        });
    },

    getInitialState() {
        // Panggil super untuk mendapatkan state awal
        const initialState = super.getInitialState();
        
        // Pastikan semua payment method dengan nilai 0 menggunakan format "0"
        if (this.props.default_cash_details && this.props.default_cash_details.amount === 0) {
            if (initialState.payments[this.props.default_cash_details.id]) {
                initialState.payments[this.props.default_cash_details.id].counted = "0";
            }
        }
        
        this.props.other_payment_methods?.forEach((pm) => {
            if (pm && pm.amount === 0 && initialState.payments[pm.id]) {
                initialState.payments[pm.id].counted = "0";
            }
        });
        
        return initialState;
    },

    getDifference(paymentId) {
        const countedStr = this.state.payments[paymentId]?.counted || "0";
        // Hapus koma sebelum parse
        const counted = parseFloat(countedStr.replace(/,/g, '')) || 0;
        
        let expectedAmount = 0;
        if (paymentId === this.props.default_cash_details?.id) {
            expectedAmount = this.props.default_cash_details.amount;
        } else {
            const pm = this.props.other_payment_methods?.find(p => p.id === paymentId);
            expectedAmount = pm?.amount || 0;
        }
        
        return counted - expectedAmount;
    },

    async closeSession() {
        // Hapus semua koma dari state sebelum menyimpan
        Object.keys(this.state.payments).forEach(paymentId => {
            if (this.state.payments[paymentId]?.counted) {
                this.state.payments[paymentId].counted = 
                    this.state.payments[paymentId].counted.replace(/,/g, '');
            }
        });

        this.customerDisplay?.update({ closeUI: true });

        const syncSuccess = await this.pos.push_orders_with_closing_popup();
        if (!syncSuccess) return;

        if (this.pos.config.cash_control && this.props.default_cash_details) {
            const countedCash = parseFloat(
                this.state.payments[this.props.default_cash_details.id]?.counted || "0"
            );
            const response = await this.orm.call(
                "pos.session",
                "post_closing_cash_details",
                [this.pos.pos_session.id],
                { counted_cash: countedCash }
            );
            if (!response?.successful) return this.handleClosingError(response);
        }

        try {
            await this.orm.call("pos.session", "update_closing_control_state_session", [
                this.pos.pos_session.id,
                this.state.notes,
            ]);
        } catch (error) {
            if (!error.data || error.data.message !== "This session is already closed.") throw error;
        }

        try {
            const bankPaymentMethodDiffPairs = this.props.other_payment_methods
                ?.filter((pm) => pm && pm.type === "bank")
                .map((pm) => [pm.id, this.getDifference(pm.id)]) || [];

            const response = await this.orm.call("pos.session", "close_session_from_ui", [
                this.pos.pos_session.id,
                bankPaymentMethodDiffPairs,
            ]);

            if (!response?.successful) return this.handleClosingError(response);
            this.pos.redirectToBackend();
        } catch (error) {
            if (error instanceof ConnectionLostError) throw error;
            await this.popup.add(ErrorPopup, {
                title: _t("Closing session error"),
                body: _t(
                    "An error has occurred when trying to close the session.\n" +
                    "You will be redirected to the back-end to manually close the session."
                ),
            });
            this.pos.redirectToBackend();
        }
    },
});