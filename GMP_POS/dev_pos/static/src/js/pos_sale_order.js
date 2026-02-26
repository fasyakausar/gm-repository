/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { SaleOrderManagementScreen } from "@pos_sale/app/order_management_screen/sale_order_management_screen/sale_order_management_screen";
import { _t } from "@web/core/l10n/translation";
import { Orderline } from "@point_of_sale/app/store/models";
import { ConfirmPopup } from "@point_of_sale/app/utils/confirm_popup/confirm_popup";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";
import { floatIsZero } from "@web/core/utils/numbers";

function getId(fieldVal) {
    return fieldVal && fieldVal[0];
}

patch(SaleOrderManagementScreen.prototype, {
    /**
     * Cari hr.employee yang terhubung ke res.users berdasarkan user_id dari SO.
     * SO.user_id → res.users → hr.employee (via user_id field di hr.employee)
     */
    _getSalespersonEmployee(resUserId) {
        if (!resUserId || !this.pos.hr_employee) return null;
        return this.pos.hr_employee.find(emp => emp.user_id === resUserId) || null;
    },

    async onClickSaleOrder(clickedOrder) {
        let currentPOSOrder = this.pos.get_order();
        const sale_order = await this._getSaleOrder(clickedOrder.id);
        clickedOrder.shipping_date = this.pos.config.ship_later && sale_order.shipping_date;

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
                const title = _t("Customer loading error");
                const body = _t(
                    "There was a problem in loading the %s customer.",
                    sale_order.partner_id[1]
                );
                await this.popup.add(ErrorPopup, { title, body });
                return;
            }
            currentPOSOrder.set_partner(
                this.pos.db.get_partner_by_id(sale_order.partner_id[0])
            );
        }

        const orderFiscalPos = sale_order.fiscal_position_id
            ? this.pos.fiscal_positions.find(
                  (position) => position.id === sale_order.fiscal_position_id[0]
              )
            : false;
        if (orderFiscalPos) {
            currentPOSOrder.fiscal_position = orderFiscalPos;
        }

        const orderPricelist = sale_order.pricelist_id
            ? this.pos.pricelists.find(
                  (pricelist) => pricelist.id === sale_order.pricelist_id[0]
              )
            : false;
        if (orderPricelist) {
            currentPOSOrder.set_pricelist(orderPricelist);
        }

        // ✅ Resolve salesperson: SO.user_id (res.users) → hr.employee
        // sale_order.user_id = [id, name] seperti Many2one field Odoo
        const soUserId = sale_order.user_id ? getId(sale_order.user_id) : null;
        const soUserName = sale_order.user_id ? sale_order.user_id[1] : "";
        const employeeMatch = soUserId ? this._getSalespersonEmployee(soUserId) : null;

        if (employeeMatch) {
            console.log(
                "✅ [SALESPERSON] SO user_id=%s (%s) → hr.employee id=%s name=%s",
                soUserId, soUserName, employeeMatch.id, employeeMatch.name
            );
        } else if (soUserId) {
            console.warn(
                "⚠️ [SALESPERSON] SO user_id=%s (%s) tidak ditemukan di hr.employee (is_sales=True)",
                soUserId, soUserName
            );
        }

        // SETTLE THE ORDER
        const lines = sale_order.order_line;
        const product_to_add_in_pos = lines
            .filter((line) => !this.pos.db.get_product_by_id(line.product_id[0]))
            .map((line) => line.product_id[0]);

        if (product_to_add_in_pos.length) {
            const { confirmed } = await this.popup.add(ConfirmPopup, {
                title: _t("Products not available in POS"),
                body: _t(
                    "Some of the products in your Sale Order are not available in POS, do you want to import them?"
                ),
                confirmText: _t("Yes"),
                cancelText: _t("No"),
            });
            if (confirmed) {
                await this.pos._addProducts(product_to_add_in_pos);
            }
        }

        let useLoadedLots;

        for (var i = 0; i < lines.length; i++) {
            const line = lines[i];
            if (!this.pos.db.get_product_by_id(line.product_id[0])) {
                continue;
            }

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
                customer_note: line.customer_note,
            };
            const new_line = new Orderline({ env: this.env }, line_values);

            // ✅ Set salesperson dari SO ke setiap orderline
            if (employeeMatch) {
                new_line.salesperson = String(employeeMatch.name);
                new_line.user_id = Number(employeeMatch.id);
            } else if (soUserName) {
                // Fallback: pakai nama dari SO langsung, tanpa employee id
                new_line.salesperson = String(soUserName);
                new_line.user_id = 0;
            }

            if (
                new_line.get_product().tracking !== "none" &&
                (this.pos.picking_type.use_create_lots ||
                    this.pos.picking_type.use_existing_lots) &&
                line.lot_names?.length > 0
            ) {
                const { confirmed } =
                    useLoadedLots === undefined
                        ? await this.popup.add(ConfirmPopup, {
                              title: _t("SN/Lots Loading"),
                              body: _t(
                                  "Do you want to load the SN/Lots linked to the Sales Order?"
                              ),
                              confirmText: _t("Yes"),
                              cancelText: _t("No"),
                          })
                        : { confirmed: useLoadedLots };
                useLoadedLots = confirmed;
                if (useLoadedLots) {
                    new_line.setPackLotLines({
                        modifiedPackLotLines: [],
                        newPackLotLines: (line.lot_names || []).map((name) => ({
                            lot_name: name,
                        })),
                    });
                }
            }
            new_line.setQuantityFromSOL(line);
            new_line.set_unit_price(line.price_unit);
            new_line.set_discount(line.discount);

            const product = this.pos.db.get_product_by_id(line.product_id[0]);
            const product_unit = product.get_unit();

            if (product_unit && !product.get_unit().is_pos_groupable) {
                let remaining_quantity = new_line.quantity;
                while (!floatIsZero(remaining_quantity, 6)) {
                    const splitted_line = new Orderline({ env: this.env }, line_values);
                    // ✅ Propagate salesperson ke split lines
                    if (employeeMatch) {
                        splitted_line.salesperson = String(employeeMatch.name);
                        splitted_line.user_id = Number(employeeMatch.id);
                    } else if (soUserName) {
                        splitted_line.salesperson = String(soUserName);
                        splitted_line.user_id = 0;
                    }
                    splitted_line.set_quantity(Math.min(remaining_quantity, 1.0), true);
                    splitted_line.set_discount(line.discount);
                    this.pos.get_order().add_orderline(splitted_line);
                    remaining_quantity -= splitted_line.quantity;
                }
            } else if (new_line.get_product().tracking == "lot") {
                let total_lot_quantity = 0;
                for (const lot of line.lot_names) {
                    total_lot_quantity += line.lot_qty_by_name?.[lot] || 0;
                    const splitted_line = new Orderline({ env: this.env }, line_values);
                    // ✅ Propagate salesperson ke lot lines
                    if (employeeMatch) {
                        splitted_line.salesperson = String(employeeMatch.name);
                        splitted_line.user_id = Number(employeeMatch.id);
                    } else if (soUserName) {
                        splitted_line.salesperson = String(soUserName);
                        splitted_line.user_id = 0;
                    }
                    splitted_line.set_quantity(line.lot_qty_by_name?.[lot] || 0, true);
                    splitted_line.set_unit_price(line.price_unit);
                    splitted_line.set_discount(line.discount);
                    splitted_line.setPackLotLines({
                        modifiedPackLotLines: [],
                        newPackLotLines: [{ lot_name: lot }],
                        setQuantity: false,
                    });
                    this.pos.get_order().add_orderline(splitted_line);
                }
                if (total_lot_quantity < new_line.quantity) {
                    const remaining_quantity = new_line.quantity - total_lot_quantity;
                    const splitted_line = new Orderline({ env: this.env }, line_values);
                    // ✅ Propagate salesperson ke sisa line
                    if (employeeMatch) {
                        splitted_line.salesperson = String(employeeMatch.name);
                        splitted_line.user_id = Number(employeeMatch.id);
                    } else if (soUserName) {
                        splitted_line.salesperson = String(soUserName);
                        splitted_line.user_id = 0;
                    }
                    splitted_line.set_quantity(remaining_quantity, true);
                    splitted_line.set_unit_price(line.price_unit);
                    splitted_line.set_discount(line.discount);
                    this.pos.get_order().add_orderline(splitted_line);
                }
            } else {
                this.pos.get_order().add_orderline(new_line);
            }
        }

        this.pos.closeScreen();
    }
});