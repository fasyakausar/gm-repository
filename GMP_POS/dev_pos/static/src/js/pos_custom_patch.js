// /** @odoo-module */

// import { Orderline } from "@point_of_sale/app/store/models";
// import { patch } from "@web/core/utils/patch";

// // Patch untuk Orderline - Fix harga untuk struk
// patch(Orderline.prototype, {
    
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
//      * Method untuk mendapatkan harga unit yang ditampilkan di struk
//      * Selalu kembalikan LIST PRICE (harga asli produk)
//      */
//     _getDisplayUnitPrice() {
//         // Prioritaskan list_price (harga asli produk)
//         if (this.product && (this.product.list_price || this.product.lst_price)) {
//             return this.product.list_price || this.product.lst_price;
//         }
//         // Fallback ke harga di line
//         return this.price;
//     },

//     /**
//      * Method untuk mendapatkan harga total line untuk struk
//      */
//     _getDisplayLineTotal() {
//         return this.get_display_price();
//     },

//     /**
//      * Override getDisplayData untuk fix harga di struk
//      */
//     getDisplayData() {
//         const displayData = super.getDisplayData();
        
//         // PERBAIKAN: Dapatkan harga unit yang benar untuk struk (LIST PRICE)
//         const displayUnitPrice = this._getDisplayUnitPrice();
        
//         // Format harga unit untuk struk
//         displayData.unitPrice = this._formatCurrencyWithoutDecimals(displayUnitPrice);
        
//         // Simpan juga dalam originalUnitPrice untuk konsistensi
//         displayData.originalUnitPrice = this._formatCurrencyWithoutDecimals(displayUnitPrice);
        
//         // Dapatkan harga total line (sudah termasuk pricelist)
//         const lineTotal = this._getDisplayLineTotal();
        
//         // Format total line
//         displayData.price = this._formatCurrencyWithoutDecimals(lineTotal);
        
//         // Tandai apakah ada pricelist yang diterapkan
//         displayData.hasPricelist = (displayUnitPrice !== this.price);
        
//         // Debug logging (bisa di-comment jika tidak diperlukan)
//         console.log("=== DEBUG Orderline ===");
//         console.log("Product:", this.product?.display_name);
//         console.log("List Price:", this.product?.list_price);
//         console.log("Lst Price:", this.product?.lst_price);
//         console.log("Line Price (this.price):", this.price);
//         console.log("Display Unit Price:", displayUnitPrice);
//         console.log("Line Total:", lineTotal);
//         console.log("Has Pricelist:", displayData.hasPricelist);
        
//         return displayData;
//     }
// });