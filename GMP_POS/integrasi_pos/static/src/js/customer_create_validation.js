/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";
import { PartnerDetailsEdit } from "@point_of_sale/app/screens/partner_list/partner_editor/partner_editor";
import { PartnerListScreen } from "@point_of_sale/app/screens/partner_list/partner_list";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { useService } from "@web/core/utils/hooks";
import { onWillStart, useState } from "@odoo/owl";

// =====================================================
// PATCH PosStore - Load customer groups saat POS init
// =====================================================
patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);

        // ✅ Inisialisasi DULU dengan array kosong agar getter tidak pernah undefined
        this.customerGroups = [];

        try {
            const groups = await this.orm.searchRead(
                "customer.group",
                [],
                ["id", "vit_group_name", "vit_pricelist_id"],
                { order: "vit_group_name ASC" }
            );
            this.customerGroups = groups || [];
            console.log("✅ [POS STORE] Customer Groups loaded:", this.customerGroups.length);
        } catch (error) {
            console.error("❌ [POS STORE] Error loading customer groups:", error);
            this.customerGroups = [];
        }
    },
});

// =====================================================
// PATCH PartnerDetailsEdit
// =====================================================
patch(PartnerDetailsEdit.prototype, {
    setup() {
        super.setup(...arguments);
        this.orm = useService("orm");

        if (!this.intFields.includes('vit_customer_group')) {
            this.intFields.push('vit_customer_group');
        }

        const partner = this.props.partner;
        this.changes.vit_customer_group = partner.vit_customer_group
            ? partner.vit_customer_group[0]
            : false;

        // ✅ Set gm_bp_type otomatis
        this.changes.gm_bp_type = partner.id
            ? (partner.gm_bp_type || 'customer')
            : 'customer';

        this.changes = useState(this.changes);

        // ✅ FIX UTAMA: Gunakan useState untuk _customerGroups agar reaktif
        // Inisialisasi langsung dari pos.customerGroups (sudah di-init sebagai [] di PosStore)
        this._customerGroups = useState({
            list: Array.isArray(this.pos.customerGroups) ? [...this.pos.customerGroups] : []
        });

        // ✅ Gunakan onWillStart sebagai safety net jika PosStore belum selesai load
        onWillStart(async () => {
            // Jika data sudah ada dari PosStore, gunakan langsung
            if (this.pos.customerGroups && this.pos.customerGroups.length > 0) {
                this._customerGroups.list = [...this.pos.customerGroups];
                return;
            }

            // Fallback: load sendiri jika PosStore belum ready
            try {
                const groups = await this.orm.searchRead(
                    "customer.group",
                    [],
                    ["id", "vit_group_name", "vit_pricelist_id"],
                    { order: "vit_group_name ASC" }
                );
                const result = groups || [];
                this._customerGroups.list = result;
                // Simpan ke PosStore juga agar konsisten
                this.pos.customerGroups = result;
                console.log("✅ [EDITOR] Customer Groups loaded (fallback):", result.length);
            } catch (error) {
                console.error("❌ [EDITOR] Error loading customer groups:", error);
                this._customerGroups.list = [];
            }
        });
    },

    // ✅ Getter: SELALU kembalikan array, tidak pernah undefined/null
    get customerGroups() {
        // Prioritas: _customerGroups (reactive state) → pos.customerGroups → []
        if (this._customerGroups && Array.isArray(this._customerGroups.list)) {
            return this._customerGroups.list;
        }
        if (this.pos && Array.isArray(this.pos.customerGroups)) {
            return this.pos.customerGroups;
        }
        return [];
    },

    async onCustomerGroupChange(ev) {
        const customerGroupId = parseInt(ev.target.value) || false;
        this.changes.vit_customer_group = customerGroupId;

        if (customerGroupId) {
            const selectedGroup = this.customerGroups.find(g => g.id === customerGroupId);
            if (selectedGroup?.vit_pricelist_id) {
                this.changes.property_product_pricelist = selectedGroup.vit_pricelist_id[0];
                console.log("✅ Pricelist auto-set:", selectedGroup.vit_pricelist_id);
            }
        } else {
            const partner = this.props.partner;
            this.changes.property_product_pricelist = partner.property_product_pricelist
                ? partner.property_product_pricelist[0]
                : this.pos.config.pricelist_id?.[0];
        }
    },

    async saveChanges() {
        const processedChanges = {};
        for (const [key, value] of Object.entries(this.changes)) {
            if (this.intFields.includes(key)) {
                processedChanges[key] = parseInt(value) || false;
            } else {
                processedChanges[key] = value;
            }
        }

        // ✅ Pastikan gm_bp_type selalu terisi
        if (!processedChanges.gm_bp_type) {
            processedChanges.gm_bp_type = 'customer';
        }

        // Validasi phone
        const phoneValue = processedChanges.phone;
        if (!phoneValue || (typeof phoneValue === 'string' && phoneValue.trim() === "")) {
            return this.popup.add(ErrorPopup, {
                title: _t("Phone Number Is Required"),
                body: _t("Please enter a phone number before saving the customer."),
            });
        }

        // Auto-fill pricelist dari customer group
        if (processedChanges.vit_customer_group) {
            const selectedGroup = this.customerGroups.find(
                g => g.id === processedChanges.vit_customer_group
            );
            if (selectedGroup?.vit_pricelist_id) {
                processedChanges.property_product_pricelist = selectedGroup.vit_pricelist_id[0];
            }
        }

        // Set company_id
        if (this.pos.company?.id) {
            processedChanges.company_id = this.pos.company.id;
        }

        // Validasi state vs country
        if (
            processedChanges.state_id &&
            this.pos.states.find(
                s => s.id === processedChanges.state_id
            )?.country_id[0] !== processedChanges.country_id
        ) {
            processedChanges.state_id = false;
        }

        // Validasi nama
        if ((!this.props.partner.name && !processedChanges.name) || processedChanges.name === "") {
            return this.popup.add(ErrorPopup, {
                title: _t("A Customer Name Is Required"),
            });
        }

        processedChanges.id = this.props.partner.id || false;
        console.log("✅ Final processedChanges:", JSON.parse(JSON.stringify(processedChanges)));
        this.props.saveChanges(processedChanges);
    },

    isFieldCommercialAndPartnerIsChild(field) {
        if (field === 'property_product_pricelist' && this.changes.vit_customer_group) {
            return true;
        }
        return (
            this.pos.isChildPartner(this.props.partner) &&
            this.pos.partner_commercial_fields.includes(field)
        );
    }
});

// =====================================================
// PATCH PartnerListScreen
// =====================================================
patch(PartnerListScreen.prototype, {
    createPartner() {
        super.createPartner(...arguments);
        if (this.state.editModeProps.partner) {
            this.state.editModeProps.partner = {
                ...this.state.editModeProps.partner,
                gm_bp_type: 'customer',
            };
            console.log("✅ [GM BP TYPE] createPartner: gm_bp_type = 'customer'");
        }
    },
});