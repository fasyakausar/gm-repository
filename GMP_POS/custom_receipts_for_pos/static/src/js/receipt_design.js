/** @odoo-module */
import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";
import { patch } from "@web/core/utils/patch";
import { useState, Component, xml } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

patch(OrderReceipt.prototype, {
    setup() {
        super.setup();
        this.state = useState({ template: true });
        this.pos = useState(useService("pos"));
    },

    // ✅ Format tanggal dari Date object atau string ISO
    formatReceiptDate(val) {
        if (!val) return 'N/A';
        try {
            const s = val.toString();
            if (s.includes('T')) {
                const [d, t] = s.split('T');
                return d + ' ' + (t ? t.split('.')[0] : '');
            }
            if (s.includes('/')) {
                const parts = s.split(' ');
                const dParts = parts[0].split('/');
                return dParts[2] + '-' + dParts[1].padStart(2,'0') + '-' + dParts[0].padStart(2,'0') + (parts[1] ? ' ' + parts[1] : '');
            }
            return s;
        } catch(e) {
            return 'N/A';
        }
    },

    // ✅ Strip currency prefix Rp
    stripRp(val) {
        if (!val && val !== 0) return '0';
        return val.toString().replace('Rp','').replace(/\s/g,'').replace('.00','').trim();
    },

    // ✅ Format currency + strip Rp
    fmtCurrency(amount) {
        try {
            const utils = this.pos.env.utils;
            if (utils?.formatCurrency) {
                return this.stripRp(utils.formatCurrency(amount || 0));
            }
        } catch(e) {}
        return (amount || 0).toString();
    },

    get templateProps() {
        const order = this.pos.get_order();
        const partner = order ? order.get_partner() : null;
        const self = this;

        return {
            pos: this.pos,
            data: this.props.data,
            order: order,
            receipt: this.props.data,
            orderlines: this.props.data.orderlines,
            paymentlines: this.props.data.paymentlines,
            partner: partner,
            // ✅ Helper functions dikirim sebagai props
            formatDate: (val) => self.formatReceiptDate(val),
            fmtCurrency: (amount) => self.fmtCurrency(amount),
            stripRp: (val) => self.stripRp(val),
        };
    },

    get templateComponent() {
        const mainRef = this;
        return class extends Component {
            setup() {}
            static template = xml`${mainRef.pos.config.design_receipt}`;
        };
    },

    get isTrue() {
        return this.env.services.pos.config.is_custom_receipt === false;
    }
});