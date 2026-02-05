# 1. Standard Python libraries
from datetime import datetime
import base64
import io
import xlsxwriter
# 2. Odoo core
from odoo import models, fields, _, api
from odoo.exceptions import UserError, ValidationError
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
# 3. Odoo addons

class PosOrder(models.Model):
    _inherit = 'pos.order'
    
    def get_dp_code(self):
        """Get DP Code / Gift Card Code from order"""
        self.ensure_one()
        
        # Cek gift_card_code langsung
        if hasattr(self, 'gift_card_code') and self.gift_card_code:
            return self.gift_card_code
        
        # Cek loyalty card
        if hasattr(self, 'loyalty_card_id') and self.loyalty_card_id and self.loyalty_card_id.code:
            return self.loyalty_card_id.code
        
        # Cek loyalty history
        if hasattr(self, 'loyalty_history_ids') and self.loyalty_history_ids:
            for history in self.loyalty_history_ids:
                if history.card_id and history.card_id.code:
                    return history.card_id.code
        
        # Cek coupon
        if hasattr(self, 'coupon_ids') and self.coupon_ids:
            for coupon in self.coupon_ids:
                if coupon.code:
                    return coupon.code
        
        return '-'

class SalesReportDetail(models.TransientModel):
    _name = 'sales.report'
    _description = 'Sales Report'

    vit_date_from = fields.Date(string='Date From')
    vit_date_to = fields.Date(string='Date To')
    vit_invoice_no = fields.Char(string='Invoice No.')
    vit_pos_order_ref = fields.Char(string='POS Order No.')
    vit_counting_no = fields.Char(string='Counting No.')
    
    vit_customer_name_id = fields.Many2one('res.partner', string='Customer Name')
  
