from odoo import models, fields, _, api, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

class SalesReportDetailController(http.Controller):

    def back_to_pos_view(self):
        # cari action untuk POS Config
        action = request.env.ref("point_of_sale.action_pos_config_kanban").read()[0]
        menu = request.env.ref("point_of_sale.menu_point_root")
        # susun URL backend
        backend_url = "/web#action={}&model={}&view_type={}&menu_id={}".format(
            action["id"], action["res_model"], action.get("view_mode", "kanban"), menu.id
        )
        return backend_url
    
    def parse_date(self, raw_date):
        if raw_date:
            return datetime.strptime(raw_date, "%d/%m/%Y").strftime("%Y-%m-%d")
        return None
    
    def format_number(self, number):
        # Pemisah ribuan pakai koma (,) dan desimal pakai titik (.)
        # Pembulatan fleksibel: pecahan < 0,50 dibulatkan ke bawah, >= 0,50 dibulatkan ke atas
        rounded = Decimal(str(number)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        return f"{int(rounded):,}"

    @http.route('/my/sales/report/detail', type='http', auth='user', website=True)
    def portal_sales_report_detail(self, **kw):
        date_from = kw.get('date_from')
        date_to = kw.get('date_to')
        invoice_no = kw.get('invoice_no')
        pos_order_ref = kw.get('pos_order_ref')

        # Validasi parameter wajib
        if not date_from or not date_to:
            return request.not_found()
        
        account_move = request.env['account.move'].sudo().search([('name', '=', invoice_no)], limit=1)

        domain = []
        if date_from:
            domain.append(('date_order', '>=', date_from))
        if date_to:
            domain.append(('date_order', '<=', date_to))
        if account_move:
            domain.append(('account_move', '=', account_move.id))
        if pos_order_ref:
            domain.append(('name', '=', pos_order_ref))

        orders = request.env['pos.order'].sudo().search(domain)

        values = {
            'orders': orders,
            'date_from': fields.Date.from_string(date_from).strftime('%d/%m/%Y'),
            'date_to': fields.Date.from_string(date_to).strftime('%d/%m/%Y'),
            'tanggal_cetak': fields.Date.today().strftime("%d %b %Y"),
            'backend_url': self.back_to_pos_view(),
            'format_number': self.format_number,  # tambahkan ini
        }
        return request.render('report_pos.report_sales_detail', values)
    
    
    @http.route(['/my/sales/report/detail/pdf'], type='http', auth="user", website=True)
    def portal_sales_report_detail_pdf(self, date_from=None, date_to=None, **kw):

        if not date_from or not date_to:
            return request.not_found()  # atau tampilkan error page
    
        # tangkap parameter dari URL
        raw_date_from = request.params.get('date_from')
        raw_date_to = request.params.get('date_to')

        date_from = fields.Date.from_string(self.parse_date(raw_date_from))
        date_to = fields.Date.from_string(self.parse_date(raw_date_to))

        # ambil data sesuai filter
        orders = request.env['sale.order'].sudo().search([
            ('date_order', '>=', date_from),
            ('date_order', '<=', date_to),
        ])

        values = {
            'orders': orders,
            'date_from': date_from,
            'date_to': date_to,
            'tanggal_cetak': fields.Date.today(),
        }

        # render template QWeb yang sudah kamu daftarkan di XML
        html = request.env['ir.qweb']._render('report_pos.report_detail_pdf_template', values)

        # gunakan wkhtmltopdf untuk generate PDF
        pdf = request.env['ir.actions.report']._run_wkhtmltopdf(
            [html], landscape=False
        )

        # kirim ke browser
        pdfhttpheaders = [
            ('Content-Type', 'application/pdf'),
            ('Content-Length', len(pdf)),
            ('Content-Disposition', 'attachment; filename="sales_report_detail.pdf"')
        ]
        return request.make_response(pdf, headers=pdfhttpheaders)

    @http.route('/sales/report/recap', type='http', auth='user', website=True)
    def portal_sales_report_recap(self, **kw):
        date_from = kw.get('date_from')
        date_to = kw.get('date_to')
        invoice_no = kw.get('invoice_no')
        pos_order_ref = kw.get('pos_order_ref')

        # Validasi parameter wajib
        if not date_from or not date_to:
            return request.not_found()

        account_move = request.env['account.move'].sudo().search([('name', '=', invoice_no)], limit=1)

        domain = []
        if date_from:
            domain.append(('date_order', '>=', date_from))
        if date_to:
            domain.append(('date_order', '<=', date_to))
        if account_move:
            domain.append(('account_move', '=', account_move.id))
        if pos_order_ref:
            domain.append(('name', '=', pos_order_ref))

        orders = request.env['pos.order'].sudo().search(domain)

        values = {
            'orders': orders,
            'date_from': fields.Date.from_string(date_from).strftime('%d/%m/%Y'),
            'date_to': fields.Date.from_string(date_to).strftime('%d/%m/%Y'),
            'tanggal_cetak': fields.Date.today().strftime("%d %b %Y"),
            'backend_url': self.back_to_pos_view(),
            'format_number': self.format_number,
        }
        return request.render('report_pos.report_sales_recap', values)

    @http.route('/sales/report/spending', type='http', auth='user', website=True)
    def portal_sales_report_spending(self, **kw):
        date_from = kw.get('date_from')
        date_to = kw.get('date_to')
        # invoice_no = kw.get('invoice_no')
        # pos_order_ref = kw.get('pos_order_ref')

        if not date_from or not date_to:
            return request.not_found()

        domain = [
            ('date_order', '>=', date_from),
            ('date_order', '<=', date_to),
        ]

        # if invoice_no:
        #     move = request.env['account.move'].sudo().search([('name', '=', invoice_no)], limit=1)
        #     if move:
        #         domain.append(('account_move', '=', move.id))

        # if pos_order_ref:
        #     domain.append(('name', '=', pos_order_ref))

        orders = request.env['pos.order'].sudo().search(domain)

        # Ambil daftar tanggal unik
        tanggal_set = set(
            fields.Datetime.context_timestamp(request.env.user, o.date_order).date()
            for o in orders
        )
        tanggal_list = sorted(list(tanggal_set))

        # Range Spending seperti di Python XLSX kamu
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

        # Bentuk data_rows
        data_rows = []
        for min_spending, max_spending, label in range_spending:
            row_data = {'label': label}
            for tgl in tanggal_list:
                order_filtered = orders.filtered(lambda o:
                    fields.Datetime.context_timestamp(request.env.user, o.date_order).date() == tgl and
                    min_spending <= o.amount_total <= max_spending
                )

                total_qty = sum(sum(line.qty for line in o.lines) for o in order_filtered)
                total_trx = len(order_filtered)
                total_sales = sum(o.amount_total for o in order_filtered)

                row_data[f"{tgl.strftime('%d/%m/%Y')}_qty"] = total_qty or ''
                row_data[f"{tgl.strftime('%d/%m/%Y')}_trx"] = total_trx or ''
                row_data[f"{tgl.strftime('%d/%m/%Y')}_sales"] = "{:,.0f}".format(total_sales) if total_sales else ''
            
            data_rows.append(row_data)

        values = {
            'orders': orders,
            'tanggal_list': tanggal_list,  # dikirim ke QWeb
            'data_rows': data_rows,
            'date_from': fields.Date.from_string(date_from).strftime('%d/%m/%Y'),
            'date_to': fields.Date.from_string(date_to).strftime('%d/%m/%Y'),
            'tanggal_cetak': fields.Date.today().strftime("%d %b %Y"),
        }
        return request.render('report_pos.report_sales_spending', values)
    
    @http.route('/sales/report/hourly', type='http', auth='user', website=True)
    def portal_sales_report_hourly(self, **kw):
        date_from = kw.get('date_from')
        date_to = kw.get('date_to')
        # invoice_no = kw.get('invoice_no')
        # pos_order_ref = kw.get('pos_order_ref')

        if not date_from or not date_to:
            return request.not_found()

        domain = [
            ('date_order', '>=', date_from),
            ('date_order', '<=', date_to),
        ]

        # if invoice_no:
        #     move = request.env['account.move'].sudo().search([('name', '=', invoice_no)], limit=1)
        #     if move:
        #         domain.append(('account_move', '=', move.id))

        # if pos_order_ref:
        #     domain.append(('name', '=', pos_order_ref))

        orders = request.env['pos.order'].sudo().search(domain)

        # Ambil daftar tanggal unik
        tanggal_set = set(
            fields.Datetime.context_timestamp(request.env.user, o.date_order).date()
            for o in orders
        )
        tanggal_list = sorted(list(tanggal_set))

        # Range Spending seperti di Python XLSX kamu
        hourly = []
        for data_hour in range(24):
            hourly.append(data_hour)
        # range_spending = [
        #     (0, 50000, "0 - 50.000"),
        #     (50001, 100000, "50.001 - 100.000"),
        #     (100001, 250000, "100.001 - 250.000"),
        #     (250001, 500000, "250.001 - 500.000"),
        #     (500001, 1000000, "500.001 - 1.000.000"),
        #     (1000001, 3000000, "1.000.001 - 3.000.000"),
        #     (3000001, 5000000, "3.000.001 - 5.000.000"),
        #     (5000001, 20000000, "5.000.001 - 20.000.000"),
        #     (20000001, float('inf'), ">20.000.001"),
        # ]

        # Bentuk data_rows
        data_rows = []
        for hour in hourly:
            row_data = {}
            for tgl in tanggal_list:
                order_filtered = orders.filtered(lambda o: fields.Datetime.context_timestamp(request.env.user, o.date_order).date() == tgl and fields.Datetime.context_timestamp(request.env.user, o.date_order).hour == hour)
                # total_qty = sum(sum(line.qty for line in o.lines) for o in order_filtered)
                # total_trx = len(order_filtered)
                # total_sales = sum(o.amount_total for o in order_filtered)

                total_qty = sum(order_filtered.mapped(lambda o: sum(o.lines.mapped('qty'))))
                total_trx = len(order_filtered)
                total_sales = sum(order_filtered.mapped('amount_total'))

                row_data[f"{tgl.strftime('%d/%m/%Y')}_qty"] = total_qty or ''
                row_data[f"{tgl.strftime('%d/%m/%Y')}_trx"] = total_trx or ''
                row_data[f"{tgl.strftime('%d/%m/%Y')}_sales"] = "{:,.0f}".format(total_sales) if total_sales else ''
            
            data_rows.append(row_data)

        values = {
            'orders': orders,
            'tanggal_list': tanggal_list,  # dikirim ke QWeb
            'data_rows': data_rows,
            'date_from': fields.Date.from_string(date_from).strftime('%d/%m/%Y'),
            'date_to': fields.Date.from_string(date_to).strftime('%d/%m/%Y'),
            'tanggal_cetak': fields.Date.today().strftime("%d %b %Y"),
        }
        return request.render('report_pos.report_sales_hourly', values)


    @http.route('/sales/report/hourly_category', type='http', auth='user', website=True)
    def portal_sales_report_hourly_category(self, **kw):
        date_from = kw.get('date_from')
        date_to = kw.get('date_to')
        invoice_no = kw.get('invoice_no')
        pos_order_ref = kw.get('pos_order_ref')

        if not date_from or not date_to:
            return request.not_found()

        domain = [
            ('date_order', '>=', date_from),
            ('date_order', '<=', date_to),
        ]

        if invoice_no:
            move = request.env['account.move'].sudo().search([('name', '=', invoice_no)], limit=1)
            if move:
                domain.append(('account_move', '=', move.id))

        if pos_order_ref:
            domain.append(('name', '=', pos_order_ref))

        orders = request.env['pos.order'].sudo().search(domain)
        if not orders:
            return request.render('report_pos.report_sales_hourly_category', {
                'orders': [],
                'tanggal_list': [],
                'data_rows': [],
                'date_from': fields.Date.from_string(date_from).strftime('%d/%m/%Y'),
                'date_to': fields.Date.from_string(date_to).strftime('%d/%m/%Y'),
                'tanggal_cetak': fields.Date.today().strftime("%d %b %Y"),
            })

        jam_list = ['{:02d}'.format(j) for j in range(24)]
        categories = request.env['pos.category'].sudo().search([])

        data_rows = []
        for category in categories:
            row_data = {'kategori': category.name}
            for jam in jam_list:
                jam_int = int(jam)
                total_qty = 0
                total_sales = 0
                trx_set = set()

                for order in orders:
                    order_dt = fields.Datetime.context_timestamp(request.env.user, order.date_order)
                    if order_dt.hour != jam_int:
                        continue
                    if not (fields.Date.from_string(date_from) <= order_dt.date() <= fields.Date.from_string(date_to)):
                        continue

                    matching_lines = order.lines.filtered(
                        lambda l: category.id in l.product_id.product_tmpl_id.pos_categ_ids.ids
                    )
                    if matching_lines:
                        trx_set.add(order.id)
                        total_qty += sum(matching_lines.mapped('qty'))
                        total_sales += sum(matching_lines.mapped('price_subtotal_incl'))

                row_data[f"{jam}_qty"] = total_qty or ''
                row_data[f"{jam}_trx"] = len(trx_set) or ''
                row_data[f"{jam}_sales"] = "{:,.0f}".format(total_sales) if total_sales else ''
            
            data_rows.append(row_data)

        values = {
            'orders': orders,
            'data_rows': data_rows,
            'jam_list': jam_list,
            'date_from': fields.Date.from_string(date_from).strftime('%d/%m/%Y'),
            'date_to': fields.Date.from_string(date_to).strftime('%d/%m/%Y'),
            'tanggal_cetak': fields.Date.today().strftime("%d %b %Y"),
        }
        return request.render('report_pos.report_sales_hourly_category', values)



    @http.route('/sales/report/hourly_payment', type='http', auth='user', website=True)
    def portal_sales_report_hourly_payment(self, **kw):
        date_from = kw.get('date_from')
        date_to = kw.get('date_to')
        invoice_no = kw.get('invoice_no')
        pos_order_ref = kw.get('pos_order_ref')

        # Validasi parameter wajib
        if not date_from or not date_to:
            return request.not_found()

        domain = [
            ('date_order', '>=', date_from),
            ('date_order', '<=', date_to),
        ]

        if invoice_no:
            move = request.env['account.move'].sudo().search([('name', '=', invoice_no)], limit=1)
            if move:
                domain.append(('account_move', '=', move.id))

        if pos_order_ref:
            domain.append(('name', '=', pos_order_ref))

        orders = request.env['pos.order'].sudo().search(domain)

        values = {
            'orders': orders,
            'date_from': fields.Date.from_string(date_from).strftime('%d/%m/%Y'),
            'date_to': fields.Date.from_string(date_to).strftime('%d/%m/%Y'),
            'tanggal_cetak': fields.Date.today().strftime("%d %b %Y"),
        }
        return request.render('report_pos.report_sales_hourly_payment', values)


    @http.route('/sales/report/contribution_by_brand', type='http', auth='user', website=True)
    def portal_sales_report_contribution_by_brand(self, **kw):
        date_from = kw.get('date_from')
        date_to = kw.get('date_to')
        invoice_no = kw.get('invoice_no')
        pos_order_ref = kw.get('pos_order_ref')

        # Validasi parameter wajib
        if not date_from or not date_to:
            return request.not_found()

        domain = [
            ('date_order', '>=', date_from),
            ('date_order', '<=', date_to),
        ]

        if invoice_no:
            move = request.env['account.move'].sudo().search([('name', '=', invoice_no)], limit=1)
            if move:
                domain.append(('account_move', '=', move.id))

        if pos_order_ref:
            domain.append(('name', '=', pos_order_ref))

        orders = request.env['pos.order'].sudo().search(domain)

        values = {
            'orders': orders,
            'date_from': fields.Date.from_string(date_from).strftime('%d/%m/%Y'),
            'date_to': fields.Date.from_string(date_to).strftime('%d/%m/%Y'),
            'tanggal_cetak': fields.Date.today().strftime("%d %b %Y"),
        }
        return request.render('report_pos.report_sales_contribution_by_brand', values)


    # @http.route('/sales/report/contribution_by_category', type='http', auth='user', website=True)
    # def portal_sales_report_contribution_by_category(self, **kw):
    #     date_from = kw.get('date_from')
    #     date_to = kw.get('date_to')
    #     # invoice_no = kw.get('invoice_no')
    #     # pos_order_ref = kw.get('pos_order_ref')

    #     # Validasi parameter wajib
    #     if not date_from or not date_to:
    #         return request.not_found()

    #     domain = [
    #         ('date_order', '>=', date_from),
    #         ('date_order', '<=', date_to),
    #     ]

    #     # if invoice_no:
    #     #     move = request.env['account.move'].sudo().search([('name', '=', invoice_no)], limit=1)
    #     #     if move:
    #     #         domain.append(('account_move', '=', move.id))

    #     # if pos_order_ref:
    #     #     domain.append(('name', '=', pos_order_ref))

    #     orders = request.env['pos.order'].sudo().search(domain)

    #     values = {
    #         'orders': orders,
    #         'date_from': fields.Date.from_string(date_from).strftime('%d/%m/%Y'),
    #         'date_to': fields.Date.from_string(date_to).strftime('%d/%m/%Y'),
    #         'tanggal_cetak': fields.Date.today().strftime("%d %b %Y"),
    #     }
    #     return request.render('report_pos.report_sales_contribution_by_category', values)

    @http.route(['/my/sales/report/contribution_by_category'], type='http', auth="user", website=True)
    def portal_contribution_by_category(self, date_from=None, date_to=None, **kw):
        # ambil data order berdasarkan tanggal
        orders = request.env['sale.order'].sudo().search([
            ('date_order', '>=', date_from),
            ('date_order', '<=', date_to)
        ])

        return request.render("report_pos.portal_contribution_report_template", {
            'date_from': date_from,
            'date_to': date_to,
            'orders': orders,
        })

    @http.route(['/my/sales/report/contribution_by_category/pdf'], type='http', auth="user", website=True)
    def portal_contribution_pdf(self, date_from=None, date_to=None, **kw):
        # ambil data orders
        orders = request.env['sale.order'].sudo().search([
            ('date_order', '>=', date_from),
            ('date_order', '<=', date_to)
        ])

        # render template QWeb jadi HTML
        html = request.env['ir.qweb']._render(
            "report_pos.portal_contribution_report_template",
            {
                'date_from': date_from,
                'date_to': date_to,
                'orders': orders,
            }
        )

        # gunakan report_wkhtmltopdf untuk konversi HTML ke PDF
        pdf = request.env['ir.actions.report']._run_wkhtmltopdf(
            html, landscape=False
        )

        # kirim PDF ke browser
        pdfhttpheaders = [
            ('Content-Type', 'application/pdf'),
            ('Content-Length', len(pdf)),
            ('Content-Disposition', 'attachment; filename="contribution_report.pdf"')
        ]
        return request.make_response(pdf, headers=pdfhttpheaders)
    
    @http.route('/my/sales/report/settlement_end_of_shift', type='http', auth='user', website=True)
    def portal_sales_report_settlement_end_of_shift(self, **kw):
        date_from = kw.get('date_from')
        date_to = kw.get('date_to')

        # Validasi parameter wajib
        if not date_from or not date_to:
            return request.not_found()
        
        domain = []
        if date_from:
            domain.append(('start_date', '>=', date_from))
        if date_to:
            domain.append(('start_date', '<=', date_to))
            
        end_shift = request.env['end.shift'].sudo().search(domain, order='id desc')

        values = {
            'orders': end_shift,
            'date_from': fields.Date.from_string(date_from).strftime('%d/%m/%Y'),
            'date_to': fields.Date.from_string(date_to).strftime('%d/%m/%Y'),
            'tanggal_cetak': fields.Date.today().strftime("%d %b %Y"),
            'backend_url': self.back_to_pos_view(),
            'format_number': self.format_number,  # tambahkan ini
        }
        return request.render('report_pos.report_sales_settlement_end_of_shift', values)
