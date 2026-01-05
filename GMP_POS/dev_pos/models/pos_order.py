# -*- coding: utf-8 -*-

from collections import defaultdict
from odoo import models, fields, api, _
from odoo.tools import float_compare
import logging
import re
import pytz

_logger = logging.getLogger(__name__)

class PosOrder(models.Model):
    _inherit = 'pos.order'

    # Fields
    vit_trxid = fields.Char(string='Transaction ID', tracking=True)
    vit_id = fields.Char(string='Document ID', tracking=True)
    is_integrated = fields.Boolean(string="Integrated", default=False, readonly=True, tracking=True)
    vit_pos_store = fields.Char(
        string='POS Store Location',
        readonly=True,
        help='Location source from delivery picking (complete name)'
    )
    
    gift_card_code = fields.Char(
        string='Gift Card Code',
        copy=False,
        readonly=True,
        help='Gift Card code generated for DP order'
    )

    def _export_for_ui(self, order):
        """
        ✅ FIXED: Override to handle None pos_reference which causes TypeError
        """
        timezone = pytz.timezone(self._context.get('tz') or self.env.user.tz or 'UTC')
        
        # ✅ FIX: Handle None pos_reference before regex search
        uid = ''
        if order.pos_reference:
            match = re.search('([0-9-]){14,}', order.pos_reference)
            uid = match.group(0) if match else ''
        
        return {
            'lines': [[0, 0, line] for line in order.lines.export_for_ui()],
            'statement_ids': [[0, 0, payment] for payment in order.payment_ids.export_for_ui()],
            'name': order.pos_reference or '',  # ✅ Handle None
            'uid': uid,  # ✅ Use safely extracted uid
            'amount_paid': order.amount_paid,
            'amount_total': order.amount_total,
            'amount_tax': order.amount_tax,
            'amount_return': order.amount_return,
            'pos_session_id': order.session_id.id,
            'pricelist_id': order.pricelist_id.id,
            'partner_id': order.partner_id.id,
            'user_id': order.user_id.id,
            'sequence_number': order.sequence_number,
            'date_order': str(order.date_order.astimezone(timezone)),
            'fiscal_position_id': order.fiscal_position_id.id,
            'to_invoice': order.to_invoice,
            'shipping_date': order.shipping_date,
            'state': order.state,
            'account_move': order.account_move.id,
            'id': order.id,
            'is_tipped': order.is_tipped,
            'tip_amount': order.tip_amount,
            'access_token': order.access_token,
            'ticket_code': order.ticket_code,
            'last_order_preparation_change': order.last_order_preparation_change,
            'tracking_number': order.tracking_number,
        }

    def confirm_coupon_programs(self, coupon_data):
        """
        ✅ FIXED: Gift card balance TIDAK DIBAGI - setiap card dapat nilai penuh
        ✅ FIXED: Simpan customer POS yang membeli gift card ke partner_id
        """
        _logger.info("="*80)
        _logger.info("🎁 START confirm_coupon_programs - ORDER: %s", self.name)
        _logger.info("🎁 Order ID: %s, Amount Total: %s, Amount Paid: %s", 
                    self.id, self.amount_total, self.amount_paid)
        
        # ✅ GET CUSTOMER FROM ORDER
        order_partner_id = self.partner_id.id if self.partner_id else False
        _logger.info("🎁 Order Customer (partner_id): %s - %s", 
                    order_partner_id, 
                    self.partner_id.name if self.partner_id else 'No Customer')
        
        # Helper function - MODIFIED to use order partner
        def get_partner_id(partner_id):
            """
            ✅ PRIORITY:
            1. Use partner_id from parameter if exists
            2. Use order partner_id
            3. Return False
            """
            if partner_id:
                partner = self.env['res.partner'].browse(partner_id).exists()
                if partner:
                    return partner_id
            
            # Fallback to order partner
            if order_partner_id:
                return order_partner_id
            
            return False
        
        # Convert keys to int
        coupon_data = {int(k): v for k, v in coupon_data.items()} if coupon_data else {}
        
        # Check existing loyalty cards
        self._check_existing_loyalty_cards(coupon_data)
        
        # Map coupon IDs
        coupon_new_id_map = {k: k for k in coupon_data.keys() if k > 0}
        
        # Create coupons
        coupons_to_create = {k: v for k, v in coupon_data.items() if k < 0 and not v.get('giftCardId')}
        
        _logger.info("🎁 Coupons to create: %s", len(coupons_to_create))
        
        # ============================================================
        # ✅ SOLUSI: AMBIL NILAI PENUH DARI ORDER LINE
        # ============================================================
        gift_card_lines = self.lines.filtered(
            lambda l: l.reward_id and l.reward_id.program_id.program_type == 'gift_card'
        )
        
        _logger.info("🎁 Gift card lines found: %s", len(gift_card_lines))
        
        # Buat list nilai gift card TANPA membagi dengan qty
        gift_card_amounts = []
        
        for line in gift_card_lines:
            # ✅ KUNCI: Gunakan price_subtotal_incl langsung TANPA dibagi qty
            line_amount = abs(line.price_subtotal_incl)
            
            _logger.info("🎁 Gift Card Line: %s", line.product_id.name)
            _logger.info("   Qty: %s", line.qty)
            _logger.info("   Price Unit: Rp. {:,.2f}".format(line.price_unit))
            _logger.info("   Subtotal (incl): Rp. {:,.2f}".format(line.price_subtotal_incl))
            _logger.info("   Amount per Card: Rp. {:,.2f} (TIDAK DIBAGI)".format(line_amount))
            
            # Setiap qty mendapat nilai penuh (tidak dibagi)
            for i in range(int(line.qty)):
                gift_card_amounts.append({
                    'program_id': line.reward_id.program_id.id,
                    'amount': line_amount,
                    'line_id': line.id,
                    'index': i + 1
                })
        
        _logger.info("🎁 Total gift card amounts: %s", len(gift_card_amounts))
        
        # ============================================================
        # ✅ BUAT COUPON DENGAN NILAI PENUH DAN CUSTOMER
        # ============================================================
        coupon_create_vals = []
        gift_card_index = 0
        
        for key, p in coupons_to_create.items():
            program_id = p.get('program_id')
            points = 0
            
            # ✅ Determine partner_id for this coupon
            coupon_partner_id = get_partner_id(p.get('partner_id', False))
            
            if program_id:
                program = self.env['loyalty.program'].browse(program_id)
                
                if program.program_type == 'gift_card':
                    # ✅ Ambil nilai dari mapping (NILAI PENUH)
                    if gift_card_index < len(gift_card_amounts):
                        matching_found = False
                        for idx in range(gift_card_index, len(gift_card_amounts)):
                            if gift_card_amounts[idx]['program_id'] == program_id:
                                points = gift_card_amounts[idx]['amount']
                                gift_card_index = idx + 1
                                matching_found = True
                                _logger.info("✅ Matched gift card #%s with program %s: Rp. {:,.2f}".format(points),
                                            idx + 1, program_id)
                                break
                        
                        if not matching_found:
                            _logger.warning("⚠️ No matching gift card found for program %s", program_id)
                            points = self.amount_paid
                    else:
                        _logger.warning("⚠️ Gift card index exceeded, using amount_paid")
                        points = self.amount_paid
                    
                    # Round to 2 decimal
                    points = round(points, 2)
                    
                    _logger.info("✅ Creating Gift Card:")
                    _logger.info("   Program: %s", program.name)
                    _logger.info("   Balance: Rp. {:,.2f} (NILAI PENUH)".format(points))
                    _logger.info("   Customer: %s (ID: %s)", 
                                self.env['res.partner'].browse(coupon_partner_id).name if coupon_partner_id else 'No Customer',
                                coupon_partner_id)
            
            coupon_create_vals.append({
                'program_id': program_id,
                'partner_id': coupon_partner_id,  # ✅ SET CUSTOMER
                'code': p.get('barcode') or self.env['loyalty.card']._generate_code(),
                'points': points,
                'expiration_date': p.get('date_to', False),
                'source_pos_order_id': self.id,
            })
        
        _logger.info("🎁 Creating %s coupons with full values and customers", len(coupon_create_vals))
        
        # ============================================================
        # CREATE COUPONS
        # ============================================================
        new_coupons = self.env['loyalty.card'].with_context(action_no_send_mail=True).sudo().create(coupon_create_vals)
        
        _logger.info("="*80)
        _logger.info("✅ CREATED %s GIFT CARDS WITH FULL VALUES AND CUSTOMERS:", len(new_coupons))
        _logger.info("="*80)
        for idx, coupon in enumerate(new_coupons, 1):
            _logger.info("   %s. Code: %s | Balance: Rp. {:,.2f} | Customer: %s".format(coupon.points), 
                        idx, coupon.code, coupon.partner_id.name if coupon.partner_id else 'No Customer')
        
        # ============================================================
        # SAVE GIFT CARD CODE
        # ============================================================
        gift_card_codes = []
        gift_card_code_str = ''
        
        for coupon in new_coupons:
            if coupon.program_id.program_type == 'gift_card':
                gift_card_codes.append(coupon.code)
        
        if gift_card_codes:
            gift_card_code_str = ', '.join(gift_card_codes)
            
            # Direct SQL update
            self.env.cr.execute(
                "UPDATE pos_order SET gift_card_code = %s WHERE id = %s",
                (gift_card_code_str, self.id)
            )
            self.env.cr.commit()
            
            # Update cache
            self.invalidate_recordset(['gift_card_code'])
            
            _logger.info("✅ Gift card codes saved: %s", gift_card_code_str)
        
        # ============================================================
        # UPDATE EXISTING GIFT CARDS - ✅ INCLUDE PARTNER_ID
        # ============================================================
        gift_cards_to_update = [v for v in coupon_data.values() if v.get('giftCardId')]
        updated_gift_cards = self.env['loyalty.card']
        
        for coupon_vals in gift_cards_to_update:
            gift_card = self.env['loyalty.card'].browse(coupon_vals.get('giftCardId'))
            
            # ✅ Update partner_id juga untuk existing gift cards
            update_vals = {
                'points': coupon_vals['points'],
                'source_pos_order_id': self.id,
                'partner_id': get_partner_id(coupon_vals.get('partner_id', False)),
            }
            
            gift_card.write(update_vals)
            updated_gift_cards |= gift_card
            
            _logger.info("✅ Updated existing gift card: %s | Customer: %s", 
                        gift_card.code, 
                        gift_card.partner_id.name if gift_card.partner_id else 'No Customer')
        
        # ============================================================
        # MAP NEW COUPONS
        # ============================================================
        for old_id, new_id in zip(coupons_to_create.keys(), new_coupons):
            coupon_new_id_map[new_id.id] = old_id
        
        # Process all coupons
        all_coupons = self.env['loyalty.card'].sudo().browse(coupon_new_id_map.keys()).exists()
        
        # Link to order lines
        lines_per_reward_code = defaultdict(lambda: self.env['pos.order.line'])
        for line in self.lines:
            if not line.reward_identifier_code:
                continue
            lines_per_reward_code[line.reward_identifier_code] |= line
        
        for coupon in all_coupons:
            if coupon.id in coupon_new_id_map:
                old_id = coupon_new_id_map[coupon.id]
                is_newly_created = old_id < 0
                is_gift_card = coupon.program_id.program_type == 'gift_card'
                
                # ✅ PENTING: Jangan tambahkan points untuk gift card yang baru dibuat
                if not (is_newly_created and is_gift_card):
                    coupon.points += coupon_data[old_id]['points']
            
            for reward_code in coupon_data[coupon_new_id_map[coupon.id]].get('line_codes', []):
                lines_per_reward_code[reward_code].coupon_id = coupon
        
        # Send emails
        new_coupons.with_context(action_no_send_mail=False)._send_creation_communication()
        
        # Prepare reports
        report_per_program = {}
        coupon_per_report = defaultdict(list)
        
        for coupon in new_coupons | updated_gift_cards:
            if coupon.program_id not in report_per_program:
                report_per_program[coupon.program_id] = coupon.program_id.communication_plan_ids.\
                    filtered(lambda c: c.trigger == 'create').pos_report_print_id
            for report in report_per_program[coupon.program_id]:
                coupon_per_report[report.id].append(coupon.id)
        
        # ============================================================
        # PREPARE RESPONSE
        # ============================================================
        result = {
            'coupon_updates': [{
                'old_id': coupon_new_id_map[coupon.id],
                'id': coupon.id,
                'points': coupon.points,
                'code': coupon.code,
                'program_id': coupon.program_id.id,
                'partner_id': coupon.partner_id.id,
            } for coupon in all_coupons if coupon.program_id.is_nominative],
            'program_updates': [{
                'program_id': program.id,
                'usages': program.total_order_count,
            } for program in all_coupons.program_id],
            'new_coupon_info': [{
                'program_name': coupon.program_id.name,
                'expiration_date': coupon.expiration_date,
                'code': coupon.code,
                'balance': coupon.points,
            } for coupon in new_coupons if (
                coupon.program_id.applies_on == 'future'
                and coupon.program_id.program_type not in ['gift_card', 'ewallet']
            )],
            'coupon_report': coupon_per_report,
            'gift_card_code': gift_card_code_str if gift_card_codes else '',
        }
        
        _logger.info("="*80)
        _logger.info("✅ confirm_coupon_programs COMPLETED - ALL GIFT CARDS WITH CUSTOMERS")
        _logger.info("="*80)
        
        return result

    # ============================================================
    # ✅ METHOD UNTUK FIX GIFT CARD YANG SUDAH TERLANJUR SALAH
    # ============================================================
    def fix_existing_gift_cards(self):
        """
        Method untuk memperbaiki gift card yang sudah terlanjur dibuat dengan nilai yang salah
        """
        _logger.info("="*80)
        _logger.info("🔧 FIXING EXISTING GIFT CARDS WITH WRONG BALANCE")
        _logger.info("="*80)
        
        fixed_count = 0
        
        for order in self:
            _logger.info("📋 Processing Order: %s (ID: %s)", order.name, order.id)
            
            # Find gift card lines
            gift_card_lines = order.lines.filtered(
                lambda l: l.reward_id and l.reward_id.program_id.program_type == 'gift_card'
            )
            
            if not gift_card_lines:
                _logger.info("   ⚠️ No gift card lines found")
                continue
            
            # Get the FULL amount (tidak dibagi)
            correct_amounts = []
            for line in gift_card_lines:
                line_amount = abs(line.price_subtotal_incl)
                _logger.info("   Gift Card Line: %s | Qty: %s | Amount: Rp. {:,.2f}".format(line_amount),
                            line.product_id.name, line.qty)
                
                # Setiap qty mendapat nilai penuh
                for i in range(int(line.qty)):
                    correct_amounts.append(line_amount)
            
            # Find loyalty cards
            loyalty_cards = self.env['loyalty.card'].search([
                ('source_pos_order_id', '=', order.id),
                ('program_id.program_type', '=', 'gift_card')
            ], order='id asc')
            
            if not loyalty_cards:
                _logger.info("   ⚠️ No loyalty cards found")
                continue
            
            _logger.info("   Found %s loyalty cards", len(loyalty_cards))
            
            # Update each card dengan nilai penuh
            for idx, card in enumerate(loyalty_cards):
                if idx < len(correct_amounts):
                    correct_balance = round(correct_amounts[idx], 2)
                    current_balance = card.points
                    
                    if abs(current_balance - correct_balance) > 0.01:  # Ada perbedaan
                        _logger.info("   🔧 Fixing Card: %s", card.code)
                        _logger.info("      Old Balance: Rp. {:,.2f}".format(current_balance))
                        _logger.info("      New Balance: Rp. {:,.2f}".format(correct_balance))
                        
                        card.write({'points': correct_balance})
                        fixed_count += 1
                    else:
                        _logger.info("   ✅ Card %s already correct: Rp. {:,.2f}".format(current_balance), card.code)
        
        _logger.info("="*80)
        _logger.info("✅ FIXED %s GIFT CARDS", fixed_count)
        _logger.info("="*80)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Gift Card Fixed',
                'message': f'Successfully fixed {fixed_count} gift cards',
                'type': 'success',
                'sticky': False,
            }
        }

    def debug_gift_card_calculation(self):
        """
        Method untuk debug perhitungan gift card
        """
        _logger.info("="*80)
        _logger.info("🔍 DEBUG GIFT CARD CALCULATION")
        _logger.info("="*80)
        
        for order in self:
            _logger.info("📋 Order: %s (ID: %s)", order.name, order.id)
            _logger.info("   Amount Total: Rp. {:,.2f}".format(order.amount_total))
            _logger.info("   Amount Paid: Rp. {:,.2f}".format(order.amount_paid))
            
            # Check order lines
            gift_card_lines = order.lines.filtered(
                lambda l: l.reward_id and l.reward_id.program_id.program_type == 'gift_card'
            )
            
            _logger.info("   " + "="*60)
            _logger.info("   GIFT CARD LINES:")
            _logger.info("   " + "="*60)
            
            for idx, line in enumerate(gift_card_lines, 1):
                _logger.info("   %s. Product: %s", idx, line.product_id.name)
                _logger.info("      Qty: %s", line.qty)
                _logger.info("      Price Unit: Rp. {:,.2f}".format(line.price_unit))
                _logger.info("      Subtotal (excl): Rp. {:,.2f}".format(line.price_subtotal))
                _logger.info("      Subtotal (incl): Rp. {:,.2f}".format(line.price_subtotal_incl))
                _logger.info("      ✅ CORRECT VALUE (FULL): Rp. {:,.2f}".format(abs(line.price_subtotal_incl)))
                _logger.info("      ❌ WRONG if divided: Rp. {:,.2f}".format(
                    abs(line.price_subtotal_incl) / line.qty if line.qty > 0 else 0))
            
            # Check loyalty cards
            loyalty_cards = self.env['loyalty.card'].search([
                ('source_pos_order_id', '=', order.id),
                ('program_id.program_type', '=', 'gift_card')
            ], order='id asc')
            
            _logger.info("   " + "="*60)
            _logger.info("   LOYALTY CARDS CREATED:")
            _logger.info("   " + "="*60)
            
            for idx, card in enumerate(loyalty_cards, 1):
                _logger.info("   %s. Code: %s", idx, card.code)
                _logger.info("      Program: %s", card.program_id.name)
                _logger.info("      Balance: Rp. {:,.2f}".format(card.points))
        
        _logger.info("="*80)
        return True