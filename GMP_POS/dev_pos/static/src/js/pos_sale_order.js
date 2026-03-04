/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { SaleOrderManagementScreen } from "@pos_sale/app/order_management_screen/sale_order_management_screen/sale_order_management_screen";
import { _t } from "@web/core/l10n/translation";
import { Orderline } from "@point_of_sale/app/store/models";
import { ConfirmPopup } from "@point_of_sale/app/utils/confirm_popup/confirm_popup";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";


function getId(fieldVal) {
    return fieldVal && fieldVal[0];
}

patch(SaleOrderManagementScreen.prototype, {

    /**
     * ✅ Override _getSaleOrder untuk pastikan user_id ikut ter-fetch
     */
    async _getSaleOrder(id) {
        const sale_order = await this.orm.call(
            'sale.order',
            'read',
            [[id]],
            {
                fields: [
                    'name', 'partner_id', 'partner_invoice_id', 'partner_shipping_id',
                    'pricelist_id', 'fiscal_position_id', 'payment_term_id',
                    'order_line', 'picking_ids', 'date_order', 'note',
                    'user_id',  // ✅ Salesperson SO → res.users → [id, name]
                ],
            }
        );
        const order = sale_order[0];

        if (order.order_line.length) {
            const lines = await this.orm.call(
                'sale.order.line',
                'read',
                [order.order_line],
                {
                    fields: [
                        'product_id', 'name', 'price_unit', 'product_uom_qty',
                        'qty_delivered', 'qty_invoiced', 'discount', 'tax_id',
                        'display_type'
                    ],
                }
            );
            order.order_line = lines;
        }

        return order;
    },

    /**
     * Cari hr.employee berdasarkan res.users id.
     * hr.employee.user_id dari search_read = [res_users_id, name] atau false
     */
    _getSalespersonEmployee(resUserId) {
        if (!resUserId || !this.pos.hr_employee?.length) return null;
        return this.pos.hr_employee.find(emp => {
            const empUserId = Array.isArray(emp.user_id) ? emp.user_id[0] : emp.user_id;
            return empUserId === resUserId;
        }) || null;
    },

    /**
     * Tempel salesperson ke satu orderline.
     * Dipanggil untuk SEMUA line termasuk split lines.
     */
    _setLineSalesperson(line, employee, fallbackName) {
        if (employee) {
            line.salesperson = String(employee.name);
            line.user_id = Number(employee.id);
        } else if (fallbackName) {
            line.salesperson = String(fallbackName);
            line.user_id = 0;
        }
    },

    async onClickSaleOrder(clickedOrder) {
        let currentPOSOrder = this.pos.get_order();
        const sale_order = await this._getSaleOrder(clickedOrder.id);
        clickedOrder.shipping_date = this.pos.config.ship_later && sale_order.date_order;

        const currentSaleOrigin = this._getSaleOrderOrigin(currentPOSOrder);
        const currentSaleOriginId = currentSaleOrigin && currentSaleOrigin.id;

        if (currentSaleOriginId) {
            const linkedSO = await this._getSaleOrder(currentSaleOriginId);
            if (
                getId(linkedSO.partner_id) !== getId(sale_order.partner_id) ||
                getId(linkedSO.partner_invoice_id) !== getId(sale_order.partner_invoice_id) ||
                getId(linkedSO.partner_shipping_id) !== getId(sale_order.partner_shipping_id)
            ) {
                currentPOSOrder = this.pos.add_new_order();
                this.notification.add(_t("A new order has been created."), 4000);
            }
        }

        const order_partner = this.pos.db.get_partner_by_id(sale_order.partner_id[0]);
        if (order_partner) {
            currentPOSOrder.set_partner(order_partner);
        } else {
            try {
                await this.pos._loadPartners([sale_order.partner_id[0]]);
            } catch {
                await this.popup.add(ErrorPopup, {
                    title: _t("Customer loading error"),
                    body: _t("There was a problem in loading the %s customer.", sale_order.partner_id[1]),
                });
                return;
            }
            currentPOSOrder.set_partner(
                this.pos.db.get_partner_by_id(sale_order.partner_id[0])
            );
        }

        const orderFiscalPos = sale_order.fiscal_position_id
            ? this.pos.fiscal_positions.find(p => p.id === sale_order.fiscal_position_id[0])
            : false;
        if (orderFiscalPos) currentPOSOrder.fiscal_position = orderFiscalPos;

        const orderPricelist = sale_order.pricelist_id
            ? this.pos.pricelists.find(p => p.id === sale_order.pricelist_id[0])
            : false;
        if (orderPricelist) currentPOSOrder.set_pricelist(orderPricelist);

        // ✅ Resolve salesperson SEKALI dari header SO
        // Hasilnya di-tempel ke SEMUA line item (5 item → semua dapat salesperson yang sama)
        const soUserId   = sale_order.user_id ? getId(sale_order.user_id) : null;
        const soUserName = sale_order.user_id ? sale_order.user_id[1]    : "";
        const employee   = this._getSalespersonEmployee(soUserId);

        console.log("🧑 [SALESPERSON] SO:", sale_order.name,
                    "| user_id:", soUserId, soUserName,
                    "| employee:", employee ? employee.name : "NOT FOUND");

        const lines = sale_order.order_line;
        const product_to_add_in_pos = lines
            .filter(line => !this.pos.db.get_product_by_id(line.product_id[0]))
            .map(line => line.product_id[0]);

        if (product_to_add_in_pos.length) {
            const { confirmed } = await this.popup.add(ConfirmPopup, {
                title: _t("Products not available in POS"),
                body: _t("Some of the products in your Sale Order are not available in POS, do you want to import them?"),
                confirmText: _t("Yes"),
                cancelText: _t("No"),
            });
            if (confirmed) await this.pos._addProducts(product_to_add_in_pos);
        }

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];
            if (!this.pos.db.get_product_by_id(line.product_id[0])) continue;

            let taxIds = orderFiscalPos ? undefined : line.tax_id;
            if (line.product_id[0] === this.pos.config.down_payment_product_id?.[0]) {
                taxIds = line.tax_id;
            }

            const line_values = {
                pos: this.pos,
                order: this.pos.get_order(),
                product: this.pos.db.get_product_by_id(line.product_id[0]),
                description: line.name,
                price: line.price_unit,
                tax_ids: taxIds,
                price_manually_set: false,
                price_type: "automatic",
                sale_order_origin_id: clickedOrder,
                sale_order_line_id: line,
            };

            const new_line = new Orderline({ env: this.env }, line_values);
            this._setLineSalesperson(new_line, employee, soUserName); // ✅

            new_line.setQuantityFromSOL(line);
            new_line.set_unit_price(line.price_unit);
            new_line.set_discount(line.discount);

            this.pos.get_order().add_orderline(new_line);
        }

        this.pos.closeScreen();
    }
});