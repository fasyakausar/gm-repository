/** @odoo-module */
import { SelectionPopup } from "@point_of_sale/app/utils/input_popups/selection_popup";
import { patch } from "@web/core/utils/patch";
import { useState } from "@odoo/owl";

patch(SelectionPopup.prototype, {
    setup() {
        super.setup();
        // Initialize search state only for cashier selection
        if (this.props.title && (this.props.title.includes("Cashier") || this.props.title.includes("cashier"))) {
            this.searchState = useState({
                searchQuery: "",
            });
        }
    },

    get filteredList() {
        let list = this.props.list;

        // ✅ Filter berdasarkan basic_employee_ids & advanced_employee_ids dari pos.config
        const basicIds = this.pos.config?.basic_employee_ids || [];
        const advancedIds = this.pos.config?.advanced_employee_ids || [];
        const allowedIds = [...new Set([...basicIds, ...advancedIds])];

        // Jika allowedIds kosong = semua employee boleh login (sesuai tooltip Odoo)
        if (allowedIds.length > 0) {
            list = list.filter(item => {
                const employeeId = item.item?.id;
                return allowedIds.includes(employeeId);
            });
        }

        // Filter search query
        if (this.searchState?.searchQuery?.trim()) {
            const query = this.searchState.searchQuery.toLowerCase().trim();
            list = list.filter(item =>
                item.label && item.label.toLowerCase().includes(query)
            );
        }

        return list;
    },

    onSearchInput(event) {
        if (this.searchState) {
            this.searchState.searchQuery = event.target.value;
        }
    },

    clearSearch() {
        if (this.searchState) {
            this.searchState.searchQuery = "";
        }
    },

    get showSearchField() {
        // Show search field only for cashier selection popup
        return this.props.title && (this.props.title.includes("Cashier") || this.props.title.includes("cashier"));
    }
});