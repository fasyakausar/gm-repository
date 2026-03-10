/** @odoo-module **/
import { ListController } from "@web/views/list/list_controller";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";

patch(ListController.prototype, {
    setup() {
        super.setup();
        this.actionService = useService("action");
        this.rpc = useService("rpc");
    },

    async createRecord() {
        // Hanya intercept untuk model sale.order
        if (this.props.resModel !== "sale.order") {
            return super.createRecord(...arguments);
        }

        try {
            const allowedIds = await this.rpc(
                "/web/dataset/call_kw",
                {
                    model: "sale.order",
                    method: "get_allowed_warehouse_ids_for_current_user",
                    args: [],
                    kwargs: {},
                }
            );

            if (allowedIds.length <= 1) {
                // 0 atau 1 warehouse → langsung buat SO seperti biasa
                return super.createRecord(...arguments);
            }

            // >1 warehouse → buka wizard
            await this.actionService.doAction({
                type: "ir.actions.act_window",
                name: "Pilih Warehouse",
                res_model: "sale.warehouse.wizard",
                view_mode: "form",
                views: [[false, "form"]],
                target: "new",
                context: this.props.context || {},
            });

        } catch (e) {
            // Fallback jika RPC error
            return super.createRecord(...arguments);
        }
    },
});