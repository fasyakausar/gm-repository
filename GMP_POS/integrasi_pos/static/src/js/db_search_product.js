/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosDB } from "@point_of_sale/app/store/db";

patch(PosDB.prototype, {
    /**
     * FIX: Tambahkan '%' ke daftar karakter yang di-escape menjadi '.'
     * sebelum dijadikan RegExp pattern.
     *
     * Karakter '%' tidak ada di escape list original Odoo, sehingga ketika
     * user search "ysly%4x0,5", regex pattern menjadi rusak dan tidak bisa
     * match entry di category_search_string.
     */
    search_product_in_category(category_id, query) {
        let filteredProducts = [];
        let re;
        try {
            let reg = new RegExp(";product_tmpl_id:(\\d+)");
            let match = reg.exec(query);
            if (match) {
                filteredProducts = this.product_by_tmpl_id[parseInt(match[1], 10)];
                query = query.replace(reg, '');
            }
        } catch (e) {
            console.error("Search on product template ID fails", e);
        }
        try {
            // FIX: Tambahkan '%' ke daftar escape agar tidak merusak RegExp pattern
            query = query.replace(/[\[\]\(\)\+\*\?\.\-\!\&\^\$\|\~\_\{\}\:\,\\\/\%]/g, ".");
            query = query.replace(/ /g, ".+");
            if (filteredProducts && filteredProducts.length > 0) {
                const filteredProductIds = filteredProducts.map(p => p.id);
                const idsPattern = filteredProductIds.join('|');
                re = new RegExp(`(${idsPattern}):.*?` + query, "gi");
            } else {
                re = RegExp("([0-9]+):.*?" + query, "gi");
            }
        } catch {
            return [];
        }
        var results = [];
        while (results.length < this.limit) {
            var r = re.exec(this.category_search_string[category_id]);
            if (r) {
                var id = Number(r[1]);
                const product = this.get_product_by_id(id);
                if (!this.shouldAddProduct(product, results)) {
                    continue;
                }
                results.push(product);
            } else {
                break;
            }
        }
        return results;
    },
});