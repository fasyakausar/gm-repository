// /** @odoo-module **/

// import { patch } from "@web/core/utils/patch";
// import { PosStore } from "@point_of_sale/app/store/pos_store";

// /**
//  * ✅ AUTO-FILL CUSTOMER dari Gift Card Redemption
//  * 
//  * Hook ke _activateCode yang ada di pos_loyalty override.
//  * Setelah kode berhasil diaktivasi, cek couponCache untuk partner_id,
//  * lalu set ke order jika order belum punya customer.
//  */
// patch(PosStore.prototype, {

//     /**
//      * Override _activateCode dari pos_loyalty
//      * Dipanggil saat kasir scan/input kode gift card di ProductScreen
//      */
//     async _activateCode(code) {
//         console.log("🎁 [AUTO-CUSTOMER] _activateCode:", code);

//         // Panggil parent (pos_loyalty _activateCode) terlebih dahulu
//         // agar couponCache sudah terisi dengan data terbaru
//         const result = await super._activateCode(...arguments);

//         // Setelah parent selesai, coba auto-fill customer
//         try {
//             await this._autoFillCustomerFromActivatedCode(code);
//         } catch (e) {
//             // Jangan sampai error ini mengganggu flow utama
//             console.error("🎁 [AUTO-CUSTOMER] Error (non-fatal):", e);
//         }

//         return result;
//     },

//     /**
//      * Core logic: cari partner dari couponCache berdasarkan kode yang baru diaktivasi,
//      * lalu set ke order aktif jika belum ada customer.
//      * 
//      * Menggunakan couponCache yang sudah diisi oleh _activateCode (pos_loyalty),
//      * sehingga tidak perlu ORM call tambahan.
//      */
//     async _autoFillCustomerFromActivatedCode(code) {
//         const order = this.get_order();
//         if (!order) return;

//         // Skip jika order sudah punya customer
//         if (order.get_partner()) {
//             console.log("🎁 [AUTO-CUSTOMER] Order sudah ada customer:", order.get_partner().name);
//             return;
//         }

//         // ============================================================
//         // STEP 1: Cari coupon di cache berdasarkan kode
//         // couponCache diisi oleh fetchCoupons() yang dipanggil
//         // saat _activateCode berhasil di pos_loyalty
//         // ============================================================
//         let targetCoupon = null;

//         for (const coupon of Object.values(this.couponCache || {})) {
//             if (coupon.code === code) {
//                 targetCoupon = coupon;
//                 break;
//             }
//         }

//         if (!targetCoupon) {
//             console.log("🎁 [AUTO-CUSTOMER] Coupon tidak ditemukan di cache untuk code:", code);
//             return;
//         }

//         console.log("🎁 [AUTO-CUSTOMER] Coupon ditemukan:", {
//             id: targetCoupon.id,
//             code: targetCoupon.code,
//             program_id: targetCoupon.program_id,
//             partner_id: targetCoupon.partner_id,
//         });

//         // ============================================================
//         // STEP 2: Validasi bahwa ini adalah gift card program
//         // ============================================================
//         const program = this.program_by_id?.[targetCoupon.program_id];
//         if (!program) {
//             console.log("🎁 [AUTO-CUSTOMER] Program tidak ditemukan:", targetCoupon.program_id);
//             return;
//         }

//         if (program.program_type !== 'gift_card') {
//             console.log("🎁 [AUTO-CUSTOMER] Bukan gift card program, skip. Type:", program.program_type);
//             return;
//         }

//         // ============================================================
//         // STEP 3: Cek apakah coupon punya partner_id
//         // partner_id bisa berupa number (dari PosLoyaltyCard constructor)
//         // ============================================================
//         const partnerId = targetCoupon.partner_id;
//         if (!partnerId || partnerId === false || partnerId === 0) {
//             console.log("🎁 [AUTO-CUSTOMER] Gift card tidak memiliki customer terdaftar.");
//             return;
//         }

//         console.log("🎁 [AUTO-CUSTOMER] Gift card milik partner ID:", partnerId);

//         // ============================================================
//         // STEP 4: Cari partner di local DB POS
//         // Partner mungkin sudah ada di cache karena addPartners()
//         // di _processData memuat loyalty_cards sekaligus
//         // ============================================================
//         let partner = this.db.get_partner_by_id(partnerId);

//         if (!partner) {
//             console.log("🎁 [AUTO-CUSTOMER] Partner tidak ada di cache, fetch dari server...");
//             partner = await this._fetchAndCachePartner(partnerId);
//         }

//         if (!partner) {
//             console.warn("🎁 [AUTO-CUSTOMER] Partner ID", partnerId, "tidak bisa dimuat.");
//             return;
//         }

//         // ============================================================
//         // STEP 5: Set partner ke order
//         // ============================================================
//         order.set_partner(partner);
//         console.log("✅ [AUTO-CUSTOMER] Customer berhasil di-set:", partner.name);

//         // Notifikasi ke kasir
//         this._notifyCustomerAutoFilled(partner.name);
//     },

//     /**
//      * Fetch partner dari server dan tambahkan ke local DB POS.
//      * Menggunakan pattern yang sama dengan _loadMissingPartners() di pos_store.js
//      * 
//      * @param {number} partnerId
//      * @returns {object|null} partner object atau null
//      */
//     async _fetchAndCachePartner(partnerId) {
//         try {
//             // Gunakan method resmi Odoo untuk fetch partner ke POS
//             // (sama persis dengan yang dipakai _loadMissingPartners)
//             const fetchedPartners = await this.orm.silent.call(
//                 "pos.session",
//                 "get_pos_ui_res_partner_by_params",
//                 [[odoo.pos_session_id], { domain: [["id", "=", partnerId]] }]
//             );

//             if (fetchedPartners && fetchedPartners.length > 0) {
//                 // addPartners() juga akan mengisi partnerId2CouponIds dari loyalty_cards
//                 this.addPartners(fetchedPartners);
//                 console.log("✅ [AUTO-CUSTOMER] Partner berhasil di-fetch:", fetchedPartners[0].name);
//                 return this.db.get_partner_by_id(partnerId);
//             }

//         } catch (error) {
//             console.error("❌ [AUTO-CUSTOMER] Gagal fetch partner:", error);
//         }
//         return null;
//     },

//     /**
//      * Tampilkan notifikasi ke kasir bahwa customer otomatis terisi.
//      * Menggunakan notification service yang tersedia di POS.
//      * 
//      * @param {string} partnerName
//      */
//     _notifyCustomerAutoFilled(partnerName) {
//         try {
//             // Coba gunakan notification service
//             const notif = this.env?.services?.notification;
//             if (notif) {
//                 notif.add(
//                     `Customer otomatis terisi: ${partnerName}`,
//                     {
//                         type: 'success',
//                         title: '🎁 Gift Card',
//                         sticky: false,
//                     }
//                 );
//                 return;
//             }
//         } catch (e) {
//             // Fallback: tidak ada notifikasi, tidak masalah
//         }
//     },
// });