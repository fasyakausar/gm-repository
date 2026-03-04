/** @odoo-module */

import { ClosePosPopup } from "@point_of_sale/app/navbar/closing_popup/closing_popup";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { ConnectionLostError } from "@web/core/network/rpc_service";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";
import { useEffect } from "@odoo/owl";

// =====================================================
// Shared Helper Functions
// =====================================================
function getDecimalAndThousandSep(formatCurrencyFn) {
    const decimalPoint = formatCurrencyFn(1.5, false).includes(",") ? "," : ".";
    const thousandSep = decimalPoint === "," ? "." : ",";
    return { decimalPoint, thousandSep };
}

function formatWithSeparator(value, formatCurrencyFn) {
    const { decimalPoint, thousandSep } = getDecimalAndThousandSep(formatCurrencyFn);

    let raw = String(value).replace(/[^\d.,]/g, "");
    let [intPart, ...decParts] = raw.split(decimalPoint);
    const decPart = decParts.join(decimalPoint);

    intPart = intPart.replace(/[.,]/g, "");
    intPart = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, thousandSep);

    return decPart !== undefined && decParts.length > 0
        ? `${intPart}${decimalPoint}${decPart}`
        : intPart;
}

function parseFormattedValue(value, formatCurrencyFn) {
    const { decimalPoint, thousandSep } = getDecimalAndThousandSep(formatCurrencyFn);
    return parseFloat(
        String(value)
            .replace(new RegExp(`\\${thousandSep}`, "g"), "")
            .replace(decimalPoint, ".")
    ) || 0;
}

