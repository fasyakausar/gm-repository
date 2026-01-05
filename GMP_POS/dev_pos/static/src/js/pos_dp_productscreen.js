/** @odoo-module **/

import { Order, Orderline } from "@point_of_sale/app/store/models";
import { patch } from "@web/core/utils/patch";

patch(Order.prototype, {
    /**
     * Override _getRewardLineValues to set gift card product price to 0
     * before the line is created
     */
    _getRewardLineValues(args) {
        const rewardLines = super._getRewardLineValues(args);
        const reward = args["reward"];
        
        // Check if this is a gift_card program
        if (reward && reward.program_id && reward.program_id.program_type === 'gift_card') {
            // If rewardLines is an array, set price to 0 for all lines
            if (Array.isArray(rewardLines)) {
                for (const line of rewardLines) {
                    line.price = 0;
                }
            }
        }
        
        return rewardLines;
    },

    /**
     * Override _getRewardLineValuesProduct specifically for product rewards
     */
    _getRewardLineValuesProduct(args) {
        const rewardLines = super._getRewardLineValuesProduct(args);
        const reward = args["reward"];
        
        // Check if this is a gift_card program
        if (reward && reward.program_id && reward.program_id.program_type === 'gift_card') {
            // If rewardLines is an array, set price to 0 for all lines
            if (Array.isArray(rewardLines)) {
                for (const line of rewardLines) {
                    line.price = 0;
                }
            }
        }
        
        return rewardLines;
    },

    /**
     * Override _applyReward to prevent duplicate gift card rewards and set customer note
     */
    _applyReward(reward, coupon_id, args) {
        // Check if this is a gift_card program
        if (reward && reward.program_id && reward.program_id.program_type === 'gift_card') {
            // Check if this gift card reward is already applied for this coupon
            const existingRewardLine = this.get_orderlines().find(line => 
                line.is_reward_line && 
                line.reward_id === reward.id && 
                line.coupon_id === coupon_id
            );
            
            // If already exists, don't apply again
            if (existingRewardLine) {
                return true;
            }
        }
        
        // Call parent method
        const result = super._applyReward(reward, coupon_id, args);
        
        // After applying reward, set customer note with gift card code
        if (reward && reward.program_id && reward.program_id.program_type === 'gift_card' && coupon_id) {
            const coupon = this.pos.couponCache[coupon_id];
            if (coupon && coupon.code) {
                // Find the newly added reward line
                const rewardLine = this.get_orderlines().find(line => 
                    line.is_reward_line && 
                    line.reward_id === reward.id && 
                    line.coupon_id === coupon_id
                );
                
                if (rewardLine) {
                    // Set customer note with gift card code
                    rewardLine.set_customer_note(coupon.code);
                }
            }
        }
        
        return result;
    },

    /**
     * Override getClaimableRewards to prevent gift card from being auto-claimed repeatedly
     */
    getClaimableRewards(coupon_id = false, program_id = false, auto = false) {
        const claimableRewards = super.getClaimableRewards(coupon_id, program_id, auto);
        
        // Filter out gift card rewards that are already claimed
        return claimableRewards.filter(({ coupon_id, reward }) => {
            if (reward.program_id.program_type === 'gift_card') {
                // Check if this gift card reward is already in orderlines
                const alreadyClaimed = this.get_orderlines().some(line => 
                    line.is_reward_line && 
                    line.reward_id === reward.id && 
                    line.coupon_id === coupon_id
                );
                return !alreadyClaimed;
            }
            return true;
        });
    }
});

patch(Orderline.prototype, {
    /**
     * Override get_display_data to show gift card code with product name
     */
    get_display_data() {
        const data = super.get_display_data();
        
        // Check if this is a gift card reward line
        if (this.is_reward_line && 
            this.reward_id && 
            this.reward_id.program_id && 
            this.reward_id.program_id.program_type === 'gift_card' &&
            this.coupon_id) {
            
            // Get the coupon code
            const coupon = this.pos.couponCache[this.coupon_id];
            if (coupon && coupon.code) {
                // Prepend the code to the existing product name
                data.productName = `${coupon.code} - ${data.productName}`;
            }
        }
        
        return data;
    },
    
    /**
     * Override get_product_display_name directly
     */
    get_product_display_name() {
        let productName = super.get_product_display_name();
        
        // Check if this is a gift card reward line
        if (this.is_reward_line && 
            this.reward_id && 
            this.reward_id.program_id && 
            this.reward_id.program_id.program_type === 'gift_card' &&
            this.coupon_id) {
            
            // Get the coupon code
            const coupon = this.pos.couponCache[this.coupon_id];
            if (coupon && coupon.code) {
                // Prepend the code to the existing product name
                productName = `${coupon.code} - ${productName}`;
            }
        }
        
        return productName;
    }
});