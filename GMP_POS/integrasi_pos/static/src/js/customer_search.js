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

        const currentCompanyId = this.pos.company?.id;

        // Build domain dengan company filter
        const domain = [
            ['active', '=', true],
            ['gm_bp_type', '=', 'customer'],
            '|',
            ['name', 'ilike', this.state.query],
            ['barcode', '=', this.state.query],
        ];

        // Filter hanya company saat ini + global (company_id=False)
        if (currentCompanyId) {
            domain.push('|');
            domain.push(['company_id', '=', currentCompanyId]);
            domain.push(['company_id', '=', false]);
        }

        const result = await this.pos.orm.call(
            'res.partner',
            'search_read',
            [],
            {
                domain,
                fields: [
                    'name', 'street', 'city', 'state_id', 'country_id',
                    'vat', 'lang', 'phone', 'zip', 'mobile', 'email',
                    'barcode', 'write_date', 'property_account_position_id',
                    'property_product_pricelist', 'parent_name', 'category_id',
                    'vit_customer_group', 'gm_bp_type', 'company_id',
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

        // ── Dedup: prioritaskan company-specific atas global ──
        const byName = new Map();
        const byId = new Map();

        for (const partner of result) {
            const cid = Array.isArray(partner.company_id)
                ? partner.company_id[0]
                : partner.company_id;
            const nameKey = (partner.name || '').trim().toLowerCase();
            const isCompanySpecific = cid && cid === currentCompanyId;

            // Dedup by id
            if (byId.has(partner.id)) continue;
            byId.set(partner.id, partner);

            // Dedup by name: simpan company-specific, skip global jika nama sudah ada
            if (isCompanySpecific) {
                byName.set(nameKey, partner);
            } else if (!byName.has(nameKey)) {
                byName.set(nameKey, partner);
            }
        }

        // Hasil akhir = semua partner yang menang di byName
        const deduped = Array.from(byName.values());

        // Add ke db jika belum ada
        for (const partner of deduped) {
            if (!this.pos.db.partner_by_id[partner.id]) {
                this.pos.db.add_partners([partner]);
            }
        }

        this.state.partners = deduped;
    },
});