/** @odoo-module */

import { PosStore } from "@point_of_sale/app/store/pos_store";
import { patch } from "@web/core/utils/patch";

patch(PosStore.prototype, {
    async _processData(loadedData) {
        await super._processData(...arguments);
        
        // Load config settings untuk rounding
        if (loadedData['res.config.settings']) {
            this.config_settings = loadedData['res.config.settings'][0] || {};
        } else {
            // Fallback: load dari server jika tidak ada di loadedData
            try {
                const settings = await this.orm.call(
                    'res.config.settings',
                    'get_config_settings',
                    []
                );
                this.config_settings = settings;
            } catch (error) {
                console.error('Failed to load config settings:', error);
                this.config_settings = {};
            }
        }
    },
});