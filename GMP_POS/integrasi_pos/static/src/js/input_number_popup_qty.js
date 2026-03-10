/** @odoo-module **/

import { AbstractAwaitablePopup } from "@point_of_sale/app/popup/abstract_awaitable_popup";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";

export class InputNumberPopUpQty extends AbstractAwaitablePopup {
    static template = "integrasi_pos.InputNumberPopUpQty";

    setup() {
        super.setup();
        this.popup = useService("popup");
        this.inputRef = useRef("numberInput");

        this.state = useState({
            inputValue: "",
            displayValue: "",
        });

        // Keyboard handler
        this._onKeyDown = (ev) => {
            if (ev.defaultPrevented) return;
            const key = ev.key;
            if (key >= "0" && key <= "9") {
                ev.preventDefault();
                this.addNumber(key);
            } else if (key === "." || key === ",") {
                ev.preventDefault();
                this.addNumber(".");
            } else if (key === "Backspace") {
                ev.preventDefault();
                this.removeLastChar();
            } else if (key === "Enter") {
                ev.preventDefault();
                this.confirmInput();
            } else if (key === "Escape") {
                ev.preventDefault();
                this.cancel();
            }
        };

        onMounted(() => {
            this.inputRef.el?.focus();
            window.addEventListener("keydown", this._onKeyDown);
        });

        onWillUnmount(() => {
            window.removeEventListener("keydown", this._onKeyDown);
        });
    }

    // ─── Numpad: handler utama via data-num ───────────────────────

    /**
     * Handler untuk click (mouse/desktop)
     */
    onNumpadClick(ev) {
        const num = ev.currentTarget.dataset.num;
        if (!num) return;
        if (num === "backspace") {
            this.removeLastChar();
        } else {
            this.addNumber(num);
        }
    }

    /**
     * Handler untuk touchstart (touchscreen)
     * preventDefault() mencegah ghost click ~300ms setelah touch
     */
    onNumpadTouch(ev) {
        ev.preventDefault();
        const num = ev.currentTarget.dataset.num;
        if (!num) return;
        if (num === "backspace") {
            this.removeLastChar();
        } else {
            this.addNumber(num);
        }
    }

    // ─── Action buttons touch handlers ───────────────────────────

    onConfirmTouch(ev) {
        ev.preventDefault();
        this.confirmInput();
    }

    onCancelTouch(ev) {
        ev.preventDefault();
        this.cancel();
    }

    // ─── Format helpers ───────────────────────────────────────────

    formatNumber(value) {
        if (!value) return "";
        const parts = value.split(',');
        const integerPart = parts[0];
        const decimalPart = parts[1];
        const formattedInteger = integerPart.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
        return decimalPart !== undefined
            ? `${formattedInteger},${decimalPart}`
            : formattedInteger;
    }

    updateDisplayValue() {
        this.state.displayValue = this.formatNumber(this.state.inputValue);
    }

    // ─── Core logic ───────────────────────────────────────────────

    addNumber(num) {
        if (num === ".") {
            if (!this.state.inputValue.includes(",")) {
                this.state.inputValue += ",";
            }
        } else if (/[0-9]/.test(num)) {
            this.state.inputValue += num;
        }
        this.updateDisplayValue();
    }

    removeLastChar() {
        this.state.inputValue = this.state.inputValue.slice(0, -1);
        this.updateDisplayValue();
    }

    clearInput() {
        this.state.inputValue = "";
        this.state.displayValue = "";
    }

    confirmInput() {
        const input = this.state.inputValue.trim();
        if (!input || isNaN(parseFloat(input.replace(',', '.')))) {
            this.popup.add(ErrorPopup, {
                title: _t("Input tidak valid"),
                body: _t("Harap masukkan angka yang valid."),
            });
            return;
        }
        const standardFormat = input.replace(',', '.');
        this.props.resolve({ input: parseFloat(standardFormat) });
        this.cancel();
    }

    // Handle ketik langsung di input field
    onInputKeyboard(ev) {
        const raw = ev.target.value.replace(/\./g, '').replace(',', '.');
        const cleaned = raw.replace('.', ',');
        this.state.inputValue = cleaned;
        this.updateDisplayValue();
        ev.target.value = this.state.displayValue;
    }

    onKeyDown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.confirmInput();
        } else if (ev.key === "Escape") {
            ev.preventDefault();
            this.cancel();
        }
    }

    // Alias untuk backward compat (dipanggil dari tempat lain jika ada)
    handleKeyClick(key) {
        if (key === "⌫") {
            this.removeLastChar();
        } else {
            this.addNumber(key);
        }
    }
}