/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PartnerListScreen } from "@point_of_sale/app/screens/partner_list/partner_list";

patch(PartnerListScreen.prototype, {

    /**
     * Override _onPressEnterKey untuk filter gm_bp_type = customer
     * saat "Search more" diklik
     */
    async _onPressEnterKey() {
        if (!this.state.query) return;

        const result = await this.pos.orm.call(
            'res.partner',
            'search_read',
            [],
            {
                domain: [
                    ['active', '=', true],
                    ['gm_bp_type', '=', 'customer'],
                    '|',
                    ['name', 'ilike', this.state.query],
                    ['barcode', '=', this.state.query],
                ],
                fields: [
                    'name', 'street', 'city', 'state_id', 'country_id',
                    'vat', 'lang', 'phone', 'zip', 'mobile', 'email',
                    'barcode', 'write_date', 'property_account_position_id',
                    'property_product_pricelist', 'parent_name', 'category_id',
                    'vit_customer_group', 'gm_bp_type',
                ],
                limit: 100,
            }
        );

        if (result.length === 0) {
            this.pos.env.services.notification.add(
                `No customer found for "${this.state.query}"`,
                { type: 'warning' }
            );
            return;
        }

        // Tambahkan partner yang belum ada ke db
        for (const partner of result) {
            if (!this.pos.db.partner_by_id[partner.id]) {
                this.pos.db.add_partners([partner]);
            }
        }

        // Update list dengan hasil search
        this.state.partners = result;
    },
});