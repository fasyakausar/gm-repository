/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";

patch(PosStore.prototype, {
    async _processData(loadedData) {
        await super._processData(...arguments);

        // ✅ Load hr.employee untuk salesperson mapping
        this.hr_employee = loadedData['hr_employee'] || [];

        // ✅ Load custom receipt address dari pos.config
        // Disimpan di this.receipt_address agar mudah diakses di template
        this.receipt_address = loadedData['pos_receipt_address'] || {};

        console.log("✅ [HR_EMPLOYEE] Loaded:", this.hr_employee.length);
        console.log("✅ [RECEIPT ADDRESS] Loaded:", this.receipt_address);
    },
});