# [{'id': 17, 'name': 'S01/0016', 'date_order': datetime.datetime(2025, 6, 17, 7, 45, 20), 'user_id': (2, 'Administrator'), 'amount_difference': 0.0, 'amount_tax': 0.0, 'amount_total': 0.0, 'amount_paid': 0.0, 'amount_return': 0.0, 'margin': 0.0, 'margin_percent': 0.0, 'is_total_cost_computed': True, 'lines': [31, 32], 'company_id': (1, 'Visi-Intech'), 'country_code': 'ID', 'pricelist_id': False, 'partner_id': (10, 'Astri Ririn'), 'sequence_number': 14, 'session_id': (5, 'POS/00003'), 'config_id': (1, 'S01'), 'currency_id': (12, 'IDR'), 'currency_rate': 1.0, 'state': 'paid', 'account_move': False, 'picking_ids': [79], 'picking_count': 1, 'failed_pickings': False, 'picking_type_id': (9, 'Store 01: PoS Orders'), 'procurement_group_id': False, 'floating_order_name': False, 'general_note': '', 'nb_print': 0, 'pos_reference': 'Order 00005-008-0014', 'sale_journal': (12, 'Point of Sale'), 'fiscal_position_id': False, 'payment_ids': [], 'session_move_id': False, 'to_invoice': False, 'shipping_date': False, 'is_invoiced': False, 'is_tipped': False, 'tip_amount': 0.0, 'refund_orders_count': 0, 'refunded_order_id': False, 'has_refundable_lines': True, 'ticket_code': 'k7my0', 'tracking_number': '514', 'uuid': 'f123d9f8-3721-40f3-9d18-dd3132506887', 'email': 'ririn.e@visi-intech.com', 'mobile': False, 'is_edited': False, 'has_deleted_line': False, 'order_edit_tracking': False, 'available_payment_method_ids': [2, 3, 1], 'display_name': 'S01/0016', 'create_uid': (2, 'Administrator'), 'create_date': datetime.datetime(2025, 6, 17, 7, 45, 22, 29417), 'write_uid': (2, 'Administrator'), 'write_date': datetime.datetime(2025, 6, 17, 7, 45, 22, 29417), 'l10n_id_qris_transaction_ids': [], 'employee_id': False, 'cashier': 'Administrator', 'online_payment_method_id': False, 'next_online_payment_amount': 0.0, 'table_id': False, 'customer_count': 0, 'takeaway': False, 'crm_team_id': False, 'sale_order_count': 0, 'table_stand_number': False, 'use_self_order_online_payment': False}]
    
    def action_generate_report_detail(self):
        # self.ensure_one() # umumnya dipakai dari form view karena memastikan hanya mengambil 1 record
        date_from = self.vit_date_from or False
        date_to = self.vit_date_to or False
        invoice_no = self.vit_invoice_no or False
        pos_order_ref = self.vit_pos_order_ref or False

        if not date_from or not date_to:
            raise UserError("Tidak dapat menampilkan report. Mohon pilih Date From dan Date To")

        account_move = self.env['account.move'].search([('name', '=', invoice_no)], limit=1)

        domain = []
        if date_from:
            domain.append(('date_order', '>=', date_from))
        if date_to:
            domain.append(('date_order', '<=', date_to))
        if account_move:
            domain.append(('account_move', '=', account_move.id))
        if pos_order_ref:
            domain.append(('name', '=', pos_order_ref))

        orders = self.env['pos.order'].search(domain)

        if not orders:
            raise UserError("Tidak ada data POS di periode tersebut.")

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet()
        header_format = self.get_header_format(workbook)

        tanggal_dari = self.vit_date_from.strftime("%d/%m/%Y") if self.vit_date_from else ''
        tanggal_sampai = self.vit_date_to.strftime("%d/%m/%Y") if self.vit_date_to else ''
        tanggal_cetak = fields.Date.today().strftime("%d %b %Y")

        # Header laporan
        worksheet.write(0, 0, "Laporan Penjualan")
        worksheet.write(1, 0, "[ {} - {} ]".format(tanggal_dari, tanggal_sampai))
        worksheet.write(2, 0, "Dicetak Tanggal {}".format(tanggal_cetak))

        header = [
            'User', 'Kasir', 'Customer Code', 'Customer Name', 'Kode Currency', 'Kode Store','Nama Store',
            'Invoice No.', 'Order No.', 'Session', 'No Retur', 'No HP', 'Tanggal', 'Tanggal Jatuh Tempo',
            'Sub Divisi', 'Item Kelas', 'Item Tipe',
            'Item Code', 'Nama Item', 'POS Category', 'Satuan', 'Quantity',
            'Harga', 'Disc', 'Taxes', 'Sub Total', 'Sub Total Nett'
        ]

        for col, title in enumerate(header):
            worksheet.write(4, col, title, header_format)

        row = 5
        for order in orders:
            local_date_order = fields.Datetime.context_timestamp(self, order.date_order)
            for order_line in order.lines:
                worksheet.write(row, 0, order.user_id.name or '')
                worksheet.write(row, 1, order.employee_id.name or '')
                worksheet.write(row, 2, order.partner_id.customer_code or '')
                worksheet.write(row, 3, order.partner_id.name or '')
                worksheet.write(row, 4, order.currency_id.name or '')
                worksheet.write(row, 5, order.config_id.name or '')
                worksheet.write(row, 6, order.config_id.name or '')
                worksheet.write(row, 7, order.account_move.name or '')
                worksheet.write(row, 8, order.name or '')
                worksheet.write(row, 9, order.session_id.name or '')
                worksheet.write(row, 10, order.name if 'REFUND' in order.name.upper() else '')
                worksheet.write(row, 11, order.partner_id.mobile or '')
                worksheet.write(row, 12, local_date_order.strftime('%d/%m/%Y %H:%M:%S'))
                worksheet.write(row, 13, local_date_order.strftime('%d/%m/%Y %H:%M:%S'))
                
                worksheet.write(row, 14, order_line.product_id.vit_sub_div or '')
                worksheet.write(row, 15, order_line.product_id.vit_item_kel or '')
                worksheet.write(row, 16, order_line.product_id.vit_item_type or '')

                worksheet.write(row, 17, order_line.product_id.default_code or '')
                worksheet.write(row, 18, order_line.product_id.name or '')
                worksheet.write(row, 19, order_line.product_id.product_tmpl_id.pos_categ_ids[0].name if order_line.product_id.product_tmpl_id.pos_categ_ids else '')
                worksheet.write(row, 20, order_line.product_uom_id.name or '')
                worksheet.write(row, 21, order_line.qty)
                worksheet.write(row, 22, self.format_number(order_line.price_unit) if order_line.price_unit else '')
                worksheet.write(row, 23, order_line.discount or 0)
                worksheet.write(row, 24, ", ".join(order_line.tax_ids_after_fiscal_position.mapped('name')) or '')
                worksheet.write(row, 25, self.format_number(order_line.price_subtotal) if order_line.price_subtotal else '')
                worksheet.write(row, 26, self.format_number(order_line.price_subtotal_incl) if order_line.price_subtotal_incl else '')
                row += 1

        workbook.close()
        xlsx_data = output.getvalue()
        output.close()

        attachment = self.env['ir.attachment'].create({
            'name': 'Sales_Report_Detail.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(xlsx_data),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        })

        download_url = '/web/content/%s?download=true' % attachment.id
        return {
            'type': 'ir.actions.act_url',
            'url': download_url,
            'target': 'new',
        }

    def action_generate_report_recap(self):
        # self.ensure_one()
        date_from = self.vit_date_from or False
        date_to = self.vit_date_to or False
        invoice_no = self.vit_invoice_no or False
        pos_order_ref = self.vit_pos_order_ref or False

        if not date_from or not date_to:
            raise UserError("Tidak dapat menampilkan report. Mohon pilih Date From dan Date To")

        account_move = self.env['account.move'].search([('name', '=', invoice_no)], limit=1)

        domain = []
        if date_from:
            domain.append(('date_order', '>=', date_from))
        if date_to:
            domain.append(('date_order', '<=', date_to))
        if account_move:
            domain.append(('account_move', '=', account_move.id))
        if pos_order_ref:
            domain.append(('name', '=', pos_order_ref))

        orders = self.env['pos.order'].search(domain)

        if not orders:
            raise UserError("Tidak ada data POS di periode tersebut.")

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet()
        header_format = self.get_header_format(workbook)

        tanggal_dari = self.vit_date_from.strftime("%d/%m/%Y") if self.vit_date_from else ''
        tanggal_sampai = self.vit_date_to.strftime("%d/%m/%Y") if self.vit_date_to else ''
        tanggal_cetak = fields.Date.today().strftime("%d %b %Y")

        # Header laporan
        worksheet.write(0, 0, "Laporan Penjualan")
        worksheet.write(1, 0, "[ {} - {} ]".format(tanggal_dari, tanggal_sampai))
        worksheet.write(2, 0, "Dicetak Tanggal {}".format(tanggal_cetak))

        # Updated header with DP Code column
        header = [
            'User', 'Kasir', 'Customer Code', 'Customer Name', 'Kode Currency', 'Kode Store','Nama Store',
            'Invoice No.', 'Order No.', 'Session', 'No Retur', 'No HP', 'Tanggal', 'Tanggal Jatuh Tempo',
            'DP Code',  # New column added here
            'Total Quantity', 'Total Bersih'
        ]

        for col, title in enumerate(header):
            worksheet.write(4, col, title, header_format)

        row = 5
        for order in orders:
            total_qty = sum(order.lines.mapped('qty'))
            total_bersih = sum(order.lines.mapped('price_subtotal_incl'))
            local_date_order = fields.Datetime.context_timestamp(self, order.date_order)
            
            # Get DP Code / gift_card_code
            dp_code = ''
            # Option 1: If gift_card_code is a direct field on pos.order
            if hasattr(order, 'gift_card_code'):
                dp_code = order.gift_card_code or ''
            # Option 2: If it's related to loyalty card
            elif hasattr(order, 'loyalty_card_id') and order.loyalty_card_id:
                dp_code = order.loyalty_card_id.code or ''
            # Option 3: If it's from loyalty history
            elif hasattr(order, 'loyalty_history_ids') and order.loyalty_history_ids:
                # Get the first loyalty history record's card code
                loyalty_history = order.loyalty_history_ids.filtered(lambda l: l.card_id)
                if loyalty_history:
                    dp_code = loyalty_history[0].card_id.code or ''
            
            worksheet.write(row, 0, order.user_id.name or '')
            worksheet.write(row, 1, order.employee_id.name or '')
            worksheet.write(row, 2, order.partner_id.customer_code or '')
            worksheet.write(row, 3, order.partner_id.name or '')
            worksheet.write(row, 4, order.currency_id.name or '')
            worksheet.write(row, 5, order.config_id.name or '')
            worksheet.write(row, 6, order.config_id.name or '')
            worksheet.write(row, 7, order.account_move.name or '')
            worksheet.write(row, 8, order.name or '')
            worksheet.write(row, 9, order.session_id.name or '')
            worksheet.write(row, 10, order.name if 'REFUND' in order.name.upper() else '')
            worksheet.write(row, 11, order.partner_id.mobile or '')
            worksheet.write(row, 12, local_date_order.strftime('%d/%m/%Y %H:%M:%S'))
            worksheet.write(row, 13, local_date_order.strftime('%d/%m/%Y %H:%M:%S'))
            worksheet.write(row, 14, dp_code)  # DP Code column
            worksheet.write(row, 15, total_qty or '')
            worksheet.write(row, 16, self.format_number(total_bersih) if total_bersih else '')
            row += 1

        workbook.close()
        xlsx_data = output.getvalue()
        output.close()

        attachment = self.env['ir.attachment'].create({
            'name': 'Sales_Report_Recap.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(xlsx_data),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        })

        download_url = '/web/content/%s?download=true' % attachment.id
        return {
            'type': 'ir.actions.act_url',
            'url': download_url,
            'target': 'new',
        }

    def action_generate_report_spending(self):
        # self.ensure_one()
        date_from = self.vit_date_from or False
        date_to = self.vit_date_to or False
        # invoice_no = self.vit_invoice_no or False
        # pos_order_ref = self.vit_pos_order_ref or False

        if not date_from or not date_to:
            raise UserError("Tidak dapat menampilkan report. Mohon pilih Date From dan Date To")

        # account_move = self.env['account.move'].search([('name', '=', invoice_no)], limit=1)

        domain = []
        if date_from:
            domain.append(('date_order', '>=', date_from))
        if date_to:
            domain.append(('date_order', '<=', date_to))
        # if account_move:
        #     domain.append(('account_move', '=', account_move.id))
        # if pos_order_ref:
        #     domain.append(('name', '=', pos_order_ref))

        orders = self.env['pos.order'].search(domain)

        if not orders:
            raise UserError("Tidak ada data POS di periode tersebut.")

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet()
        header_format = self.get_header_format(workbook)

        tanggal_dari = self.vit_date_from.strftime("%d/%m/%Y") if self.vit_date_from else ''
        tanggal_sampai = self.vit_date_to.strftime("%d/%m/%Y") if self.vit_date_to else ''
        tanggal_cetak = fields.Date.today().strftime("%d %b %Y")

        # Header laporan
        worksheet.write(0, 0, "Laporan History Penjualan")
        worksheet.write(1, 0, "[ {} - {} ]".format(tanggal_dari, tanggal_sampai))
        worksheet.write(2, 0, "Dicetak Tanggal {}".format(tanggal_cetak))
        
        range_spending = [
            (0, 50000, "0 - 50.000"),
            (50001, 100000, "50.001 - 100.000"),
            (100001, 250000, "100.001 - 250.000"),
            (250001, 500000, "250.001 - 500.000"),
            (500001, 1000000, "500.001 - 1.000.000"),
            (1000001, 3000000, "1.000.001 - 3.000.000"),
            (3000001, 5000000, "3.000.001 - 5.000.000"),
            (5000001, 20000000, "5.000.001 - 20.000.000"),
            (20000001, float('inf'), ">20.000.001"),
        ]
        
        tanggal_set = set(fields.Datetime.context_timestamp(self, order.date_order).date() for order in orders)
        tanggal_list = sorted(list(tanggal_set))
        
        header = ["Nomor", "Nama"]
        for tgl in tanggal_list:
            header += [f"Qty-{tgl.strftime('%d/%m/%Y')}", f"Trx-{tgl.strftime('%d/%m/%Y')}", f"Sales-{tgl.strftime('%d/%m/%Y')}"]

        for col, title in enumerate(header):
            worksheet.write(4, col, title, header_format)

        row = 5
        for idx, (min_spending, max_spending, label) in enumerate(range_spending, 1):
            worksheet.write(row, 0, idx)
            worksheet.write(row, 1, label)

            col = 2
            for tgl in tanggal_list:
                order_filtered = orders.filtered(lambda o: fields.Datetime.context_timestamp(self, o.date_order).date() == tgl and min_spending <= o.amount_total <= max_spending)

                total_qty = sum(order_filtered.mapped(lambda o: sum(o.lines.mapped('qty'))))
                total_trx = len(order_filtered)
                total_sales = sum(order_filtered.mapped('amount_total'))

                worksheet.write(row, col, total_qty or '')
                worksheet.write(row, col + 1, total_trx or '')
                worksheet.write(row, col + 2, self.format_number(total_sales) if total_sales else '')

                col += 3
            row += 1

        workbook.close()
        xlsx_data = output.getvalue()
        output.close()

        attachment = self.env['ir.attachment'].create({
            'name': 'Sales_Report_Spending.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(xlsx_data),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        })

        download_url = '/web/content/%s?download=true' % attachment.id
        return {
            'type': 'ir.actions.act_url',
            'url': download_url,
            'target': 'new',
        }
    
    def action_generate_report_hourly(self):
        # self.ensure_one()
        date_from = self.vit_date_from or False
        date_to = self.vit_date_to or False
        # invoice_no = self.vit_invoice_no or False
        # pos_order_ref = self.vit_pos_order_ref or False

        if not date_from or not date_to:
            raise UserError("Tidak dapat menampilkan report. Mohon pilih Date From dan Date To")

        # account_move = self.env['account.move'].search([('name', '=', invoice_no)], limit=1)

        domain = []
        if date_from:
            domain.append(('date_order', '>=', date_from))
        if date_to:
            domain.append(('date_order', '<=', date_to))
        # if account_move:
        #     domain.append(('account_move', '=', account_move.id))
        # if pos_order_ref:
        #     domain.append(('name', '=', pos_order_ref))

        orders = self.env['pos.order'].search(domain)

        if not orders:
            raise UserError("Tidak ada data POS di periode tersebut.")

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet()
        header_format = self.get_header_format(workbook)

        tanggal_dari = self.vit_date_from.strftime("%d/%m/%Y") if self.vit_date_from else ''
        tanggal_sampai = self.vit_date_to.strftime("%d/%m/%Y") if self.vit_date_to else ''
        tanggal_cetak = fields.Date.today().strftime("%d %b %Y")

        # Header laporan
        worksheet.write(0, 0, "Laporan History Penjualan")
        worksheet.write(1, 0, "[{} - {}]".format(tanggal_dari, tanggal_sampai))
        worksheet.write(2, 0, "Dicetak Tanggal {}".format(tanggal_cetak))

        # Ambil semua tanggal unik dalam order
        tanggal_set = set(fields.Datetime.context_timestamp(self, order.date_order).date() for order in orders)
        tanggal_list = sorted(list(tanggal_set))

        # Buat header kolom
        headers = ["Jam"]
        for tgl in tanggal_list:
            tgl_str = tgl.strftime('%d/%m/%Y')
            headers += [f"Qty-{tgl_str}", f"Trx-{tgl_str}", f"Sales-{tgl_str}"]

        for col, title in enumerate(headers):
            worksheet.write(4, col, title, header_format)

        row = 5
        for hour in range(24):
            worksheet.write(row, 0, f"{hour:02d}")

            col = 1
            for tgl in tanggal_list:
                order_filtered = orders.filtered(lambda o: fields.Datetime.context_timestamp(self, o.date_order).date() == tgl and fields.Datetime.context_timestamp(self, o.date_order).hour == hour)

                total_qty = sum(order_filtered.mapped(lambda o: sum(o.lines.mapped('qty'))))
                total_trx = len(order_filtered)
                total_sales = sum(order_filtered.mapped('amount_total'))

                worksheet.write(row, col, total_qty or '0')
                worksheet.write(row, col + 1, total_trx or '0')
                worksheet.write(row, col + 2, self.format_number(total_sales) if total_sales else '0')

                col += 3
            row += 1

        workbook.close()
        xlsx_data = output.getvalue()
        output.close()

        attachment = self.env['ir.attachment'].create({
            'name': 'Sales_Report_Hourly.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(xlsx_data),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        })

        download_url = '/web/content/%s?download=true' % attachment.id
        return {
            'type': 'ir.actions.act_url',
            'url': download_url,
            'target': 'new',
        }
        
    def action_generate_sales_report_loyalty_customer(self):
        # self.ensure_one()
        customer = self.vit_customer_name_id or False # res.partner(2721,)
        domain = [('program_type', '=', 'loyalty')]
        if customer:
            domain = [('partner_id', 'in', customer.ids), ('program_type', '=', 'loyalty')]
            cust_code = customer.customer_code
            cust_name = customer.name

        loyalty_card = self.env['loyalty.card'].search(domain)
        if not loyalty_card:
            raise UserError("Tidak ada data Loyalty pada customer tersebut.")
        loyalty_card = loyalty_card.sorted(key=lambda c: c.partner_id.name or '')
        
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet()
        header_format = self.get_header_format(workbook)

        tanggal_cetak = fields.Date.today().strftime("%d %b %Y")

        # Header laporan
        worksheet.write(0, 0, "Laporan Loyalty Customer")
        worksheet.write(1, 0, f"[{cust_code} - {cust_name}]" if customer else 'All')
        worksheet.write(2, 0, "Dicetak Tanggal {}".format(tanggal_cetak))

        header = [
            'Kode', 'Nama', 'Telepon', 'Program Name', 'Point Akhir'
        ]
        
        for col, title in enumerate(header):
            worksheet.write(4, col, title, header_format)

        row = 5
        for order in loyalty_card:
            worksheet.write(row, 0, order.partner_id.customer_code or '')
            worksheet.write(row, 1, order.partner_id.name or '')
            worksheet.write(row, 2, order.partner_id.mobile or '')
            worksheet.write(row, 3, order.partner_id.name or '')
            worksheet.write(row, 4, self.format_number(order.points) if order.points else '0')
            row += 1

        workbook.close()
        xlsx_data = output.getvalue()
        output.close()

        attachment = self.env['ir.attachment'].create({
            'name': 'Report_Loyalty_Customer.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(xlsx_data),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        })

        download_url = '/web/content/%s?download=true' % attachment.id
        return {
            'type': 'ir.actions.act_url',
            'url': download_url,
            'target': 'new',
        }
        
    def action_generate_sales_report_history_loyalty_customer(self):
        # self.ensure_one()
        customer = self.vit_customer_name_id or False # res.partner(2721,)
        if not customer:
            raise UserError("Tidak ada Customer yang dipilih.")
        
        loyalty = self.env['loyalty.card'].search([('partner_id', 'in', customer.ids), ('program_type', '=', 'loyalty')]) # loyalty.card(130,)
        loyalty_history = self.env['loyalty.history'].search([('card_id', 'in', loyalty.ids)], order='id desc') # loyalty.card(130,)
        
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet()
        header_format = self.get_header_format(workbook)
        
        cust_code = customer.customer_code or ''
        cust_name = customer.name or ''
        cust_phone = customer.mobile or ''
        tanggal_cetak = fields.Date.today().strftime("%d %b %Y")
        # printed_data = set()

        # Header laporan
        worksheet.write(0, 0, "Laporan History Loyalty Customer")
        worksheet.write(1, 0, f"[{cust_code} - {cust_name} - {cust_phone}]")
        worksheet.write(2, 0, "Dicetak Tanggal {}".format(tanggal_cetak))

        header = [
            'Kode', 'Nama', 'Program Name', 'Tanggal', 'Invoice No.', 'Order No.', 'Session',
            'Kode Store', 'Masuk', 'Keluar', 'Akhir'
        ]
        
        for col, title in enumerate(header):
            worksheet.write(4, col, title, header_format)

        row = 5
        for order in loyalty_history:
            date_order = order.pos_order_id.date_order
            local_date_order = ''
            if date_order:
                if isinstance(date_order, str):
                    date_order = fields.Datetime.from_string(date_order)
                if isinstance(date_order, datetime):
                    local_date_order = date_order.strftime('%d/%m/%Y %H:%M:%S')
            
            # key = (order.card_id.id, order.points_before, order.points_after)
            # if key in printed_data:
            #     continue  # Skip data duplikat
            # printed_data.add(key)

            points_before = order.points_before
            points_after = order.points_after

            if points_after > points_before:
                points_in = points_after - points_before
                points_out = 0
            elif points_after < points_before:
                points_in = 0
                points_out = points_before - points_after
            else:
                points_in = 0
                points_out = 0

            if points_in == 0 and points_out == 0:
                continue
            
            worksheet.write(row, 0, order.card_id.partner_id.customer_code or '')
            worksheet.write(row, 1, order.card_id.partner_id.name or '')
            worksheet.write(row, 2, order.card_id.display_name or '')
            worksheet.write(row, 3, local_date_order or '')
            worksheet.write(row, 4, order.pos_order_id.account_move.name or '')
            worksheet.write(row, 5, order.pos_order_id.name or '')
            worksheet.write(row, 6, order.pos_order_id.session_id.name or '')
            worksheet.write(row, 7, order.pos_order_id.config_id.name or '')
            worksheet.write(row, 8, self.format_number(points_in) if points_in else '0')
            worksheet.write(row, 9, self.format_number(points_out) if points_out else '0')
            worksheet.write(row, 10, self.format_number(points_after) if points_after else '0')
            # worksheet.write(row, 11, order.is_integrated or '')
            row += 1

        workbook.close()
        xlsx_data = output.getvalue()
        output.close()

        attachment = self.env['ir.attachment'].create({
            'name': 'Report_History_Loyalty_Customer.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(xlsx_data),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        })

        download_url = '/web/content/%s?download=true' % attachment.id
        return {
            'type': 'ir.actions.act_url',
            'url': download_url,
            'target': 'new',
        }

    def format_number(self, number):
        return f"{number:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    
    def get_header_format(self, workbook):
        return workbook.add_format({
            'bold': True,
            'border': 1,
            'align': 'center',
            'valign': 'vcenter',
            # 'bg_color': '#D7E4BC'  # Optional
        })
    
    def action_generate_sales_report_hourly_category(self):
        # raise ValidationError(_(f"action_generate_sales_report_hourly_category"))
        date_from = self.vit_date_from or False
        date_to = self.vit_date_to or False
        invoice_no = self.vit_invoice_no or False
        pos_order_ref = self.vit_pos_order_ref or False

        account_move = self.env['account.move'].search([('name', '=', invoice_no)], limit=1)

        domain = []
        if date_from:
            domain.append(('date_order', '>=', date_from))
        if date_to:
            domain.append(('date_order', '<=', date_to))
        if account_move:
            domain.append(('account_move', '=', account_move.id))
        if pos_order_ref:
            domain.append(('name', '=', pos_order_ref))

        orders = self.env['pos.order'].search(domain)

        if not orders:
            raise UserError("Tidak ada data POS di periode tersebut.")
        if not date_from or not date_to:
            raise UserError("Tidak dapat menampilkan report. Mohon pilih Date From dan Date To")

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet()
        header_format = self.get_header_format(workbook)

        tanggal_dari = self.vit_date_from.strftime("%d/%m/%Y") if self.vit_date_from else ''
        tanggal_sampai = self.vit_date_to.strftime("%d/%m/%Y") if self.vit_date_to else ''
        tanggal_cetak = fields.Date.today().strftime("%d %b %Y")

        # Header laporan
        worksheet.write(0, 0, "Laporan History Penjualan Hourly per Kategori")
        worksheet.write(1, 0, "[{} - {}]".format(tanggal_dari, tanggal_sampai))
        worksheet.write(2, 0, "Dicetak Tanggal {}".format(tanggal_cetak))

        jam_list = ['{:02d}'.format(jam) for jam in range(24)]
        # kategori
        categories = self.env['pos.category'].search([])

        # Buat header kolom
        headers = ["Nama"]
        for jam in jam_list:
            headers += [f"Qty-{jam}", f"Trx-{jam}", f"Sales-{jam}"]

        for col, title in enumerate(headers):
            worksheet.write(4, col, title, header_format)

        row = 5
        for category in categories:
            worksheet.write(row, 0, category.name or '')

            col = 1
            for jam in jam_list:
                jam_int = int(jam)
                total_qty = 0
                total_sales = 0
                trx_set = set()

                for order in orders:
                    order_dt = fields.Datetime.context_timestamp(self, order.date_order)

                    # Tambahan filter jam dan tanggal
                    if order_dt.hour != jam_int:
                        continue
                    if not (date_from <= order_dt.date() <= date_to):
                        continue

                    matching_lines = order.lines.filtered(
                        lambda l: category.id in l.product_id.product_tmpl_id.pos_categ_ids.ids
                    )
                    if matching_lines:
                        trx_set.add(order.id)
                        total_qty += sum(matching_lines.mapped('qty'))
                        total_sales += sum(matching_lines.mapped('price_subtotal_incl'))
                
                worksheet.write(row, col, total_qty or '0')
                worksheet.write(row, col + 1, len(trx_set) or '0')
                worksheet.write(row, col + 2, self.format_number(total_sales) if total_sales else '0')

                col += 3
            row += 1

        workbook.close()
        xlsx_data = output.getvalue()
        output.close()

        attachment = self.env['ir.attachment'].create({
            'name': 'Sales_Report_Hourly_by_Categories.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(xlsx_data),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        })

        download_url = '/web/content/%s?download=true' % attachment.id
        return {
            'type': 'ir.actions.act_url',
            'url': download_url,
            'target': 'new',
        }
    
    def action_generate_sales_report_hourly_payment(self):
        # raise ValidationError(_(f"action_generate_sales_report_hourly_payment"))
        date_from = self.vit_date_from or False
        date_to = self.vit_date_to or False
        invoice_no = self.vit_invoice_no or False
        pos_order_ref = self.vit_pos_order_ref or False

        account_move = self.env['account.move'].search([('name', '=', invoice_no)], limit=1)

        domain = []
        if date_from:
            domain.append(('date_order', '>=', date_from))
        if date_to:
            domain.append(('date_order', '<=', date_to))
        if account_move:
            domain.append(('account_move', '=', account_move.id))
        if pos_order_ref:
            domain.append(('name', '=', pos_order_ref))

        orders = self.env['pos.order'].search(domain)

        if not orders:
            raise UserError("Tidak ada data POS di periode tersebut.")
        if not date_from or not date_to:
            raise UserError("Tidak dapat menampilkan report. Mohon pilih Date From dan Date To")

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet()
        header_format = self.get_header_format(workbook)

        tanggal_dari = self.vit_date_from.strftime("%d/%m/%Y") if self.vit_date_from else ''
        tanggal_sampai = self.vit_date_to.strftime("%d/%m/%Y") if self.vit_date_to else ''
        tanggal_cetak = fields.Date.today().strftime("%d %b %Y")

        # Header laporan
        worksheet.write(0, 0, "Laporan History Penjualan Hourly per Kategori")
        worksheet.write(1, 0, "[{} - {}]".format(tanggal_dari, tanggal_sampai))
        worksheet.write(2, 0, "Dicetak Tanggal {}".format(tanggal_cetak))

        jam_list = ['{:02d}'.format(jam) for jam in range(24)]
        # kategori
        payment = self.env['pos.payment.method'].search([])

        # Buat header kolom
        headers = ["Nama"]
        for jam in jam_list:
            headers += [f"Qty-{jam}", f"Trx-{jam}", f"Sales-{jam}"]

        for col, title in enumerate(headers):
            worksheet.write(4, col, title, header_format)

        row = 5
        for category in payment:
            worksheet.write(row, 0, category.name or '')

            col = 1
            for jam in jam_list:
                jam_int = int(jam)
                total_qty = 0
                total_sales = 0
                trx_set = set()

                for order in orders:
                    order_dt = fields.Datetime.context_timestamp(self, order.date_order)

                    # Tambahan filter jam dan tanggal
                    if order_dt.hour != jam_int:
                        continue
                    if not (date_from <= order_dt.date() <= date_to):
                        continue

                    # Menyaring transaksi berdasarkan metode pembayaran
                    payments = order.payment_ids.filtered(lambda p: p.payment_method_id.name == category.name)
                    if not payments:
                        continue  # Jika tidak ada pembayaran dengan metode yang sesuai, lanjutkan ke order berikutnya

                    matching_lines = order.lines  # Semua baris produk dalam order
                    if matching_lines:
                        trx_set.add(order.id)
                        total_qty += sum(matching_lines.mapped('qty'))
                        total_sales += sum(matching_lines.mapped('price_subtotal_incl'))
                
                worksheet.write(row, col, total_qty or '0')
                worksheet.write(row, col + 1, len(trx_set) or '0')
                worksheet.write(row, col + 2, self.format_number(total_sales) if total_sales else '0')

                col += 3
            row += 1

        workbook.close()
        xlsx_data = output.getvalue()
        output.close()

        attachment = self.env['ir.attachment'].create({
            'name': 'Sales_Report_Hourly_by_Payment.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(xlsx_data),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        })

        download_url = '/web/content/%s?download=true' % attachment.id
        return {
            'type': 'ir.actions.act_url',
            'url': download_url,
            'target': 'new',
        }
    
    def action_generate_sales_report_hourly_contribution_by_category(self):
        date_from = self.vit_date_from or False
        date_to = self.vit_date_to or False

        domain = []
        if date_from:
            domain.append(('date_order', '>=', date_from))
        if date_to:
            domain.append(('date_order', '<=', date_to))

        orders = self.env['pos.order'].search(domain)

        if not orders:
            raise UserError("Tidak ada data POS di periode tersebut.")
        if not date_from or not date_to:
            raise UserError("Tidak dapat menampilkan report. Mohon pilih Date From dan Date To")

        
        # Kumpulkan data per kategori
        category_data = {}

        for order in orders:
            for line in order.lines:
                if not line.product_id:
                    continue
                # Ambil kategori (bisa banyak), fallback ke '-'
                tmpl = line.product_id.product_tmpl_id
                categories = tmpl.pos_categ_ids
                category_names = categories.mapped('name') if categories else ['-']
                
                for category in categories:
                    key = category.name
                    data = category_data.setdefault(key, {
                        'user': order.user_id.name or '',
                        'store_code': order.config_id.name or '',
                        'store_name': order.config_id.name or '',
                        'category': key,
                        'qty': 0,
                        'trx_set': set(),
                        'valuesales': 0.0,
                        'valuestock': 0.0,  # Optional if needed
                        'durasi': (date_to - date_from).days + 1 if date_from and date_to else 0
                    })

                    data['qty'] += line.qty
                    data['trx_set'].add(order.id)
                    data['valuesales'] += line.price_subtotal_incl

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet()
        header_format = self.get_header_format(workbook)

        tanggal_dari = self.vit_date_from.strftime("%d/%m/%Y") if self.vit_date_from else ''
        tanggal_sampai = self.vit_date_to.strftime("%d/%m/%Y") if self.vit_date_to else ''
        tanggal_cetak = fields.Date.today().strftime("%d %b %Y")

        # Header laporan
        worksheet.write(0, 0, "Laporan History Penjualan")
        worksheet.write(1, 0, "[ {} - {} ]".format(tanggal_dari, tanggal_sampai))
        worksheet.write(2, 0, "Dicetak Tanggal {}".format(tanggal_cetak))

        header = [
            'User', 'Kode Store', 'Nama Store', 'Kategori', 'Quantity', 'Trx', 'Value Sales',
            'ATV', 'UPT', 'AUR', 'Durasi'
        ]
        # header = [
        #     'userid', 'kodelokasi', 'nama', 'Kategori', 'Qty', 'Trx', 'valuesales',
        #     'valuesales', 'valustock', 'persenstock', 'persenIL', 'ATV', 'UPT', 'AUR', 'durasi'
        # ]

        for col, title in enumerate(header):
            worksheet.write(4, col, title, header_format)

        row = 5
        for data in category_data.values():
            trx_count = len(data['trx_set'])
            ATV = data['valuesales'] / trx_count if trx_count else 0
            UPT = data['qty'] / trx_count if trx_count else 0
            AUR = data['valuesales'] / data['qty'] if data['qty'] else 0

            worksheet.write(row, 0, data['user'])
            worksheet.write(row, 1, data['store_code'])
            worksheet.write(row, 2, data['store_name'])
            worksheet.write(row, 3, data['category'])
            worksheet.write(row, 4, data['qty'])
            worksheet.write(row, 5, trx_count)
            worksheet.write(row, 6, data['valuesales'])
            # worksheet.write(row, 7, data['valuestock'])
            worksheet.write(row, 7, ATV)
            worksheet.write(row, 8, UPT)
            worksheet.write(row, 9, AUR)
            worksheet.write(row, 10, data['durasi'])
            row += 1

        workbook.close()
        xlsx_data = output.getvalue()
        output.close()

        attachment = self.env['ir.attachment'].create({
            'name': 'Sales_Report_Contribution_by_Category.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(xlsx_data),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        })

        download_url = '/web/content/%s?download=true' % attachment.id
        return {
            'type': 'ir.actions.act_url',
            'url': download_url,
            'target': 'new',
        }

    def action_generate_sales_report_hourly_contribution_by_brand(self):
        date_from = self.vit_date_from or False
        date_to = self.vit_date_to or False

        domain = []
        if date_from:
            domain.append(('date_order', '>=', date_from))
        if date_to:
            domain.append(('date_order', '<=', date_to))

        orders = self.env['pos.order'].search(domain)

        if not orders:
            raise UserError("Tidak ada data POS di periode tersebut.")
        if not date_from or not date_to:
            raise UserError("Tidak dapat menampilkan report. Mohon pilih Date From dan Date To")

        
        # Data dikumpulkan berdasarkan brand
        brand_data = {}

        for order in orders:
            for line in order.lines:
                tmpl = line.product_id.product_tmpl_id
                brand_name = tmpl.brand or '-'  # akses brand (Char)

                key = (brand_name, order.config_id.name)

                data = brand_data.setdefault(key, {
                    'user': order.user_id.name or '',
                    'store_code': order.config_id.name or '',
                    'store_name': order.config_id.name or '',
                    'brand': brand_name,
                    'qty': 0,
                    'trx_set': set(),
                    'valuesales': 0.0,
                    'valuestock': 0.0,
                    'persenstock': 0,
                    'persenil': 0,
                    'durasi': (date_to - date_from).days + 1 if date_from and date_to else "-",
                })

                data['qty'] += line.qty
                data['trx_set'].add(order.id)
                data['valuesales'] += line.price_subtotal_incl
                # Jika ingin valuestock, uncomment:
                data['valuestock'] += line.product_id.standard_price * line.qty

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet()
        header_format = self.get_header_format(workbook)

        tanggal_dari = self.vit_date_from.strftime("%d/%m/%Y") if self.vit_date_from else ''
        tanggal_sampai = self.vit_date_to.strftime("%d/%m/%Y") if self.vit_date_to else ''
        tanggal_cetak = fields.Date.today().strftime("%d %b %Y")

        # Header laporan
        worksheet.write(0, 0, "Laporan History Penjualan")
        worksheet.write(1, 0, "[ {} - {} ]".format(tanggal_dari, tanggal_sampai))
        worksheet.write(2, 0, "Dicetak Tanggal {}".format(tanggal_cetak))

        header = [
            'User', 'Kode Store', 'Nama Store', 'Brand', 'Quantity', 'Trx', 'Value Sales',
            'ATV', 'UPT', 'AUR', 'Durasi'
        ]
        # header = [
        #     'userid', 'kodelokasi', 'nama', 'brand', 'Qty', 'Trx', 'valuesales',
        #     'persensales', 'valuestock', 'persenstock', 'persenIL', 'ATV', 'UPT', 'AUR', 'durasi'
        # ]

        for col, title in enumerate(header):
            worksheet.write(4, col, title, header_format)

        row = 5
        total_valuesales = sum(d['valuesales'] for d in brand_data.values()) or 1

        for data in brand_data.values():
            trx_count = len(data['trx_set'])
            ATV = data['valuesales'] / trx_count if trx_count else 0
            UPT = data['qty'] / trx_count if trx_count else 0
            AUR = data['valuesales'] / data['qty'] if data['qty'] else 0
            persen_sales = (data['valuesales'] / total_valuesales) * 100 if total_valuesales else 0

            worksheet.write(row, 0, data['user'])
            worksheet.write(row, 1, data['store_code'])
            worksheet.write(row, 2, data['store_name'])
            worksheet.write(row, 3, data['brand'])
            worksheet.write(row, 4, data['qty'])
            worksheet.write(row, 5, trx_count)
            worksheet.write(row, 6, data['valuesales'])
            # worksheet.write(row, 7, data['valuestock'])
            worksheet.write(row, 7, ATV)
            worksheet.write(row, 8, UPT)
            worksheet.write(row, 9, AUR)
            worksheet.write(row, 10, data['durasi'])
            row += 1

        workbook.close()
        xlsx_data = output.getvalue()
        output.close()

        attachment = self.env['ir.attachment'].create({
            'name': 'Sales_Report_Contribution_by_Brand.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(xlsx_data),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        })

        download_url = '/web/content/%s?download=true' % attachment.id
        return {
            'type': 'ir.actions.act_url',
            'url': download_url,
            'target': 'new',
        }

    def action_generate_sales_report_cashier_transaction(self):
        date_from = self.vit_date_from or False
        date_to = self.vit_date_to or False
        invoice_no = self.vit_invoice_no or False
        pos_order_ref = self.vit_pos_order_ref or False

        account_move = self.env['account.move'].search([('name', '=', invoice_no)], limit=1)

        domain = []
        if date_from:
            domain.append(('date_order', '>=', date_from))
        if date_to:
            domain.append(('date_order', '<=', date_to))
        if account_move:
            domain.append(('account_move', '=', account_move.id))
        if pos_order_ref:
            domain.append(('name', '=', pos_order_ref))

        orders = self.env['pos.order'].search(domain)

        if not orders:
            raise UserError("Tidak ada data POS di periode tersebut.")
        if not date_from or not date_to:
            raise UserError("Tidak dapat menampilkan report. Mohon pilih Date From dan Date To")


        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet()
        header_format = self.get_header_format(workbook)

        tanggal_dari = self.vit_date_from.strftime("%d/%m/%Y") if self.vit_date_from else ''
        tanggal_sampai = self.vit_date_to.strftime("%d/%m/%Y") if self.vit_date_to else ''
        tanggal_cetak = fields.Date.today().strftime("%d %b %Y")

        # Header laporan
        worksheet.write(0, 0, "Laporan Transaksi Kasir")
        worksheet.write(1, 0, "[ {} - {} ]".format(tanggal_dari, tanggal_sampai))
        worksheet.write(2, 0, "Dicetak Tanggal {}".format(tanggal_cetak))

        header = [
            'User', 'Kasir', 'Invoice No.', 'Order No.', 'Session', 'Tanggal', 'Kode Store', 'Nama Store',
            'Payment Method', 'Nominal', 'Tanggal Payment'
        ]

        for col, title in enumerate(header):
            worksheet.write(4, col, title, header_format)

        row = 5
        for order in orders:
            local_date_order = fields.Datetime.context_timestamp(self, order.date_order)
            for order_line in order.payment_ids:
                worksheet.write(row, 0, order.user_id.name or '')
                worksheet.write(row, 1, order.employee_id.name or '')
                worksheet.write(row, 2, order.account_move.name or '')
                worksheet.write(row, 3, order.name or '')
                worksheet.write(row, 4, order.session_id.name or '')
                worksheet.write(row, 5, local_date_order.strftime('%d/%m/%Y %H:%M:%S'))
                worksheet.write(row, 6, order.config_id.name or '')
                worksheet.write(row, 7, order.config_id.name or '')
                worksheet.write(row, 8, order_line.payment_method_id.name or '')
                worksheet.write(row, 9, self.format_number(order_line.amount) if order_line.amount else '')
                worksheet.write(row, 10, order_line.payment_date.strftime('%Y-%m-%d %H:%M:%S') if order_line.payment_date else '')
                row += 1

        workbook.close()
        xlsx_data = output.getvalue()
        output.close()

        attachment = self.env['ir.attachment'].create({
            'name': 'Sales_Report_Cashier_Transaction.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(xlsx_data),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        })

        download_url = '/web/content/%s?download=true' % attachment.id
        return {
            'type': 'ir.actions.act_url',
            'url': download_url,
            'target': 'new',
        }
    
    def action_generate_sales_report_settlement_end_of_shift(self):
        date_from = self.vit_date_from or False
        date_to = self.vit_date_to or False

        domain = []
        if date_from:
            domain.append(('start_date', '>=', date_from))
        if date_to:
            domain.append(('start_date', '<=', date_to))

        end_shift = self.env['end.shift'].search(domain, order='id desc')

        if not end_shift:
            raise UserError("Tidak ada data Shift POS di periode tersebut.")
        if not date_from or not date_to:
            raise UserError("Tidak dapat menampilkan report. Mohon pilih Date From dan Date To")


        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet()
        header_format = self.get_header_format(workbook)

        tanggal_dari = self.vit_date_from.strftime("%d/%m/%Y") if self.vit_date_from else ''
        tanggal_sampai = self.vit_date_to.strftime("%d/%m/%Y") if self.vit_date_to else ''
        tanggal_cetak = fields.Date.today().strftime("%d %b %Y")

        # Header laporan
        worksheet.write(0, 0, "Laporan Settlement")
        worksheet.write(1, 0, "[ {} - {} ]".format(tanggal_dari, tanggal_sampai))
        worksheet.write(2, 0, "Dicetak Tanggal {}".format(tanggal_cetak))

        header = [
            'User', 'Kasir', 'Tanggal', 'Kategori', 'Kode Store', 'Nama Store', 
            'Payment Method', 'Amount', 'Expected Amount', 'Amount Difference', 'Shift Number', 'Session'
        ]

        for col, title in enumerate(header):
            worksheet.write(4, col, title, header_format)

        row = 5
        for shift in end_shift:
            if shift.line_ids:
                for order_line in shift.line_ids:
                    local_date_order = fields.Datetime.context_timestamp(self, order_line.payment_date)
                    date_str = local_date_order.strftime('%Y-%m-%d %H:%M:%S') if local_date_order else ''
                    worksheet.write(row, 0, shift.session_id.user_id.name or '')
                    worksheet.write(row, 1, shift.cashier_id.name or '')
                    worksheet.write(row, 2, date_str or '')
                    worksheet.write(row, 3, f'END OF SHIFT ({shift.start_date} - {shift.end_date}) - {shift.cashier_id.name} - {shift.session_id.config_id.name}' or '')
                    worksheet.write(row, 4, shift.session_id.config_id.name or '')
                    worksheet.write(row, 5, shift.session_id.config_id.name or '')
                    worksheet.write(row, 6, order_line.payment_method_id.name or '')
                    worksheet.write(row, 7, self.format_number(order_line.amount) if order_line.amount else '')
                    worksheet.write(row, 8, self.format_number(order_line.expected_amount) if order_line.expected_amount else '')
                    worksheet.write(row, 9, self.format_number(order_line.amount_difference) if order_line.amount_difference else '')
                    worksheet.write(row, 10, shift.doc_num or '')
                    worksheet.write(row, 11, shift.session_id.name or '')
                    row += 1
            else:
                # Jika tidak ada order_line, tetap tulis info shift, order_line kosong
                worksheet.write(row, 0, shift.session_id.user_id.name or '')
                worksheet.write(row, 1, shift.cashier_id.name or '')
                worksheet.write(row, 2, '')  # Tidak ada payment_date
                worksheet.write(row, 3, f'END OF SHIFT ({shift.start_date} - {shift.end_date}) - {shift.cashier_id.name} - {shift.session_id.config_id.name}' or '')
                worksheet.write(row, 4, shift.session_id.config_id.name or '')
                worksheet.write(row, 5, shift.session_id.config_id.name or '')
                worksheet.write(row, 6, '')  # kosong karena tidak ada order_line
                worksheet.write(row, 7, '')
                worksheet.write(row, 8, '')
                worksheet.write(row, 9, '')
                worksheet.write(row, 10, shift.doc_num or '')
                worksheet.write(row, 11, shift.session_id.name or '')
                row += 1

        workbook.close()
        xlsx_data = output.getvalue()
        output.close()

        attachment = self.env['ir.attachment'].create({
            'name': 'Sales_Report_Settlement_End_of_Shift.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(xlsx_data),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        })

        download_url = '/web/content/%s?download=true' % attachment.id
        return {
            'type': 'ir.actions.act_url',
            'url': download_url,
            'target': 'new',
        }

    def action_generate_sales_report_settlement_end_of_day(self):
        date_from = self.vit_date_from or False
        date_to = self.vit_date_to or False

        domain = []
        if date_from:
            domain.append(('start_date', '>=', date_from))
        if date_to:
            domain.append(('start_date', '<=', date_to))

        end_shift = self.env['end.shift'].search(domain, order='id desc')

        if not end_shift:
            raise UserError("Tidak ada data Shift POS di periode tersebut.")
        if not date_from or not date_to:
            raise UserError("Tidak dapat menampilkan report. Mohon pilih Date From dan Date To")

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet()
        header_format = self.get_header_format(workbook)

        tanggal_dari = self.vit_date_from.strftime("%d/%m/%Y") if self.vit_date_from else ''
        tanggal_sampai = self.vit_date_to.strftime("%d/%m/%Y") if self.vit_date_to else ''
        tanggal_cetak = fields.Date.today().strftime("%d %b %Y")

        # Header laporan
        worksheet.write(0, 0, "Laporan Settlement")
        worksheet.write(1, 0, "[ {} - {} ]".format(tanggal_dari, tanggal_sampai))
        worksheet.write(2, 0, "Dicetak Tanggal {}".format(tanggal_cetak))

        header = [
            'User', 'Tanggal', 'Kode Store', 'Nama Store', 'Payment Method', 
            'Amount', 'Expected Amount', 'Amount Difference', 'Shift Number', 'Session'
        ]

        for col, title in enumerate(header):
            worksheet.write(4, col, title, header_format)

        row = 5
        for shift in end_shift:
            for order_line in shift.line_ids:
                local_date_order = fields.Datetime.context_timestamp(self, order_line.payment_date)
                worksheet.write(row, 0, shift.session_id.user_id.name or '')
                worksheet.write(row, 1, local_date_order.strftime('%Y-%m-%d %H:%M:%S') if local_date_order else '')
                worksheet.write(row, 2, shift.session_id.config_id.name or '')
                worksheet.write(row, 3, shift.session_id.config_id.name or '')
                worksheet.write(row, 4, order_line.payment_method_id.name or '')
                worksheet.write(row, 5, self.format_number(order_line.amount) if order_line.amount else '')
                worksheet.write(row, 6, self.format_number(order_line.expected_amount) if order_line.expected_amount else '')
                worksheet.write(row, 7, self.format_number(order_line.amount_difference) if order_line.amount_difference else '')
                worksheet.write(row, 8, shift.doc_num or '')
                worksheet.write(row, 9, shift.session_id.name or '')
                row += 1

        workbook.close()
        xlsx_data = output.getvalue()
        output.close()

        attachment = self.env['ir.attachment'].create({
            'name': 'Sales_Report_Settlement_End_of_Day.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(xlsx_data),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        })

        download_url = '/web/content/%s?download=true' % attachment.id
        return {
            'type': 'ir.actions.act_url',
            'url': download_url,
            'target': 'new',
        }
    
    def action_generate_sales_report_stock_counting(self):
        # raise ValidationError(_(f"action_generate_sales_report_stock_counting"))
        #  ambil yang statusnya counted -> no. counting, warehouse, lokasi, inventory date di header, detailnya product, lot/serial number, on hand,counted,difference,uom
        date_from = self.vit_date_from or False
        date_to = self.vit_date_to or False
        doc_num = self.vit_counting_no or False

        domain = []
        domain.append(('state', '=', 'counted'))
        if date_from:
            domain.append(('start_date', '>=', date_from))
        if date_to:
            domain.append(('start_date', '<=', date_to))
        if doc_num:
            domain.append(('doc_num', '=', doc_num))

        stock_counting = self.env['inventory.stock'].search(domain)

        if not stock_counting:
            raise UserError("Tidak ada data stock counting di periode tersebut.")
        if not date_from or not date_to:
            raise UserError("Tidak dapat menampilkan report. Mohon pilih Date From dan Date To")

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet()
        header_format = self.get_header_format(workbook)

        tanggal_dari = self.vit_date_from.strftime("%d/%m/%Y") if self.vit_date_from else ''
        tanggal_sampai = self.vit_date_to.strftime("%d/%m/%Y") if self.vit_date_to else ''
        tanggal_cetak = fields.Date.today().strftime("%d %b %Y")

        # Header laporan
        worksheet.write(0, 0, "Laporan Stock Counting")
        worksheet.write(1, 0, "[ {} - {} ]".format(tanggal_dari, tanggal_sampai))
        worksheet.write(2, 0, "Dicetak Tanggal {}".format(tanggal_cetak))

        header = [
            'Counting No.', 'Warehouse', 'Lokasi', 'Inventory Date', 
            'Product', 'Lot/Serial Number', 'On Hand', 'Counted', 'Difference', 'UOM'
        ]

        for col, title in enumerate(header):
            worksheet.write(4, col, title, header_format)

        row = 5
        for stock in stock_counting:
            for order_line in stock.inventory_counting_ids:
                local_inventory_date = fields.Datetime.context_timestamp(self, stock.inventory_date)
                worksheet.write(row, 0, stock.doc_num or '')
                worksheet.write(row, 1, stock.warehouse_id.name or '')
                worksheet.write(row, 2, stock.location_id.display_name or '')
                worksheet.write(row, 3, local_inventory_date.strftime('%Y-%m-%d %H:%M:%S') if local_inventory_date else '')
                worksheet.write(row, 4, order_line.product_id.name or '')
                worksheet.write(row, 5, order_line.lot_id.name or '')
                worksheet.write(row, 6, order_line.qty_hand or '0')
                worksheet.write(row, 7, order_line.counted_qty or '0')
                worksheet.write(row, 8, order_line.difference_qty or '0')
                worksheet.write(row, 9, order_line.uom_id.name or '')
                row += 1

        workbook.close()
        xlsx_data = output.getvalue()
        output.close()

        attachment = self.env['ir.attachment'].create({
            'name': 'Sales_Report_Stock_Counting.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(xlsx_data),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        })

        download_url = '/web/content/%s?download=true' % attachment.id
        return {
            'type': 'ir.actions.act_url',
            'url': download_url,
            'target': 'new',
        }