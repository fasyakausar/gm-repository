/** @odoo-module */
import { Component } from "@odoo/owl";
import { PaymentScreenStatus } from "@point_of_sale/app/screens/payment_screen/payment_status/payment_status";
import { patch } from "@web/core/utils/patch";

patch(PaymentScreenStatus.prototype, {
    setup() {
        super.setup(...arguments);
        
        // Inisialisasi tracking untuk jumlah payment lines
        this.lastPaymentCount = 0;
        
        // Set remaining awal
        this.updateFixedRemaining();
    },
    
    /**
     * Update fixed remaining berdasarkan jumlah payment yang sudah ada
     * Hanya dipanggil saat jumlah payment lines berubah
     */
    updateFixedRemaining() {
        const order = this.props.order;
        const totalDue = order.get_total_with_tax();
        const paidAmount = order.get_total_paid();
        
        // Hitung remaining = Total Due - Total Paid
        const remaining = totalDue - paidAmount;
        
        this.fixedRemaining = remaining > 0 ? remaining : 0;
        
        console.log('💰 [REMAINING] Updated:');
        console.log(`   Total Due: ${totalDue}`);
        console.log(`   Total Paid: ${paidAmount}`);
        console.log(`   Remaining: ${this.fixedRemaining}`);
    },
    
    get remainingText() {
        // Cek apakah jumlah payment lines berubah
        const currentPaymentCount = this.props.order.paymentlines.length;
        
        // Jika ada payment baru ditambahkan, update remaining
        if (currentPaymentCount !== this.lastPaymentCount) {
            console.log(`🔄 [REMAINING] Payment count changed: ${this.lastPaymentCount} → ${currentPaymentCount}`);
            this.lastPaymentCount = currentPaymentCount;
            this.updateFixedRemaining();
        }
        
        // Return nilai fixed remaining (tidak berubah saat user input)
        return this.env.utils.formatCurrency(this.fixedRemaining);
    }
});

console.log("✅ [REMAINING] Fixed remaining payment loaded - updates only on new payment");