patch(ClosePosPopup.prototype, {
    setup() {
        super.setup();

        if (!this.popup) this.popup = useService("popup");
        if (!this.rpc) this.rpc = useService("rpc");
        this.orm = useService("orm");

        useEffect(() => {
            this._hideUnusedSections();
            this._setupInputFormatting();
        });
    },

    _hideUnusedSections() {
        const popup = document.querySelector(".close-pos-popup");
        if (!popup) return;

        popup.querySelectorAll("tbody").forEach((tbody) => {
            if (
                tbody.classList.contains("cash-overview") ||
                tbody.innerText.includes("Opening") ||
                tbody.innerText.includes("Payments in")
            ) {
                tbody.style.display = "none";
            }
        });

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

            newInput.addEventListener("input", (ev) => {
                const cursorPos = ev.target.selectionStart;
                const oldLength = ev.target.value.length;

                const formatted = formatWithSeparator(
                    ev.target.value,
                    this.env.utils.formatCurrency
                );

                if (formatted !== ev.target.value) {
                    ev.target.value = formatted;
                    const newLength = formatted.length;
                    const newCursor = cursorPos + (newLength - oldLength);
                    ev.target.setSelectionRange(newCursor, newCursor);
                }

                const pmId = ev.target.dataset.pmId ||
                    ev.target.closest('[data-pm-id]')?.dataset.pmId;

                if (pmId && this.state.payments[pmId]) {
                    this.state.payments[pmId].counted = formatted;
                }
            });

            newInput.addEventListener("blur", (ev) => {
                const formatted = formatWithSeparator(
                    ev.target.value,
                    this.env.utils.formatCurrency
                );
                ev.target.value = formatted;

                const pmId = ev.target.dataset.pmId ||
                    ev.target.closest('[data-pm-id]')?.dataset.pmId;

                if (pmId && this.state.payments[pmId]) {
                    this.state.payments[pmId].counted = formatted;
                }
            });

            if (newInput.value && newInput.value !== '0') {
                setTimeout(() => {
                    const formatted = formatWithSeparator(
                        newInput.value,
                        this.env.utils.formatCurrency
                    );
                    newInput.value = formatted;

                    const pmId = newInput.dataset.pmId ||
                        newInput.closest('[data-pm-id]')?.dataset.pmId;

                    if (pmId && this.state.payments[pmId]) {
                        this.state.payments[pmId].counted = formatted;
                    }
                }, 100);
            }
        });
    },

    getInitialState() {
        const initialState = super.getInitialState();

        if (this.props.default_cash_details) {
            const cashId = this.props.default_cash_details.id;
            if (initialState.payments[cashId]) {
                const raw = initialState.payments[cashId].counted || "0";
                initialState.payments[cashId].counted = formatWithSeparator(
                    raw,
                    this.env.utils.formatCurrency
                );
            }
        }

        this.props.other_payment_methods?.forEach((pm) => {
            if (pm && initialState.payments[pm.id]) {
                const raw = initialState.payments[pm.id].counted || "0";
                initialState.payments[pm.id].counted = formatWithSeparator(
                    raw,
                    this.env.utils.formatCurrency
                );
            }
        });

        return initialState;
    },

    getDifference(paymentId) {
        const countedStr = this.state.payments[paymentId]?.counted || "0";
        const counted = parseFormattedValue(countedStr, this.env.utils.formatCurrency);

        let expectedAmount = 0;
        if (paymentId === this.props.default_cash_details?.id) {
            expectedAmount = this.props.default_cash_details.amount;
        } else {
            const pm = this.props.other_payment_methods?.find((p) => p.id === paymentId);
            expectedAmount = pm?.amount || 0;
        }

        return counted - expectedAmount;
    },

    /**
     * Ambil counted cash dari DOM secara langsung sebagai fallback,
     * karena state.payments mungkin tidak ter-update ketika input di-clone.
     */
    _getCountedCashFromDOM() {
        const popup = document.querySelector(".close-pos-popup");
        if (!popup) return null;

        // Cari input pertama yang visible (input cash/counted)
        const inputs = popup.querySelectorAll("input");
        for (const input of inputs) {
            const val = input.value;
            if (val && val !== "0" && val !== "") {
                const parsed = parseFormattedValue(val, this.env.utils.formatCurrency);
                if (parsed > 0) {
                    console.log("[ClosingPopup] counted cash from DOM input:", parsed);
                    return parsed;
                }
            }
        }
        return null;
    },

    async closeSession() {
        // ── DEBUG: log state payments sebelum parse ───────────────────────────
        console.log("[ClosingPopup] state.payments BEFORE parse:",
            JSON.parse(JSON.stringify(this.state.payments))
        );
        console.log("[ClosingPopup] default_cash_details:",
            this.props.default_cash_details
        );

        // ✅ Parse semua formatted value ke numeric sebelum dikirim ke backend
        Object.keys(this.state.payments).forEach((paymentId) => {
            if (this.state.payments[paymentId]?.counted !== undefined) {
                const numeric = parseFormattedValue(
                    this.state.payments[paymentId].counted,
                    this.env.utils.formatCurrency
                );
                this.state.payments[paymentId].counted = String(numeric);
            }
        });

        // ── DEBUG: log state payments setelah parse ───────────────────────────
        console.log("[ClosingPopup] state.payments AFTER parse:",
            JSON.parse(JSON.stringify(this.state.payments))
        );

        this.customerDisplay?.update({ closeUI: true });

        const syncSuccess = await this.pos.push_orders_with_closing_popup();
        if (!syncSuccess) return;

        if (this.pos.config.cash_control && this.props.default_cash_details) {
            const cashId = this.props.default_cash_details.id;

            // ── Cara 1: ambil dari state.payments ────────────────────────────
            let countedCash = parseFloat(
                this.state.payments[cashId]?.counted || "0"
            );

            // ── Cara 2: fallback dari DOM jika state = 0 ─────────────────────
            // Ini terjadi karena input di-clone di _setupInputFormatting,
            // sehingga event listener baru tidak ter-bind ke state Owl
            if (!countedCash || countedCash === 0) {
                const domValue = this._getCountedCashFromDOM();
                if (domValue && domValue > 0) {
                    countedCash = domValue;
                    console.log("[ClosingPopup] ⚠️ state=0, using DOM value:", countedCash);
                }
            }

            console.log("[ClosingPopup] Final countedCash to send:", countedCash,
                "| cashId:", cashId,
                "| state.payments[cashId]:", this.state.payments[cashId]
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