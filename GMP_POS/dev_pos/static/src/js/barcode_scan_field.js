/** @odoo-module **/

import { registry } from "@web/core/registry";
import { CharField, charField } from "@web/views/fields/char/char_field";
import { onWillDestroy } from "@odoo/owl";

export class BarcodeScanInputField extends CharField {
    setup() {
        super.setup();

        this.scanTimer = null;
        this.lastValue = "";

        onWillDestroy(() => {
            if (this.scanTimer) {
                clearTimeout(this.scanTimer);
            }
        });
    }

    onInput(ev) {
        super.onInput(ev);

        const value = ev.target.value?.trim() || "";

        this.lastValue = value;

        if (this.scanTimer) {
            clearTimeout(this.scanTimer);
            this.scanTimer = null;
        }

        if (!value) {
            return;
        }

        // Tunggu 300ms setelah karakter terakhir.
        // Jika tidak ada karakter baru, barcode dianggap selesai.
        this.scanTimer = setTimeout(() => {
            this._commitScan();
        }, 300);
    }

    onKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();

            if (this.scanTimer) {
                clearTimeout(this.scanTimer);
                this.scanTimer = null;
            }

            this._commitScan();
            return;
        }

        super.onKeydown(ev);
    }

    async _commitScan() {
        const value = this.lastValue?.trim();

        if (!value) {
            return;
        }

        if (this.scanTimer) {
            clearTimeout(this.scanTimer);
            this.scanTimer = null;
        }

        this.lastValue = "";

        await this.props.record.update({
            [this.props.name]: value,
        });
    }
}

export const barcodeScanInputField = {
    ...charField,
    component: BarcodeScanInputField,
};

registry.category("fields").add(
    "barcode_scan_input",
    barcodeScanInputField
);