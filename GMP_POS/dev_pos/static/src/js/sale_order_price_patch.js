/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ListRenderer } from "@web/views/list/list_renderer";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { Component, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

// ============================================================
// PIN Dialog Component
// ============================================================
export class SalePinDialog extends Component {
    static template = "dev_pos.SalePinDialog";
    static props = {
        close: Function,
        confirm: Function,
    };

    setup() {
        this.state = useState({ pin: "", error: "" });
    }

    onInput(ev) {
        this.state.pin = ev.target.value;
        this.state.error = "";
    }

    onConfirm() {
        if (!this.state.pin) {
            this.state.error = _t("PIN tidak boleh kosong.");
            return;
        }
        this.props.confirm(this.state.pin);
    }

    onCancel() {
        this.props.close();
    }
}

registry.category("dialogs").add("sale_pin_dialog", SalePinDialog);