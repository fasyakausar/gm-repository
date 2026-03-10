/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ListController } from "@web/views/list/list_controller";
import { useService } from "@web/core/utils/hooks";

/**
 * Patch ListController khusus untuk model sale.order.
 * Ketika user klik tombol New:
 *   - Cek allowed_warehouse_ids milik user via RPC
 *   - 0 restriction  → buka form SO biasa
 *   - 1 warehouse    → buka form SO dengan default_warehouse_id
 *   - >1 warehouse   → buka wizard sale.warehouse.wizard dulu
 */
patch(ListController.prototype, {
    setup() {
        super.setup(...arguments);
        this.action = useService("action");
        this.orm = useService("orm");
        this.user = useService("user");
    },

    async createRecord() {
        // Hanya intercept jika ini adalah list view sale.order
        if (this.props.resModel !== "sale.order") {
            return super.createRecord(...arguments);
        }

        // Ambil allowed_warehouse_ids via call ke Python method
        // agar filter company dan sudo() ditangani di server side
        const allowedIds = await this.orm.call(
            "sale.order",
            "get_allowed_warehouse_ids_for_current_user",
            [],
            {}
        );

        // 0 restriction → default behaviour
        if (allowedIds.length === 0) {
            return super.createRecord(...arguments);
        }

        // 1 warehouse → langsung buka form dengan warehouse tersebut
        if (allowedIds.length === 1) {
            return this.action.doAction({
                type: "ir.actions.act_window",
                res_model: "sale.order",
                view_mode: "form",
                views: [[false, "form"]],
                target: "current",
                context: {
                    default_warehouse_id: allowedIds[0],
                },
            });
        }

        // >1 warehouse → buka wizard pilih warehouse
        return this.action.doAction({
            name: "Pilih Warehouse",
            type: "ir.actions.act_window",
            res_model: "sale.warehouse.wizard",
            view_mode: "form",
            views: [[false, "form"]],
            target: "new",
        });
    },
});