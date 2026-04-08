/** @odoo-module */
import { SelectionPopup } from "@point_of_sale/app/utils/input_popups/selection_popup";
import { patch } from "@web/core/utils/patch";
import { useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { _t } from "@web/core/l10n/translation";
import { PopUpSuccesError } from "./pop_up_error";
import { PosStore } from "@point_of_sale/app/store/pos_store";

// Patch pertama: reset cashier (tidak mempengaruhi pricelist)
patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);
        if (this.config && this.config.module_pos_hr) {
            const cashierKey = `connected_cashier_${this.config.id}`;
            sessionStorage.removeItem(cashierKey);
            if (typeof this.reset_cashier === 'function') {
                this.reset_cashier();
            }
            this.hasLoggedIn = false;
            if (typeof this.showTempScreen === 'function') {
                this.showTempScreen("LoginScreen");
            }
        }
    },
});

// Patch kedua: SelectionPopup untuk fitur pencarian dan validasi cashier
const originalSetup = SelectionPopup.prototype.setup;
const originalSelectItem = SelectionPopup.prototype.selectItem;

patch(SelectionPopup.prototype, {
    setup() {
        originalSetup.call(this);
        this.rpc = useService("rpc");
        this.orm = useService("orm");
        this.pos = usePos();
        this.popup = useService("popup");

        // Search state hanya untuk popup cashier
        if (this.props.title && (this.props.title.includes("Cashier") || this.props.title.includes("cashier"))) {
            this.searchState = useState({
                searchQuery: "",
            });
        }
    },

    // ✅ PERBAIKAN UTAMA: filteredList hanya memfilter employee jika popup untuk Cashier
    get filteredList() {
        let list = this.props.list;

        // Hanya terapkan filter employee jika ini adalah popup pemilihan kasir
        if (this.props.title && (this.props.title.includes("Cashier") || this.props.title.includes("cashier"))) {
            const basicIds = this.pos.config?.basic_employee_ids || [];
            const advancedIds = this.pos.config?.advanced_employee_ids || [];
            const allowedIds = [...new Set([...basicIds, ...advancedIds])];

            if (allowedIds.length > 0) {
                list = list.filter(item => {
                    const employeeId = item.item?.id;
                    return allowedIds.includes(employeeId);
                });
            }
        }

        // Filter berdasarkan search query (hanya jika searchState ada)
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
        return this.props.title && (this.props.title.includes("Cashier") || this.props.title.includes("cashier"));
    },

    async selectItem(itemId) {
        const selectedItem = this.props.list.find((item) => item.id === itemId);

        console.log("🔍 SelectedItem:", selectedItem);
        console.log("🔍 SelectedItem.item:", selectedItem?.item);
        console.log("🔍 SelectedItem.item.id:", selectedItem?.item?.id);

        const isProbablyEmployee =
            selectedItem?.item?.hasOwnProperty("work_contact_id") &&
            selectedItem?.item?.hasOwnProperty("role") &&
            selectedItem?.item?.hasOwnProperty("pin");

        if (selectedItem && selectedItem.item && selectedItem.item.id && isProbablyEmployee) {
            try {
                const employeeData = await this.orm.searchRead(
                    "hr.employee",
                    [["id", "=", selectedItem.item.id]],
                    ["is_cashier", "is_sales_person", "is_pic"]
                );

                if (!employeeData.length) {
                    await this.showErrorPopup(
                        _t("Error: Data Tidak Ditemukan"),
                        _t("Karyawan yang dipilih tidak valid.")
                    );
                    return;
                }

                const { is_cashier, is_pic } = employeeData[0];

                if (!is_cashier && !is_pic) {
                    await this.showErrorPopup(
                        _t("Error: Bukan Kasir atau Salesperson"),
                        _t("Karyawan yang dipilih bukan kasir maupun salesperson. Silakan pilih yang valid.")
                    );
                    return;
                }

                const sessionId = this.pos.pos_session ? this.pos.pos_session.id : null;
                if (!sessionId) {
                    await this.showErrorPopup(
                        _t("Error: Sesi POS"),
                        _t("Sesi POS tidak tersedia. Silakan buka sesi terlebih dahulu.")
                    );
                    return;
                }

                if (is_cashier) {
                    const response = await this.rpc("/pos/log_cashier", {
                        employee_id: selectedItem.item.id,
                        session_id: sessionId,
                    });

                    if (response.success) {
                        console.log("✅ Cashier login successful:", response);
                        return await originalSelectItem.call(this, itemId);
                    } else {
                        const errorMessages = {
                            cashier_shift_closed: _t("Tidak dapat login. Shift untuk kasir ini sudah ditutup pada sesi ini."),
                            cashier_already_logged_in: _t("Kasir ini sudah login di sesi lain. Silakan logout terlebih dahulu."),
                            payment_disabled: _t("Kasir ini tidak memiliki akses untuk melakukan pembayaran."),
                            another_cashier_active: _t("Tidak dapat login. Kasir lain sudah aktif di sesi ini."),
                        };
                        const errorMessage = errorMessages[response.error] || _t("Gagal memilih kasir.");
                        await this.showErrorPopup(_t("Error"), errorMessage);
                        return;
                    }
                }

                return await originalSelectItem.call(this, itemId);

            } catch (error) {
                console.error("❌ Error selecting item:", error);
                let errorMessage = _t("Terjadi kesalahan saat memilih karyawan.");
                if (error.message) errorMessage += _t(`\nDetail: ${error.message}`);
                if (error.data && error.data.message) errorMessage += _t(`\nServer: ${error.data.message}`);

                await this.showErrorPopup(_t("Error: Sistem"), errorMessage);
                return;
            }
        }

        return await originalSelectItem.call(this, itemId);
    },

    async showErrorPopup(title, message) {
        const { confirmed } = await this.popup.add(PopUpSuccesError, {
            title: title || _t("Error"),
            body: message,
            confirmText: _t("OK"),
        });
        return confirmed ? true : false;
    }
});