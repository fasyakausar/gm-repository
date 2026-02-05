/** @odoo-module **/

import { AbstractAwaitablePopup } from "@point_of_sale/app/popup/abstract_awaitable_popup";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { useState, useRef, onMounted } from "@odoo/owl";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";

export class InputNumberPopUpQty extends AbstractAwaitablePopup {
    static template = "integrasi_pos.InputNumberPopUpQty";

    setup() {
        super.setup();
        this.popup = useService("popup");
        this.inputRef = useRef("numberInput");

        onMounted(() => {
            this.inputRef.el?.focus();
        });

        this.state = useState({
            inputValue: "",      // Raw value without formatting
            displayValue: "",    // Formatted value with separators
        });

        this.handleKeyClick = (key) => {
            if (key === "⌫") {
                this.removeLastChar();
            } else {
                this.addNumber(key);
            }
        };
    }

    // ✅ Format number with thousand separator (Indonesian format)
    formatNumber(value) {
        if (!value) return "";
        
        // Split by comma (decimal separator)
        const parts = value.split(',');
        const integerPart = parts[0];
        const decimalPart = parts[1];

        // Add thousand separator (dot)
        const formattedInteger = integerPart.replace(/\B(?=(\d{3})+(?!\d))/g, '.');

        // Combine with decimal part if exists
        return decimalPart !== undefined 
            ? `${formattedInteger},${decimalPart}` 
            : formattedInteger;
    }

    // ✅ Update display value with formatting
    updateDisplayValue() {
        this.state.displayValue = this.formatNumber(this.state.inputValue);
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

        // Convert Indonesian format (comma as decimal) to standard format
        const standardFormat = input.replace(',', '.');
        this.props.resolve({ input: parseFloat(standardFormat) });
        this.cancel();
    }

    addNumber(num) {
        // Handle decimal point (use comma for Indonesian format)
        if (num === ".") {
            // Prevent multiple decimal separators
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
}