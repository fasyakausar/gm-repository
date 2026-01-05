/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class DbNameNavbar extends Component {
    setup() {
        this.rpc = useService("rpc");
        this.state = useState({ dbName: "Loading..." });

        onWillStart(async () => {
            try {
                // ✅ Ambil nama database langsung dari session info
                const sessionInfo = await this.rpc("/web/session/get_session_info");
                this.state.dbName = sessionInfo.db || "Unknown DB";
            } catch (e) {
                this.state.dbName = "Unknown DB";
                console.error("Failed to fetch database name:", e);
            }
        });
    }

    // ✅ Method untuk refresh browser
    refreshBrowser() {
        window.location.reload();
    }

    // ✅ Method untuk hapus semua cookies
    clearAllCookies() {
        const cookies = document.cookie.split(";");
        
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i];
            const eqPos = cookie.indexOf("=");
            const name = eqPos > -1 ? cookie.substr(0, eqPos).trim() : cookie.trim();
            
            // Hapus cookie untuk domain saat ini
            document.cookie = name + "=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/";
            
            // Hapus cookie untuk subdomain
            const domain = window.location.hostname;
            document.cookie = name + "=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/;domain=" + domain;
            document.cookie = name + "=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/;domain=." + domain;
        }
        
        console.log("All cookies cleared");
    }

    // ✅ Method untuk reset cache, cookies, dan refresh
    async resetCacheAndRefresh() {
        try {
            // 1. Hapus cache service worker (jika ada)
            if ('caches' in window) {
                const cacheNames = await caches.keys();
                await Promise.all(
                    cacheNames.map(cacheName => caches.delete(cacheName))
                );
                console.log("Browser cache cleared");
            }

            // 2. Hapus localStorage dan sessionStorage
            localStorage.clear();
            sessionStorage.clear();
            console.log("Local storage and session storage cleared");

            // 3. Hapus semua cookies
            this.clearAllCookies();

            // 4. Hapus cache Odoo khusus (jika ada)
            if (window.odoo && window.odoo.debug) {
                window.odoo.debug.clearCache();
            }

            // 5. Refresh browser setelah membersihkan cache
            setTimeout(() => {
                window.location.reload();
            }, 500);
            
        } catch (error) {
            console.error("Error clearing cache:", error);
            // Tetap refresh meskipun ada error
            window.location.reload();
        }
    }
}

DbNameNavbar.template = "integrasi_pos.DbNameNavbar";

registry.category("systray").add("db_name_navbar", {
    Component: DbNameNavbar,
    sequence: 1,
});