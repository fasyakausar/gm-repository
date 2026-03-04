/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { SaleOrderManagementControlPanel } from "@pos_sale/app/order_management_screen/sale_order_management_control_panel/sale_order_management_control_panel";
import { useService } from "@web/core/utils/hooks";
import { onMounted } from "@odoo/owl";

patch(SaleOrderManagementControlPanel.prototype, {

    setup() {
        super.setup(...arguments);
        this.orm = useService("orm");
        this._warehouseId = null;  // cache hasil fetch

        onMounted(async () => {
            await this._loadWarehouseFromPickingType();
        });
    },

    /**
     * Fetch warehouse_id dari stock.picking.type berdasarkan
     * picking_type_id yang ada di pos.config.
     *
     * Dipanggil sekali saat component mount, hasilnya di-cache.
     */
    async _loadWarehouseFromPickingType() {
        try {
            const config = this.pos.config;

            // Unpack picking_type_id dari Proxy(Array) → ambil ID numeriknya
            const ptRaw = config.picking_type_id;
            const pickingTypeId = Array.isArray(ptRaw)
                ? ptRaw[0]
                : (ptRaw?.id || null);

            if (!pickingTypeId) {
                console.warn("[WarehouseFilter] picking_type_id tidak ditemukan di pos.config");
                return;
            }

            // Query stock.picking.type untuk ambil warehouse_id
            const result = await this.orm.read(
                "stock.picking.type",
                [pickingTypeId],
                ["warehouse_id"]
            );

            if (result && result.length > 0 && result[0].warehouse_id) {
                const wh = result[0].warehouse_id;
                // warehouse_id dari ORM read = [id, name]
                this._warehouseId = Array.isArray(wh) ? wh[0] : wh;

                console.log(
                    "%c[WarehouseFilter] ✅ Warehouse loaded",
                    "color: #4CAF50; font-weight: bold;",
                    `POS: "${config.name}"`,
                    `| picking_type_id: ${pickingTypeId}`,
                    `| warehouse_id: ${this._warehouseId}`,
                    `| warehouse_name: ${Array.isArray(wh) ? wh[1] : ""}`,
                );
            } else {
                console.warn("[WarehouseFilter] warehouse_id tidak ditemukan untuk picking_type_id:", pickingTypeId);
            }
        } catch (e) {
            console.error("[WarehouseFilter] Error fetching warehouse:", e);
        }
    },

    _computeDomain() {
        const domain = super._computeDomain(...arguments);

        if (this._warehouseId) {
            domain.unshift(["warehouse_id", "=", this._warehouseId]);
        }

        return domain;
    },
});