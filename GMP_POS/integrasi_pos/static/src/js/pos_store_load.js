/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";

patch(PosStore.prototype, {
    async _processData(loadedData) {
        await super._processData(...arguments);

        try {
            console.log("🔄 Starting custom POS data processing...");

            // 🔐 Config Settings
            const configSettings = loadedData["res.config.settings"]?.[0];
            if (configSettings) {
                Object.assign(this.config, configSettings);
                console.log("✅ POS Config injected:", {
                    manager_validation: configSettings.manager_validation,
                    validate_discount: configSettings.validate_discount,
                    validate_payment: configSettings.validate_payment,
                    enable_auto_rounding: configSettings.enable_auto_rounding,
                    rounding_value: configSettings.rounding_value,
                    rounding_product_id: configSettings.rounding_product_id,
                });

                // ✅ VALIDATE ROUNDING CONFIGURATION
                if (configSettings.enable_auto_rounding) {
                    console.group("🔄 AUTO ROUNDING CONFIGURATION");
                    console.log("✅ Auto Rounding: ENABLED");
                    console.log(`💯 Rounding Value: ${configSettings.rounding_value}`);

                    if (configSettings.rounding_product_id) {
                        console.log(`📦 Rounding Product: ${configSettings.rounding_product_id.name} (ID: ${configSettings.rounding_product_id.id})`);

                        const roundingProduct = this.db.get_product_by_id(configSettings.rounding_product_id.id);
                        if (roundingProduct) {
                            console.log(`✅ Rounding product found in POS database`);
                            console.log(`   Name: ${roundingProduct.display_name}`);
                            console.log(`   Available in POS: ${roundingProduct.available_in_pos}`);
                        } else {
                            console.error(`❌ CRITICAL: Rounding product NOT found in POS database!`);
                            console.error(`   Product ID ${configSettings.rounding_product_id.id} is not loaded`);
                            console.error(`   Auto rounding will NOT work!`);
                            console.error(`   Please check:`);
                            console.error(`   1. Product exists in database`);
                            console.error(`   2. Product 'available_in_pos' is TRUE`);
                            console.error(`   3. Product is not archived`);
                        }
                    } else {
                        console.error(`❌ CRITICAL: Rounding product NOT configured!`);
                        console.error(`   Please set rounding product in POS Configuration > Auto Rounding`);
                    }
                    console.groupEnd();
                } else {
                    console.log("ℹ️ Auto Rounding: DISABLED");
                }
            } else {
                console.warn("⚠️ No config settings loaded");
            }

            // 🏢 Company Info
            const companies = loadedData["res.company"] || [];
            if (companies.length) {
                this.company = companies[0];
                console.log("✅ Company loaded:", this.company.name);
            } else {
                console.warn("⚠️ No company data loaded");
            }

            // 📦 Barcode Config
            const barcodeConfig = loadedData["barcode.config"]?.[0];
            if (barcodeConfig) {
                Object.assign(this.config, {
                    digit_awal: parseInt(barcodeConfig.digit_awal || 2),
                    digit_akhir: parseInt(barcodeConfig.digit_akhir || 4),
                    prefix_timbangan: barcodeConfig.prefix_timbangan || "",
                    panjang_barcode: parseInt(barcodeConfig.panjang_barcode || 7),
                    multiple_barcode_activate: barcodeConfig.multiple_barcode_activate || false,
                });
                console.log("✅ Barcode Config loaded:", {
                    digit_awal: this.config.digit_awal,
                    digit_akhir: this.config.digit_akhir,
                    prefix_timbangan: this.config.prefix_timbangan,
                });
            } else {
                console.warn("⚠️ No barcode config loaded");
            }

            // 👤 HR Employee (Salesperson)
            this.hr_employee = [];
            const rawEmployees = loadedData["hr.employee"];
            if (Array.isArray(rawEmployees)) {
                this.hr_employee = rawEmployees;
                console.log(`✅ Loaded ${this.hr_employee.length} HR employees`);
            } else {
                console.warn("⚠️ No HR employees loaded");
            }

            // 👤 HR Employee Config Settings
            this.hr_employee_config = [];
            const rawEmployeeConfig = loadedData["hr.employee.config.settings"];
            if (Array.isArray(rawEmployeeConfig)) {
                this.hr_employee_config = rawEmployeeConfig;
                console.log(`✅ Loaded ${this.hr_employee_config.length} HR employee configs`);
            } else {
                console.warn("⚠️ No HR employee configs loaded");
            }

            // 👤 Patch Partner Categories
            const rawPartners = loadedData["res.partner"] || [];
            const currentCompanyId = this.company?.id;

            // Dedup by id
            const partnerCategoryMap = {};
            const seenPartnerIds = new Set();

            for (const p of rawPartners) {
                if (!p || !p.id || seenPartnerIds.has(p.id)) continue;
                seenPartnerIds.add(p.id);
                partnerCategoryMap[p.id] = Array.isArray(p.category_id) ? p.category_id : [];
            }

            console.log(
                `👤 rawPartners: ${rawPartners.length}, unique: ${seenPartnerIds.size} ` +
                `(company=${currentCompanyId})`
            );

            // Apply category_id + dedup this.partners by id
            if (this.partners) {
                const seenIds = new Set();
                this.partners = this.partners.filter(p => {
                    if (seenIds.has(p.id)) return false;
                    seenIds.add(p.id);
                    return true;
                });

                let categorizedCount = 0;
                for (const p of this.partners) {
                    try {
                        if (partnerCategoryMap[p.id] !== undefined) {
                            p.category_id = partnerCategoryMap[p.id];
                            if (p.category_id.length > 0) categorizedCount++;
                        }
                    } catch (e) {
                        console.error("❌ Error patching partner:", p, e);
                    }
                }
                console.log(
                    `✅ Patched ${this.partners.length} partners ` +
                    `(${categorizedCount} have categories)`
                );
            } else {
                console.warn("⚠️ No partners to patch");
            }

            // 📦 Multiple Barcodes
            this.multiple_barcodes = [];
            const rawBarcodes = loadedData["multiple.barcode"];
            if (Array.isArray(rawBarcodes)) {
                this.multiple_barcodes = rawBarcodes;
                console.log(`✅ Loaded ${this.multiple_barcodes.length} multiple barcodes`);
            } else {
                console.warn("⚠️ No multiple barcodes loaded");
            }

            // 💰 POS Cashier Logs
            this.cashier_logs = [];
            const rawLogs = loadedData["pos.cashier.log"];
            if (Array.isArray(rawLogs)) {
                this.cashier_logs = rawLogs;
                console.log(`✅ Loaded ${this.cashier_logs.length} cashier logs`);
            } else {
                console.warn("⚠️ No cashier logs loaded");
            }

            // ✅ Validate Payment Methods have gm_is_card field
            if (this.payment_methods && this.payment_methods.length > 0) {
                console.group("💳 VALIDATING PAYMENT METHODS");

                let cardMethodsCount = 0;
                let missingFieldCount = 0;

                for (const pm of this.payment_methods) {
                    if (pm.gm_is_card === true) {
                        cardMethodsCount++;
                        console.log(`  ✅ Card method: ${pm.name} (ID: ${pm.id})`);
                    } else if (pm.gm_is_card === false || pm.gm_is_card === undefined) {
                        console.log(`  💵 Non-card method: ${pm.name} (ID: ${pm.id})`);
                    } else {
                        missingFieldCount++;
                        console.warn(`  ⚠️ Missing gm_is_card field: ${pm.name} (ID: ${pm.id})`);
                    }
                }

                console.log(`📊 Payment Method Summary:`);
                console.log(`   Total: ${this.payment_methods.length}`);
                console.log(`   Card methods: ${cardMethodsCount}`);
                console.log(`   Missing field: ${missingFieldCount}`);

                if (missingFieldCount > 0) {
                    console.warn(`⚠️ ${missingFieldCount} payment methods are missing gm_is_card field!`);
                    console.warn(`   Card number popup may not work correctly for these methods.`);
                }

                console.groupEnd();
            } else {
                console.warn("⚠️ No payment methods loaded");
            }

            // ✅ VALIDATE DEFAULT CUSTOMER
            console.group("👤 VALIDATING DEFAULT CUSTOMER");

            if (this.config.default_partner_id) {
                const defaultCustomerId = Array.isArray(this.config.default_partner_id)
                    ? this.config.default_partner_id[0]
                    : this.config.default_partner_id;

                const defaultCustomerName = Array.isArray(this.config.default_partner_id)
                    ? this.config.default_partner_id[1]
                    : 'Unknown';

                console.log(`🔍 Looking for default customer: ${defaultCustomerName} (ID: ${defaultCustomerId})`);

                let foundInDb = false;
                if (this.db && this.db.partner_by_id) {
                    foundInDb = !!this.db.partner_by_id[defaultCustomerId];
                }

                let foundInArray = false;
                if (this.partners) {
                    foundInArray = this.partners.some(p => p.id === defaultCustomerId);
                }

                console.log("Validation results:", {
                    defaultCustomerId,
                    defaultCustomerName,
                    foundInDb,
                    foundInArray,
                    dbPartnerCount: this.db ? Object.keys(this.db.partner_by_id || {}).length : 0,
                    partnersArrayCount: this.partners ? this.partners.length : 0,
                });

                if (foundInDb || foundInArray) {
                    console.log(`✅ Default customer '${defaultCustomerName}' is loaded and ready`);
                } else {
                    console.error(`❌ DEFAULT CUSTOMER '${defaultCustomerName}' NOT FOUND!`);
                    console.error("This will cause issues when creating new orders!");
                    console.error("Please check:", {
                        issue1: "Is the default_partner_id set correctly in pos.config?",
                        issue2: "Is the partner archived or deleted?",
                        issue3: "Is the partner filtered out by domain restrictions?",
                        samplePartners: this.partners ? this.partners.slice(0, 5).map(p => ({ id: p.id, name: p.name })) : [],
                    });
                }
            } else {
                console.log("ℹ️ No default customer configured in POS settings");
            }

            console.groupEnd();

            console.log("✅ All custom POS data loaded successfully!");
            console.log("📊 Data Summary:", {
                config: !!configSettings,
                company: !!this.company,
                barcodeConfig: !!barcodeConfig,
                employees: this.hr_employee.length,
                employeeConfigs: this.hr_employee_config.length,
                partners: this.partners ? this.partners.length : 0,
                multipleBarcodes: this.multiple_barcodes.length,
                cashierLogs: this.cashier_logs.length,
                paymentMethods: this.payment_methods ? this.payment_methods.length : 0,
                autoRounding: this.config.enable_auto_rounding || false,
                roundingValue: this.config.rounding_value || 0,
                roundingProduct: this.config.rounding_product_id ? this.config.rounding_product_id.name : 'Not set',
            });

        } catch (error) {
            console.error("❌ Critical error in _processData:", error);
            console.error("❌ Error stack:", error.stack);
            // Don't throw - allow POS to continue loading with partial data
        }
    },

    /**
     * Helper method to get rounding configuration
     */
    getRoundingConfig() {
        return {
            enabled: this.config.enable_auto_rounding || false,
            value: this.config.rounding_value || 100,
            product_id: this.config.rounding_product_id?.id || null,
            product_name: this.config.rounding_product_id?.name || null,
        };
    },

    /**
     * Helper method to validate rounding configuration
     */
    isRoundingConfigured() {
        const config = this.getRoundingConfig();

        if (!config.enabled) {
            return { valid: false, reason: 'Auto rounding is disabled' };
        }

        if (!config.product_id) {
            return { valid: false, reason: 'Rounding product not configured' };
        }

        const product = this.db.get_product_by_id(config.product_id);
        if (!product) {
            return { valid: false, reason: 'Rounding product not found in POS database' };
        }

        if (!product.available_in_pos) {
            return { valid: false, reason: 'Rounding product not available in POS' };
        }

        return { valid: true, config: config };
    },

    /**
     * Helper method to get default customer
     */
    getDefaultCustomer() {
        if (!this.config.default_partner_id) {
            return null;
        }

        const defaultCustomerId = Array.isArray(this.config.default_partner_id)
            ? this.config.default_partner_id[0]
            : this.config.default_partner_id;

        let customer = null;

        // 1. Try db.get_partner_by_id
        if (this.db && this.db.get_partner_by_id) {
            try {
                customer = this.db.get_partner_by_id(defaultCustomerId);
            } catch (e) {
                console.warn("⚠️ db.get_partner_by_id failed:", e.message);
            }
        }

        // 2. Try partners array
        if (!customer && this.partners) {
            customer = this.partners.find(p => p.id === defaultCustomerId);
        }

        // 3. Try direct db access
        if (!customer && this.db && this.db.partner_by_id) {
            customer = this.db.partner_by_id[defaultCustomerId];
        }

        // 4. Search in all db partners
        if (!customer && this.db && this.db.partner_by_id) {
            const allPartners = Object.values(this.db.partner_by_id);
            customer = allPartners.find(p => p.id === defaultCustomerId);
        }

        return customer;
    },

    /**
     * Override add_new_order to ensure default customer is set
     */
    add_new_order() {
        const order = super.add_new_order(...arguments);

        if (order && !order.partner && !order.is_refund_order) {
            const defaultCustomer = this.getDefaultCustomer();
            if (defaultCustomer) {
                order.set_partner(defaultCustomer);
                console.log("✅ Default customer auto-set on new order:", defaultCustomer.name);
            } else if (this.config.default_partner_id) {
                console.warn("⚠️ Could not set default customer - partner not found");
            }
        }

        return order;
    },

    /**
     * Helper method to get employee by ID
     */
    getEmployee(employeeId) {
        try {
            return this.hr_employee.find(emp => emp.id === employeeId);
        } catch (e) {
            console.error("❌ Error getting employee:", e);
            return null;
        }
    },

    /**
     * Helper method to check if employee is cashier
     */
    isEmployeeCashier(employeeId) {
        try {
            const config = this.hr_employee_config.find(c => {
                const empId = Array.isArray(c.employee_id) ? c.employee_id[0] : c.employee_id;
                return empId === employeeId;
            });
            return config ? config.is_cashier : false;
        } catch (e) {
            console.error("❌ Error checking cashier status:", e);
            return false;
        }
    },

    /**
     * Helper method to check if employee is sales person
     */
    isEmployeeSalesPerson(employeeId) {
        try {
            const config = this.hr_employee_config.find(c => {
                const empId = Array.isArray(c.employee_id) ? c.employee_id[0] : c.employee_id;
                return empId === employeeId;
            });
            return config ? config.is_sales_person : false;
        } catch (e) {
            console.error("❌ Error checking sales person status:", e);
            return false;
        }
    },

    /**
     * Helper method to get product by multiple barcode
     */
    getProductByMultipleBarcode(barcode) {
        try {
            const barcodeRecord = this.multiple_barcodes.find(b => b.barcode === barcode);
            if (barcodeRecord && barcodeRecord.product_id) {
                const productId = Array.isArray(barcodeRecord.product_id)
                    ? barcodeRecord.product_id[0]
                    : barcodeRecord.product_id;
                return this.db.get_product_by_id(productId);
            }
            return null;
        } catch (e) {
            console.error("❌ Error getting product by multiple barcode:", e);
            return null;
        }
    },

    /**
     * Helper method to check if manager validation is required
     */
    requiresManagerValidation(action) {
        try {
            if (!this.config.manager_validation) {
                return false;
            }

            const validationMap = {
                'discount': this.config.validate_discount,
                'discount_amount': this.config.validate_discount_amount,
                'price_change': this.config.validate_price_change,
                'payment': this.config.validate_payment,
                'refund': this.config.validate_refund,
                'delete_order': this.config.validate_order_deletion,
                'delete_line': this.config.validate_order_line_deletion,
                'end_shift': this.config.validate_end_shift,
                'close_session': this.config.validate_close_session,
                'void_sales': this.config.validate_void_sales,
                'member_schedule': this.config.validate_member_schedule,
                'cash_drawer': this.config.validate_cash_drawer,
                'reprint': this.config.validate_reprint_receipt,
                'discount_button': this.config.validate_discount_button,
                'pricelist': this.config.validate_pricelist,
                'add_remove_qty': this.config.validate_add_remove_quantity,
            };

            return validationMap[action] || false;
        } catch (e) {
            console.error("❌ Error checking manager validation:", e);
            return false;
        }
    },
});