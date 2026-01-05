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
        
        // Initialize refresh interval
        this._refreshInterval = null;
        
        onMounted(() => {
            this._startAutoRefresh();
        });
        
        onWillUnmount(() => {
            this._stopAutoRefresh();
        });
    },
    
    _startAutoRefresh() {
        // Clear any existing interval
        this._stopAutoRefresh();
        
        // Auto refresh every 3 seconds
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
    
    async onDoRefund() {
        const order = this.getSelectedOrder();

        if (!order) {
            this._state.ui.highlightHeaderNote = !this._state.ui.highlightHeaderNote;
            return;
        }

        if (!order.locked) {
            await this.popup.add(ErrorPopup, {
                title: _t("Cannot Create Return Approval"),
                body: _t("Only paid orders can be returned. Please complete the payment first."),
            });
            return;
        }

        // Force refresh before checking
        await this._forceRefreshOrder(order);

        // Get available items
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

        // Validate quantities
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

        const { confirmed, payload: returnReason } = await this.popup.add(TextInputPopup, {
            title: _t("Return Reason"),
            placeholder: _t("Please provide a reason for this return..."),
            rows: 4,
        });

        if (!confirmed || !returnReason || !returnReason.trim()) {
            await this.popup.add(ErrorPopup, {
                title: _t("Return Reason Required"),
                body: _t("You must provide a reason for the return."),
            });
            return;
        }

        const lineData = allToRefundDetails.map(detail => {
            return [0, 0, {
                gm_product_id: detail.orderline.productId,
                gm_qty: Math.abs(detail.qty),
            }];
        });

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

            // Clear selections
            for (const detail of allToRefundDetails) {
                if (this.pos.toRefundLines[detail.orderline.id]) {
                    delete this.pos.toRefundLines[detail.orderline.id];
                }
            }

            // Force immediate refresh
            await this._forceRefreshOrder(order);

            if (this._state.ui.filter === "SYNCED") {
                await this._fetchSyncedOrders();
            }

        } catch (error) {
            console.error("Error creating return approval:", error);
            
            let errorMessage = "Unknown error";
            if (error.data && error.data.message) {
                errorMessage = error.data.message;
            } else if (error.message) {
                errorMessage = error.message;
            }
            
            await this.popup.add(ErrorPopup, {
                title: _t("Error"),
                body: _t("Failed to create return approval: %s", errorMessage),
            });
        }
    },

    async _forceRefreshOrder(order) {
        if (!order || !order.backendId) {
            return;
        }

        try {
            // Get fresh refunded quantities
            const refundedQtys = await this.orm.call(
                'return.approval',
                'get_refunded_quantities',
                [order.backendId]
            );

            // Update all order lines
            for (const line of order.get_orderlines()) {
                const productId = line.product.id;
                const newRefundedQty = refundedQtys[productId] || 0;
                
                // Only log if changed
                if (line.refunded_qty !== newRefundedQty) {
                    console.log(`Updated ${line.product.display_name}: ${line.refunded_qty} -> ${newRefundedQty}`);
                    line.refunded_qty = newRefundedQty;
                }
            }

            // Update cache if exists
            if (this._state.syncedOrders && this._state.syncedOrders.cache) {
                const cachedOrder = this._state.syncedOrders.cache[order.backendId];
                if (cachedOrder) {
                    for (const line of cachedOrder.get_orderlines()) {
                        const productId = line.product.id;
                        line.refunded_qty = refundedQtys[productId] || 0;
                    }
                }
            }

            // Force UI re-render
            this.render();
            
        } catch (error) {
            console.error("Error refreshing order:", error);
        }
    },

    async onClickOrder(clickedOrder) {
        await super.onClickOrder(clickedOrder);
        
        // Immediate refresh when clicking order
        if (clickedOrder && clickedOrder.backendId) {
            await this._forceRefreshOrder(clickedOrder);
        }
    },

    async _fetchSyncedOrders() {
        await super._fetchSyncedOrders(...arguments);
        
        // Refresh current order after fetching
        const order = this.getSelectedOrder();
        if (order && order.backendId) {
            await this._forceRefreshOrder(order);
        }
    },

});