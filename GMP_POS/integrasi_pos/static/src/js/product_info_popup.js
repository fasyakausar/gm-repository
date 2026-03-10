/** @odoo-module **/

import { ProductInfoPopup } from "@point_of_sale/app/screens/product_screen/product_info_popup/product_info_popup";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { useState } from "@odoo/owl";

patch(ProductInfoPopup.prototype, {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.extraState = useState({
            loading: false,
            productDetail: null,
        });
        this._loadExtraProductDetail();
    },

    async _loadExtraProductDetail() {
        const productId = this.props.product.id;
        if (!productId) return;
        this.extraState.loading = true;
        try {
            const results = await this.orm.read("product.product", [productId], [
                "display_name",
                "description",
                "description_sale",
                "type",
                "categ_id",
                "uom_id",
                "uom_po_id",
                "weight",
                "volume",
                "responsible_id",
                "product_tag_ids",
            ]);
            if (results && results.length) {
                this.extraState.productDetail = results[0];
            }
        } catch (e) {
            console.warn("[ProductInfoPopupPatch] Failed to load product details:", e);
        } finally {
            this.extraState.loading = false;
        }
    },

    get productDetail() {
        return this.extraState.productDetail;
    },

    get totalAvailableQty() {
        if (!this.productInfo?.warehouses?.length) return 0;
        return this.productInfo.warehouses.reduce(
            (sum, wh) => sum + (wh.available_quantity || 0), 0
        );
    },

    get totalForecastedQty() {
        if (!this.productInfo?.warehouses?.length) return 0;
        return this.productInfo.warehouses.reduce(
            (sum, wh) => sum + (wh.forecasted_quantity || 0), 0
        );
    },
});