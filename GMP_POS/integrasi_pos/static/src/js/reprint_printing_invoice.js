/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ReprintReceiptScreen } from "@point_of_sale/app/screens/receipt_screen/reprint_receipt_screen";
import { useService } from "@web/core/utils/hooks";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";
import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";

// ========== HELPER FUNCTIONS ==========

/**
 * Function to remove circular references and reduce payload size
 */
function getCircularReplacer() {
    const seen = new WeakSet();
    return (key, value) => {
        // Skip certain large or unnecessary properties that might cause circular refs
        if (key === '_super' || 
            key === '__proto__' || 
            key === 'constructor' ||
            key === 'rules' ||
            key === 'program_id' ||
            key === 'parent' ||
            key === 'children' ||
            key === '_origin' ||
            key === 'env' ||
            key === 'model' ||
            key === '_fields' ||
            key === '_cache' ||
            key === '_context') {
            return undefined;
        }
        
        // Skip functions
        if (typeof value === 'function') {
            return undefined;
        }
        
        if (typeof value === "object" && value !== null) {
            if (seen.has(value)) {
                return '[Circular]';
            }
            seen.add(value);
        }
        return value;
    };
}

// ========== PATCH REPRINT RECEIPT SCREEN ==========

patch(ReprintReceiptScreen.prototype, {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.popup = useService("popup");
        this.notification = useService("notification");
        this._rendererService = useService("renderer");
    },

    /**
     * ✅ Get selected order from the screen with better validation
     */
    getSelectedOrder() {
        console.log("🔍 Getting selected order...");
        
        // Method 1: From props (standard Odoo way)
        if (this.props?.order) {
            console.log("📋 Order from props:", this.props.order);
            return this.props.order;
        }
        
        // Method 2: From current order
        if (this.currentOrder) {
            console.log("📋 Order from currentOrder:", this.currentOrder);
            return this.currentOrder;
        }
        
        // Method 3: From pos.selectedOrder
        if (this.pos?.selectedOrder) {
            console.log("📋 Order from pos.selectedOrder:", this.pos.selectedOrder);
            return this.pos.selectedOrder;
        }
        
        // Method 4: From pos orders (last selected)
        if (this.pos?.orders && this.pos.orders.length > 0) {
            const lastOrder = this.pos.orders[this.pos.orders.length - 1];
            console.log("📋 Order from pos.orders (last):", lastOrder);
            return lastOrder;
        }
        
        console.warn("⚠️ No order found in any location");
        return null;
    },

    /**
     * ✅ Check if order has is_printed = true
     * Try multiple methods: local data first, then backend
     */
    async checkOrderIsPrinted(order) {
        console.log("🔍 Checking is_printed status...");
        
        // Method 1: Check from local order object
        if (order.is_printed !== undefined) {
            console.log(`📋 is_printed from local object: ${order.is_printed}`);
            return order.is_printed;
        }
        
        // Method 2: Try to get from backend (with error handling)
        try {
            const orderId = order.id || order.server_id || order.backendId;
            
            if (orderId && typeof orderId === 'number' && orderId > 0) {
                console.log(`📥 Checking is_printed from backend for order ID: ${orderId}`);
                
                const orderData = await this.orm.read(
                    'pos.order',
                    [orderId],
                    ['is_printed']
                );
                
                if (orderData && orderData.length > 0) {
                    console.log(`✅ is_printed from backend: ${orderData[0].is_printed}`);
                    return orderData[0].is_printed || false;
                }
            }
        } catch (error) {
            console.warn("⚠️ Could not check is_printed from backend:", error);
        }
        
        // Method 3: Check if order has been finalized (fallback)
        if (order.finalized) {
            console.log("📋 Order is finalized, assuming it was printed");
            return true;
        }
        
        // Default: assume not printed
        console.log("📋 Defaulting to is_printed = false");
        return false;
    },

    /**
     * ✅ FIX: Fetch account_move_name dari backend untuk Invoice No
     */
    async fetchAccountMoveName(order) {
        const orderId = order.id || order.server_id || order.backendId;

        if (!orderId || typeof orderId !== 'number' || orderId <= 0) {
            console.warn("⚠️ Invalid order ID, cannot fetch account_move_name");
            return null;
        }

        try {
            console.log(`📥 Fetching account_move_name from backend for order ID: ${orderId}`);

            const orderData = await this.orm.read(
                'pos.order',
                [orderId],
                ['account_move', 'name', 'pos_reference']
            );

            if (orderData && orderData.length > 0) {
                const backendData = orderData[0];

                // account_move adalah Many2one field: [id, "INV/2026/XXXXX"]
                if (backendData.account_move) {
                    let moveName = null;

                    if (Array.isArray(backendData.account_move) && backendData.account_move.length >= 2) {
                        // Format Many2one: [id, name]
                        moveName = backendData.account_move[1];
                    } else if (typeof backendData.account_move === 'string') {
                        moveName = backendData.account_move;
                    } else if (typeof backendData.account_move === 'number') {
                        // Jika hanya ID, fetch nama invoice secara terpisah
                        try {
                            const moveData = await this.orm.read(
                                'account.move',
                                [backendData.account_move],
                                ['name']
                            );
                            if (moveData && moveData.length > 0) {
                                moveName = moveData[0].name;
                            }
                        } catch (e) {
                            console.warn("⚠️ Failed to fetch account.move name:", e.message);
                        }
                    }

                    if (moveName) {
                        console.log(`✅ account_move_name fetched: ${moveName}`);
                        return moveName;
                    }
                }

                console.warn("⚠️ account_move not found or empty for order:", orderId);
                return null;
            }
        } catch (error) {
            console.warn("⚠️ Could not fetch account_move_name from backend:", error);
        }

        return null;
    },

    /**
     * ✅ Get order data for printing (use local export_for_printing)
     *    + inject account_move_name dari backend
     */
    async getOrderDataForPrinting(order) {
        console.log("📄 Getting order data for printing...");
        
        try {
            // ✅ FIX: Selalu fetch account_move_name dari backend sebelum print
            // karena objek order lokal mungkin tidak memiliki data ini
            const accountMoveName = await this.fetchAccountMoveName(order);

            if (accountMoveName) {
                // Simpan ke objek order lokal agar export_for_printing bisa menggunakannya
                order.account_move_name = accountMoveName;
                console.log(`✅ Injected account_move_name: ${accountMoveName}`);
            } else {
                console.warn("⚠️ account_move_name tidak ditemukan, Invoice No akan N/A");
            }

            // Method 1: Use export_for_printing if available
            if (typeof order.export_for_printing === 'function') {
                console.log("✅ Using order.export_for_printing()");
                const data = order.export_for_printing();
                
                // ✅ FIX: Inject account_move_name ke data hasil export
                // karena export_for_printing() mungkin tidak menyertakannya
                if (accountMoveName) {
                    data.account_move_name = accountMoveName;
                }

                // ✅ IMPORTANT: Override is_printed to true for COPY receipt
                data.is_printed = true;
                
                return data;
            }
            
            // Method 2: Fallback - build data manually from order object
            console.log("⚠️ export_for_printing not available, building data manually");
            
            const orderData = {
                id: order.id || order.server_id,
                name: order.name,
                pos_reference: order.pos_reference,
                date_order: order.date_order || order.creation_date,
                account_move_name: accountMoveName || order.account_move_name || null, // ✅ FIX
                is_printed: true, // ✅ Set to true for COPY receipt
                amount_total: order.get_total_with_tax ? order.get_total_with_tax() : order.amount_total,
                amount_tax: order.get_total_tax ? order.get_total_tax() : order.amount_tax,
                amount_paid: order.get_total_paid ? order.get_total_paid() : order.amount_paid,
                amount_return: order.get_change ? order.get_change() : order.amount_return,
                partner_id: order.partner_id || order.partner,
                orderlines: [],
                paymentlines: []
            };
            
            // Get orderlines
            if (order.orderlines) {
                const lines = order.get_orderlines ? order.get_orderlines() : order.orderlines;
                orderData.orderlines = lines.map(line => {
                    const displayData = line.getDisplayData ? line.getDisplayData() : line;
                    return {
                        productName: displayData.productName || line.get_full_product_name?.() || line.product.display_name,
                        qty: displayData.qty || line.get_quantity?.() || line.qty,
                        price: displayData.price || line.get_display_price?.() || line.price_unit,
                        price_subtotal: displayData.price || (line.get_price_without_tax?.() || line.price_subtotal),
                        price_subtotal_incl: displayData.priceWithTax || (line.get_price_with_tax?.() || line.price_subtotal_incl),
                        discount: displayData.discount || line.get_discount?.() || line.discount,
                        full_product_name: line.get_full_product_name?.() || line.product?.display_name,
                        customerNote: displayData.customerNote || line.get_customer_note?.() || '',
                        originalUnitPrice: displayData.originalUnitPrice || displayData.price
                    };
                });
            }
            
            // Get paymentlines
            if (order.paymentlines) {
                const payments = order.get_paymentlines ? order.get_paymentlines() : order.paymentlines;
                orderData.paymentlines = payments.map(payment => ({
                    name: payment.payment_method?.name || payment.name,
                    amount: payment.amount,
                    card_number: payment.card_number
                }));
            }
            
            return orderData;
            
        } catch (error) {
            console.error("❌ Error getting order data:", error);
            throw error;
        }
    },

    /**
     * ✅ Generate HTML from order data using OrderReceipt component
     */
    async generateReceiptHTML(orderData) {
        try {
            console.log("📝 Generating receipt HTML...");
            
            // Render the OrderReceipt component to HTML
            const htmlVNode = await this._rendererService.toHtml(OrderReceipt, {
                data: orderData,
                formatCurrency: this.env.utils.formatCurrency,
            });
            
            const html = htmlVNode?.outerHTML || "";
            
            if (!html) {
                throw new Error("Failed to generate HTML - empty result");
            }
            
            console.log(`✅ HTML generated successfully (${html.length} characters)`);
            return html;
            
        } catch (error) {
            console.error("❌ Error generating HTML:", error);
            throw error;
        }
    },

    /**
     * ✅ MAIN METHOD: Print via localhost (WITH HTML GENERATION)
     */
    async printViaLocalhost() {
        try {
            console.log("🖨️ Starting localhost print...");
            
            // ✅ STEP 1: Get selected order
            const selectedOrder = this.getSelectedOrder();
            
            if (!selectedOrder) {
                await this.popup.add(ErrorPopup, {
                    title: "Tidak Ada Order Dipilih",
                    body: "Silakan pilih order dari list yang ingin di-print ulang.",
                });
                return;
            }
            
            console.log("📋 Selected order:", {
                name: selectedOrder.name,
                pos_reference: selectedOrder.pos_reference,
                finalized: selectedOrder.finalized
            });
            
            // ✅ STEP 2: Check is_printed status
            const isPrinted = await this.checkOrderIsPrinted(selectedOrder);
            
            console.log(`📋 Order is_printed status: ${isPrinted}`);
            
            if (!isPrinted) {
                await this.popup.add(ErrorPopup, {
                    title: "Order Belum Pernah Di-Print",
                    body: `Order ${selectedOrder.pos_reference || selectedOrder.name} belum pernah di-print sebelumnya.\n\nHanya order yang sudah di-print yang dapat di-reprint.`,
                });
                return;
            }
            
            console.log("✅ Order validation passed, proceeding to print...");
            
            // ✅ STEP 3: Get order data for printing
            // (termasuk fetch account_move_name dari backend)
            const orderData = await this.getOrderDataForPrinting(selectedOrder);
            
            if (!orderData) {
                throw new Error("Unable to get order data for printing");
            }

            console.log("📋 Order data account_move_name:", orderData.account_move_name);
            
            // ✅ STEP 4: Generate HTML from order data
            const html = await this.generateReceiptHTML(orderData);
            
            if (!html || typeof html !== 'string') {
                throw new Error("Failed to generate valid HTML string");
            }
            
            // ✅ STEP 5: Prepare request payload with HTML
            const requestPayload = {
                html: html
            };
            
            console.log("📤 Sending request to printer server...");
            
            // ✅ STEP 6: Send to print server
            const response = await fetch("http://localhost:3001/print", {
                method: "POST",
                headers: { 
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                },
                body: JSON.stringify(requestPayload),
            });

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`Server error: ${response.status} - ${errorText}`);
            }
            
            const result = await response.text();
            console.log("✅ Print successful:", result);
            
            // ✅ STEP 7: Show success notification
            if (this.notification) {
                this.notification.add(
                    `Receipt COPY untuk ${orderData.pos_reference || orderData.name} berhasil di-print!`, 
                    { type: "success" }
                );
            }
            
        } catch (error) {
            console.error("❌ Print error:", error);
            
            let errorMessage = "Unable to print receipt via localhost.";
            
            if (error.message.includes('circular structure')) {
                errorMessage = "Receipt data contains circular references. Please try again or contact support.";
            } else if (error.message.includes('413') || error.message.includes('PayloadTooLargeError')) {
                errorMessage = "Receipt data too large. Please try again or contact support.";
            } else if (error.message.includes('ECONNREFUSED')) {
                errorMessage = "Cannot connect to printer server. Please ensure the print server is running on localhost:3001.";
            } else if (error.message.includes('Failed to fetch')) {
                errorMessage = "Network error. Please check your connection to the printer server.";
            } else if (error.message) {
                errorMessage = error.message;
            }
            
            await this.popup.add(ErrorPopup, {
                title: "Print Error",
                body: errorMessage,
            });
        }
    },
    
    /**
     * Test printer connection
     */
    async testPrinterConnection() {
        try {
            const response = await fetch("http://localhost:3001/test", {
                method: "GET",
                headers: { "Accept": "text/plain" }
            });
            
            if (response.ok) {
                const message = await response.text();
                console.log("✅ Printer server test:", message);
                return true;
            }
            return false;
        } catch (error) {
            console.error("❌ Printer server test failed:", error);
            return false;
        }
    }
});