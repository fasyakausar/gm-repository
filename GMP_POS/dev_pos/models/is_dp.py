# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
import pytz


class AccountMove(models.Model):
    _inherit = 'account.move'
    
    gm_is_dp = fields.Boolean(
        string='Contains DP Product', 
        default=False,
        readonly=True,
        help='Invoice ini mengandung produk Down Payment'
    )


def _prepare_invoice_vals(self):
        """
        Override method untuk menambahkan pengecekan produk DP
        dan membawa vit_pos_store ke invoice
        """
        self.ensure_one()
        timezone = pytz.timezone(self._context.get('tz') or self.env.user.tz or 'UTC')
        invoice_date = fields.Datetime.now() if self.session_id.state == 'closed' else self.date_order
        pos_refunded_invoice_ids = []
        
        for orderline in self.lines:
            if orderline.refunded_orderline_id and orderline.refunded_orderline_id.order_id.account_move:
                pos_refunded_invoice_ids.append(orderline.refunded_orderline_id.order_id.account_move.id)
        
        # Cek apakah ada product dengan gm_is_dp = True
        has_dp_product = any(line.product_id.gm_is_dp for line in self.lines)
        
        vals = {
            'invoice_origin': self.name,
            'pos_refunded_invoice_ids': pos_refunded_invoice_ids,
            'journal_id': self.session_id.config_id.invoice_journal_id.id,
            'move_type': 'out_invoice' if self.amount_total >= 0 else 'out_refund',
            'ref': self.name,
            'partner_id': self.partner_id.address_get(['invoice'])['invoice'],
            'partner_shipping_id': self.partner_id.address_get(['delivery'])['delivery'],
            'partner_bank_id': self._get_partner_bank_id(),
            'currency_id': self.currency_id.id,
            'invoice_user_id': self.user_id.id,
            'invoice_date': invoice_date.astimezone(timezone).date(),
            'fiscal_position_id': self.fiscal_position_id.id,
            'invoice_line_ids': self._prepare_invoice_lines(),
            'invoice_payment_term_id': False,
            'invoice_cash_rounding_id': self.config_id.rounding_method.id
            if self.config_id.cash_rounding and (not self.config_id.only_round_cash_method or any(p.payment_method_id.is_cash_count for p in self.payment_ids))
            else False,
            'gm_is_dp': has_dp_product,  # Set flag gm_is_dp pada invoice
            'vit_pos_store': self.vit_pos_store if hasattr(self, 'vit_pos_store') else False,  # Bawa vit_pos_store ke invoice
        }
        
        if self.refunded_order_ids.account_move:
            vals['ref'] = _('Reversal of: %s', self.refunded_order_ids.account_move.name)
            vals['reversed_entry_id'] = self.refunded_order_ids.account_move.id
        
        if self.note:
            vals.update({'narration': self.note})
        
        return vals