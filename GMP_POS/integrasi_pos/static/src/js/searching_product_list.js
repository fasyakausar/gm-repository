/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosDB } from "@point_of_sale/app/store/db";
import { ProductsWidget } from "@point_of_sale/app/screens/product_screen/product_list/product_list";

// ============================================================
// PATCH 1: PosDB
// Fix: '%' dari user dikonversi ke '.*' (regex multi-char wildcard)
// sehingga "ysly%4x0,5" bisa match "ysly-jz 4x0,5 mm grey..."
//
// Flow: "ysly%4x0,5"
//   → escape karakter lain → "ysly%4x0.5"
//   → % jadi .* → "ysly.*4x0.5"
//   → regex match "ysly-jz 4x0.5 mm grey 300.500v" ✅
// ============================================================
patch(PosDB.prototype, {
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
            console.error("[PosDB.patch] template ID search failed:", e);
        }
        try {
            // Step 1: escape semua karakter regex special KECUALI '%'
            query = query.replace(/[\[\]\(\)\+\*\?\.\-\!\&\^\$\|\~\_\{\}\:\,\\\/]/g, ".");
            // Step 2: '%' dikonversi ke '.*' (wildcard bebas, bisa match apapun)
            query = query.replace(/%/g, ".*");
            query = query.replace(/ /g, ".+");

            if (filteredProducts && filteredProducts.length > 0) {
                const filteredProductIds = filteredProducts.map(p => p.id);
                const idsPattern = filteredProductIds.join('|');
                re = new RegExp(`(${idsPattern}):.*?` + query, "gi");
            } else {
                re = RegExp("([0-9]+):.*?" + query, "gi");
            }
        } catch (err) {
            console.error("[PosDB.patch] regex build failed:", err);
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

// ============================================================
// PATCH 2: ProductsWidget
// Fix: pass keyword mentah (dengan '%') ke search_product_in_category
// agar Patch 1 bisa mengkonversi '%' ke wildcard '.*'
// ============================================================
patch(ProductsWidget.prototype, {
    get searchWordForLocal() {
        // Hanya strip backslash yang benar-benar merusak regex
        // '%' TIDAK di-strip karena dipakai user sebagai wildcard
        return this.searchWord.replace(/\\/g, "").trim();
    },

    get productsToDisplay() {
        const { db } = this.pos;
        let list = [];

        const rawWord = this.searchWord;
        const localWord = this.searchWordForLocal;

        if (rawWord !== "") {
            if (localWord !== "") {
                list = db.search_product_in_category(this.selectedCategoryId, localWord);
            } else {
                list = db.get_product_by_category(this.selectedCategoryId);
            }
        } else {
            list = db.get_product_by_category(this.selectedCategoryId);
        }

        list = list.filter((product) => !this.getProductListToNotDisplay().includes(product.id));
        return list.sort((a, b) => a.display_name.localeCompare(b.display_name));
    },

    get shouldShowButton() {
        return this.productsToDisplay.length === 0 && this.searchWord;
    },
});