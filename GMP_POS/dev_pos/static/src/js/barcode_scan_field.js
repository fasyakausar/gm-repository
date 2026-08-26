/** @odoo-module **/

import { registry } from "@web/core/registry";
import { CharField, charField } from "@web/views/fields/char/char_field";
import { onWillDestroy } from "@odoo/owl";

export class BarcodeScanInputField extends CharField {
    setup() {
        super.setup();
        this.scanTimer = null;
        onWillDestroy(() => clearTimeout(this.scanTimer));
    }

    /**
     * Scanner (PDT / kamera) mengetik karakter sangat cepat (~5-30ms antar
     * karakter). Manusia mengetik jauh lebih lambat. Kita manfaatkan jeda
     * ini: kalau tidak ada karakter baru dalam 180ms, anggap scan selesai
     * dan langsung trigger onchange — tidak perlu Enter/blur manual.
     */
    onInput(ev) {
        super.onInput(ev);
        clearTimeout(this.scanTimer);
        const value = ev.target.value;
        if (!value) return;
        this.scanTimer = setTimeout(() => this._commitScan(value), 180);
    }

    // Kalau scanner/user tetap mengirim Enter, langsung commit — jangan
    // tunggu debounce lagi, dan cegah submit form.
    onKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            clearTimeout(this.scanTimer);
            this._commitScan(ev.target.value);
            return;
        }
        super.onKeydown(ev);
    }

    async _commitScan(value) {
        if (!value) return;
        // record.update() akan otomatis memanggil onchange Python
        // yang sudah didefinisikan di field ini (_onchange_barcode_input)
        await this.props.record.update({ [this.props.name]: value });
    }
}

export const barcodeScanInputField = {
    ...charField,
    component: BarcodeScanInputField,
};

registry.category("fields").add("barcode_scan_input", barcodeScanInputField);