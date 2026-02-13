/** @odoo-module */

import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";
import { TextInputPopup } from "@point_of_sale/app/utils/input_popups/text_input_popup";
import { ConfirmPopup } from "@point_of_sale/app/utils/confirm_popup/confirm_popup";
import { onMounted, onWillUnmount } from "@odoo/owl";

patch(TicketScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this._refreshInterval = null;
        onMounted(() => this._startAutoRefresh());
        onWillUnmount(() => this._stopAutoRefresh());
    },

    _startAutoRefresh() {
        this._stopAutoRefresh();
        this._refreshInterval = setInterval(() => {
            const order = this.getSelectedOrder();
            if (order && order.backendId && order.locked) {
                this._forceRefreshOrder(order);
            }
        }, 3000);
        console.log("Auto-refresh started (every 3 seconds)");
    },

    _stopAutoRefresh() {
        if (this._refreshInterval) {
            clearInterval(this._refreshInterval);
            this._refreshInterval = null;
            console.log("Auto-refresh stopped");
        }
    },

    async _forceRefreshOrder(order) {
        if (!order || !order.backendId) return;
        try {
            const refundedQtys = await this.orm.call(
                'return.approval',
                'get_refunded_quantities',
                [order.backendId]
            );
            for (const line of order.get_orderlines()) {
                const productId = line.product.id;
                const newRefundedQty = refundedQtys[productId] || 0;
                if (line.refunded_qty !== newRefundedQty) {
                    console.log(`Updated ${line.product.display_name}: ${line.refunded_qty} -> ${newRefundedQty}`);
                    line.refunded_qty = newRefundedQty;
                }
            }
            if (this._state.syncedOrders?.cache?.[order.backendId]) {
                const cachedOrder = this._state.syncedOrders.cache[order.backendId];
                for (const line of cachedOrder.get_orderlines()) {
                    const productId = line.product.id;
                    line.refunded_qty = refundedQtys[productId] || 0;
                }
            }
            this.render();
        } catch (error) {
            console.error("Error refreshing order:", error);
        }
    },

    async onClickOrder(clickedOrder) {
        await super.onClickOrder(clickedOrder);
        if (clickedOrder?.backendId) {
            await this._forceRefreshOrder(clickedOrder);
        }
    },

    async _fetchSyncedOrders() {
        await super._fetchSyncedOrders(...arguments);
        const order = this.getSelectedOrder();
        if (order?.backendId) {
            await this._forceRefreshOrder(order);
        }
    },

    async onDoRefund() {
        const order = this.getSelectedOrder();

        // Jika tidak ada order, highlight header
        if (!order) {
            this._state.ui.highlightHeaderNote = !this._state.ui.highlightHeaderNote;
            return;
        }

        // Hanya paid order yang bisa diretur
        if (!order.locked) {
            await this.popup.add(ErrorPopup, {
                title: _t("Cannot Create Return Approval"),
                body: _t("Only paid orders can be returned. Please complete the payment first."),
            });
            return;
        }

        // Refresh data sebelum melanjutkan
        await this._forceRefreshOrder(order);

        // Ambil daftar item yang tersedia untuk diretur dari backend
        let availableItems;
        try {
            availableItems = await this.orm.call(
                'return.approval',
                'get_available_return_items',
                [order.backendId]
            );

            if (!availableItems || availableItems.length === 0) {
                await this.popup.add(ErrorPopup, {
                    title: _t("No Items Available for Return"),
                    body: _t("All items in this order have already been submitted for return or fully refunded."),
                });
                return;
            }
        } catch (error) {
            console.error("Error checking available items:", error);
            await this.popup.add(ErrorPopup, {
                title: _t("Error"),
                body: _t("Failed to check available items: %s", error.message || "Unknown error"),
            });
            return;
        }

        const partner = order.get_partner();
        const allToRefundDetails = this._getRefundableDetails(partner);

        if (allToRefundDetails.length === 0) {
            this._state.ui.highlightHeaderNote = !this._state.ui.highlightHeaderNote;
            await this.popup.add(ErrorPopup, {
                title: _t("No Items Selected"),
                body: _t("Please select items to return by clicking on them and setting the quantity."),
            });
            return;
        }

        // --- PENAMBAHAN DARI PATCH KEDUA: cek multiple invoiced orders ---
        const invoicedOrderIds = new Set(
            allToRefundDetails
                .filter(
                    (detail) =>
                        this._state.syncedOrders.cache[detail.orderline.orderBackendId]?.state === "invoiced"
                )
                .map((detail) => detail.orderline.orderBackendId)
        );

        if (invoicedOrderIds.size > 1) {
            await this.popup.add(ErrorPopup, {
                title: _t("Multiple Invoiced Orders Selected"),
                body: _t(
                    "You have selected orderlines from multiple invoiced orders. To proceed with return approval, please select orderlines from the same invoiced order."
                ),
            });
            return;
        }
        // --- akhir penambahan ---

        // Validasi quantity yang diminta tidak melebihi available
        const availableMap = {};
        availableItems.forEach(item => {
            availableMap[item.product_id] = item.remaining_qty;
        });

        for (const detail of allToRefundDetails) {
            const productId = detail.orderline.productId;
            const requestedQty = Math.abs(detail.qty);
            const availableQty = availableMap[productId] || 0;

            if (requestedQty > availableQty) {
                const product = this.pos.db.get_product_by_id(productId);
                await this.popup.add(ErrorPopup, {
                    title: _t("Quantity Exceeds Available"),
                    body: _t(
                        "Product: %s\nRequested: %s\nAvailable for return: %s\n\n" +
                        "Some items may already be in return process or fully refunded.",
                        product.display_name,
                        requestedQty,
                        availableQty
                    ),
                });
                return;
            }
        }

        // Minta alasan return
        const { confirmed, payload: returnReason } = await this.popup.add(TextInputPopup, {
            title: _t("Return Reason"),
            placeholder: _t("Please provide a reason for this return..."),
            rows: 4,
        });

        if (!confirmed || !returnReason?.trim()) {
            await this.popup.add(ErrorPopup, {
                title: _t("Return Reason Required"),
                body: _t("You must provide a reason for the return."),
            });
            return;
        }

        // Siapkan data untuk dikirim ke backend
        const lineData = allToRefundDetails.map(detail => [
            0, 0, {
                gm_product_id: detail.orderline.productId,
                gm_qty: Math.abs(detail.qty),
            }
        ]);

        const returnApprovalData = {
            gm_pos_order_id: order.backendId,
            gm_return_reason: returnReason.trim(),
            gm_line_ids: lineData,
        };

        console.log("Creating return approval with data:", returnApprovalData);

        try {
            const returnApprovalId = await this.orm.call(
                'return.approval',
                'create',
                [returnApprovalData]
            );

            console.log("Return approval created with ID:", returnApprovalId);

            await this.popup.add(ErrorPopup, {
                title: _t("Success"),
                body: _t("Return approval document has been created successfully. Items are now marked as 'Refunded' pending approval."),
            });

            // Hapus seleksi item yang sudah diproses
            for (const detail of allToRefundDetails) {
                if (this.pos.toRefundLines[detail.orderline.id]) {
                    delete this.pos.toRefundLines[detail.orderline.id];
                }
            }

            // Refresh order segera
            await this._forceRefreshOrder(order);

            if (this._state.ui.filter === "SYNCED") {
                await this._fetchSyncedOrders();
            }

        } catch (error) {
            console.error("Error creating return approval:", error);
            let errorMessage = error?.data?.message || error?.message || "Unknown error";
            await this.popup.add(ErrorPopup, {
                title: _t("Error"),
                body: _t("Failed to create return approval: %s", errorMessage),
            });
        }
    },
});