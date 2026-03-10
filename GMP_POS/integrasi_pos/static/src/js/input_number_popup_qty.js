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

        // ✅ Keyboard handler
        this._onKeyDown = (ev) => {
            // Hindari konflik jika ada popup lain di atas
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
            // Focus input agar user tahu popup aktif
            this.inputRef.el?.focus();
            // Pasang listener di window
            window.addEventListener("keydown", this._onKeyDown);
        });

        onWillUnmount(() => {
            // Wajib di-remove agar tidak bocor ke screen lain
            window.removeEventListener("keydown", this._onKeyDown);
        });
    }

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
        // Ambil karakter terakhir yang diketik
        const raw = ev.target.value.replace(/\./g, '').replace(',', '.');
        // Reset inputValue dari raw value
        const cleaned = raw.replace('.', ',');
        this.state.inputValue = cleaned;
        this.updateDisplayValue();
        // Set cursor ke akhir
        ev.target.value = this.state.displayValue;
    }

    // Handle keyboard shortcut Enter & Escape
    onKeyDown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.confirmInput();
        } else if (ev.key === "Escape") {
            ev.preventDefault();
            this.cancel();
        }
    }

    handleKeyClick(key) {
        if (key === "⌫") {
            this.removeLastChar();
        } else {
            this.addNumber(key);
        }
    }
}