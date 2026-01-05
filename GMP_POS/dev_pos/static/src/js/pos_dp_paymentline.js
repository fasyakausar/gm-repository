/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { NumberPopup } from "@point_of_sale/app/utils/input_popups/number_popup";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";
import { useService } from "@web/core/utils/hooks";
import { PaymentScreenPaymentLines } from "@point_of_sale/app/screens/payment_screen/payment_lines/payment_lines";
import { patch } from "@web/core/utils/patch";

// Global cache untuk semua instance
const globalDpCache = {
    promise: null,
    ids: null,
    lastFetch: 0,
    CACHE_DURATION: 5 * 60 * 1000 // 5 minutes cache
};

patch(PaymentScreenPaymentLines.prototype, {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.popup = useService("popup");
    },
    
    async selectLine(paymentline) {
        // Check if this is a DP payment (readonly)
        const isDpPayment = await this._isDpPaymentMethod(paymentline);
        
        if (isDpPayment) {
            await this.popup.add(ErrorPopup, {
                title: _t("Cannot Modify Payment"),
                body: _t(
                    "This payment method is automatically set based on gift card balance and cannot be modified.\n\n" +
                    "Current amount: %s",
                    this._formatCurrency(paymentline.amount || 0)
                ),
            });
            return; // Block selection
        }
        
        // Original logic for non-DP payments
        super.selectLine(paymentline);
    },
    
    async _isDpPaymentMethod(paymentline) {
        if (!paymentline || !paymentline.payment_method || !paymentline.payment_method.id) {
            return false;
        }
        
        try {
            // Gunakan global cache
            await this._ensureDpCache();
            
            // Cek apakah payment method ID ada di daftar DP payment methods
            const isDp = globalDpCache.ids.includes(paymentline.payment_method.id);
            
            if (isDp) {
                console.log('[DP BLOCKED] Payment method:', 
                           paymentline.payment_method.name, 
                           'ID:', paymentline.payment_method.id);
            }
            
            return isDp;
            
        } catch (error) {
            console.error('[ERROR] Failed to check DP payment method:', error);
            return false;
        }
    },
    
    async _ensureDpCache() {
        const now = Date.now();
        
        // Jika cache masih valid, gunakan cache
        if (globalDpCache.ids !== null && 
            (now - globalDpCache.lastFetch) < globalDpCache.CACHE_DURATION) {
            return;
        }
        
        // Jika sedang fetching, tunggu
        if (globalDpCache.promise) {
            await globalDpCache.promise;
            return;
        }
        
        // Buat promise baru untuk fetch data
        globalDpCache.promise = this._fetchDpPaymentMethodIds()
            .then(ids => {
                globalDpCache.ids = ids;
                globalDpCache.lastFetch = Date.now();
                globalDpCache.promise = null;
                return ids;
            })
            .catch(error => {
                globalDpCache.promise = null;
                throw error;
            });
        
        await globalDpCache.promise;
    },
    
    async _fetchDpPaymentMethodIds() {
        try {
            console.log('[CACHE] Fetching DP payment methods from backend...');
            
            const dpMethodIds = await this.orm.search(
                'pos.payment.method',
                [['gm_is_dp', '=', true]],
                { limit: 100 }
            );
            
            console.log('[CACHE] DP Payment Method IDs loaded:', dpMethodIds.length, 'methods');
            return dpMethodIds;
            
        } catch (error) {
            console.error('[CACHE ERROR] Failed to fetch DP payment methods:', error);
            return [];
        }
    },
    
    _formatCurrency(amount) {
        // Format sederhana
        try {
            const num = parseFloat(amount) || 0;
            return num.toLocaleString('id-ID', {
                minimumFractionDigits: 0,
                maximumFractionDigits: 2
            });
        } catch (e) {
            return amount.toString();
        }
    }
});