// /** @odoo-module */

// import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
// import { patch } from "@web/core/utils/patch";

// // Patch untuk ProductScreen - Format currency tanpa desimal
// patch(ProductScreen.prototype, {
    
//     /**
//      * Helper method untuk format currency tanpa desimal jika nilainya bulat
//      */
//     _formatCurrencyWithoutDecimals(amount) {
//         if (!amount && amount !== 0) return "0";
        
//         // Konversi ke number
//         const numAmount = typeof amount === 'string' ? parseFloat(amount) : amount;
        
//         // Jika amount adalah bilangan bulat, tampilkan tanpa desimal
//         if (numAmount % 1 === 0) {
//             return this.env.utils.formatCurrency(numAmount).replace(/[.,]00$/, '');
//         }
//         // Jika ada desimal, tampilkan normal
//         return this.env.utils.formatCurrency(numAmount);
//     },

//     /**
//      * Override getter total untuk format tanpa desimal jika bilangan bulat
//      */
//     get total() {
//         const totalAmount = this.currentOrder?.get_total_with_tax() ?? 0;
//         return this._formatCurrencyWithoutDecimals(totalAmount);
//     },

//     /**
//      * Override getter selectedOrderlineTotal untuk format tanpa desimal jika bilangan bulat
//      */
//     get selectedOrderlineTotal() {
//         const lineTotal = this.currentOrder.get_selected_orderline()?.get_display_price() ?? 0;
//         return this._formatCurrencyWithoutDecimals(lineTotal);
//     },

//     /**
//      * Getter untuk unit price yang ditampilkan di UI
//      */
//     get selectedOrderlineUnitPrice() {
//         const selectedLine = this.currentOrder.get_selected_orderline();
//         if (!selectedLine || !selectedLine.product) return "0";
        
//         // Gunakan list_price (harga asli)
//         const listPrice = selectedLine.product.list_price || selectedLine.product.lst_price;
//         return this._formatCurrencyWithoutDecimals(listPrice || selectedLine.price);
//     }
// });