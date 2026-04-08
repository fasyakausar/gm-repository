import logging
from odoo import models, fields, api
from odoo.exceptions import UserError
import traceback

_logger = logging.getLogger(__name__)


class ReportSaleDetailsInherit(models.AbstractModel):
    _inherit = "report.point_of_sale.report_saledetails"

    def get_sale_details(self, date_start=False, date_stop=False, config_ids=False, session_ids=False):
        """
        Override: filter cash_moves untuk menghilangkan baris
        "Cash difference observed during the counting (Profit) - opening"
        yang muncul karena balance_start di-set manual.
        """
        result = super().get_sale_details(date_start, date_stop, config_ids, session_ids)

        for payment in result.get("payments", []):
            if "cash_moves" in payment:
                _logger.info(
                    f"[ReportSaleDetails] payment='{payment.get('name', '')}' "
                    f"cash='{payment.get('cash', '')}' "
                    f"final_count={payment.get('final_count')} "
                    f"money_counted={payment.get('money_counted')} "
                    f"cash_moves={payment.get('cash_moves')}"
                )

        def _is_opening_difference(name):
            name_lower = name.lower()
            return "difference" in name_lower and "opening" in name_lower

        for payment in result.get("payments", []):
            if "cash_moves" in payment and isinstance(payment["cash_moves"], list):
                before = len(payment["cash_moves"])
                payment["cash_moves"] = [
                    move for move in payment["cash_moves"]
                    if not _is_opening_difference(str(move.get("name", "")))
                ]
                after = len(payment["cash_moves"])
                if before != after:
                    _logger.info(
                        f"[ReportSaleDetails] Filtered {before - after} 'opening difference' "
                        f"cash_move(s) from payment '{payment.get('name', '')}'"
                    )

        return result


class PosSession(models.Model):
    _inherit = 'pos.session'

    is_updated = fields.Boolean(string="Updated", default=False, readonly=True, tracking=True)
    name_session_pos = fields.Char(string="Name Session POS (Odoo Store)", readonly=True)
    id_mc = fields.Char(string="ID MC", default=False)
    vit_edit_start_balance = fields.Char(string="Edit Start Balance", tracking=True)
    vit_edit_end_balance = fields.Char(string="Edit End Balance", tracking=True)

    @api.onchange('vit_edit_start_balance')
    def _onchange_vit_edit_start_balance(self):
        if self.vit_edit_start_balance:
            try:
                new_value = float(self.vit_edit_start_balance.replace(',', '.'))
                current_value = self.cash_register_balance_start or 0.0
                total_value = current_value + new_value
                self.cash_register_balance_start = total_value
                _logger.info(f"💰 balance_start updated: {current_value} + {new_value} = {total_value} for session {self.name}")
            except ValueError:
                _logger.warning(f"⚠️ Invalid value for start balance: {self.vit_edit_start_balance}")
                return {'warning': {'title': 'Invalid Input', 'message': 'Please enter a valid number for Start Balance'}}

    @api.onchange('vit_edit_end_balance')
    def _onchange_vit_edit_end_balance(self):
        if self.vit_edit_end_balance:
            try:
                new_value = float(self.vit_edit_end_balance.replace(',', '.'))
                current_value = self.cash_register_balance_end_real or 0.0
                total_value = current_value + new_value
                self.cash_register_balance_end_real = total_value
                _logger.info(f"💰 balance_end_real updated: {current_value} + {new_value} = {total_value} for session {self.name}")
            except ValueError:
                _logger.warning(f"⚠️ Invalid value for end balance: {self.vit_edit_end_balance}")
                return {'warning': {'title': 'Invalid Input', 'message': 'Please enter a valid number for End Balance'}}

    def get_closing_control_data(self):
        result = super().get_closing_control_data()
        total_modal = sum(
            self.env['end.shift'].search([('session_id', '=', self.id)]).mapped('modal')
        )
        result['total_modal'] = total_modal
        if self.config_id.cash_control and result.get('default_cash_details'):
            result['default_cash_details']['opening'] = total_modal
            cash_payment = result['default_cash_details'].get('payment_amount', 0)
            cash_moves = sum([move['amount'] for move in result['default_cash_details'].get('moves', [])])
            result['default_cash_details']['amount'] = total_modal + cash_payment + cash_moves
            result['default_cash_details']['modal_info'] = {
                'total_modal': total_modal,
                'cash_payments': cash_payment,
                'cash_moves': cash_moves,
                'expected_total': total_modal + cash_payment + cash_moves,
            }
        return result

    def post_closing_cash_details(self, counted_cash):
        self.ensure_one()
        _logger.info(
            f"🔍 post_closing_cash_details CALLED: session={self.name}, "
            f"counted_cash={counted_cash} (type={type(counted_cash).__name__}), "
            f"balance_end_real BEFORE={self.cash_register_balance_end_real}"
        )
        check_closing_session = self._cannot_close_session()
        if check_closing_session:
            _logger.warning(f"⚠️ _cannot_close_session returned: {check_closing_session}")
            return check_closing_session
        if not self.cash_journal_id:
            raise UserError("There is no cash register in this session.")
        safe_counted = float(counted_cash) if counted_cash else 0.0
        self.cash_register_balance_end_real = safe_counted
        _logger.info(
            f"✅ post_closing_cash_details DONE: session={self.name}, "
            f"safe_counted={safe_counted}, "
            f"balance_end_real AFTER={self.cash_register_balance_end_real}, "
            f"balance_start={self.cash_register_balance_start}"
        )
        return {'successful': True}

    def update_closing_balances(self, balance_start=None, balance_end_real=None):
        self.ensure_one()
        if self.state not in ['closing_control', 'opened']:
            raise UserError("Cannot update balances when session is not in closing state.")
        values = {}
        if balance_start is not None:
            values['cash_register_balance_start'] = balance_start
        if balance_end_real is not None:
            values['cash_register_balance_end_real'] = balance_end_real
        if values:
            self.write(values)
        return True

    def action_pos_session_closing_control(self, balancing_account=False, amount_to_balance=0, bank_payment_method_diffs=None):
        bank_payment_method_diffs = bank_payment_method_diffs or {}
        for session in self:
            total_modal = sum(
                self.env['end.shift'].search([('session_id', '=', session.id)]).mapped('modal')
            )
            if (session.config_id.cash_control
                    and total_modal > 0
                    and not session.cash_register_balance_start):
                session.cash_register_balance_start = total_modal
                _logger.info(f"🔐 Session {session.name}: balance_start auto-set to {total_modal}")
            else:
                _logger.info(
                    f"🔐 Session {session.name}: balance_start kept as "
                    f"{session.cash_register_balance_start} (total_modal={total_modal})"
                )
        return super().action_pos_session_closing_control(
            balancing_account, amount_to_balance, bank_payment_method_diffs
        )

    def _pos_ui_models_to_load(self):
        res = super()._pos_ui_models_to_load()
        additional_models = []
        model_checks = [
            'res.partner',
            'res.config.settings',
            'res.company',
            'barcode.config',
            'hr.employee',
            'hr.employee.config.settings',
            'loyalty.card'
        ]
        for model_name in model_checks:
            try:
                if model_name in self.env:
                    self.env[model_name].check_access_rights('read', raise_exception=False)
                    additional_models.append(model_name)
                    _logger.info(f"✅ Added model {model_name} to POS UI models")
            except Exception as e:
                _logger.warning(f"⚠️ Skipping model {model_name}: {e}")
        res += additional_models
        return res

    def _loader_params_pos_order(self):
        result = super()._loader_params_pos_order()
        fields = result['search_params']['fields']
        if 'account_move' not in fields:
            fields.append('account_move')
        return result
    
    def _get_pos_ui_pos_order(self, params):
        orders = super()._get_pos_ui_pos_order(params)
        
        # DEBUG: cek field yang tersedia di order pertama
        if orders:
            sample = orders[0]
            _logger.info(f"🔍 pos.order sample keys: {list(sample.keys())}")
            _logger.info(f"🔍 account_move raw: {sample.get('account_move')}")
            _logger.info(f"🔍 pos_reference: {sample.get('pos_reference')}")
        
        move_ids = [
            o['account_move'][0] if isinstance(o.get('account_move'), (list, tuple)) else o.get('account_move')
            for o in orders if o.get('account_move')
        ]
        move_ids = [m for m in move_ids if isinstance(m, int)]
        
        _logger.info(f"🔍 Total orders: {len(orders)}, orders with account_move: {len(move_ids)}")
        
        move_map = {}
        if move_ids:
            for mv in self.env['account.move'].sudo().browse(move_ids):
                move_map[mv.id] = mv.name
                _logger.info(f"✅ Move: {mv.id} → {mv.name}")
        
        for order in orders:
            am = order.get('account_move')
            mid = am[0] if isinstance(am, (list, tuple)) else am
            order['account_move_name'] = move_map.get(mid, '') if isinstance(mid, int) else ''
            if order['account_move_name']:
                _logger.info(f"✅ Order {order.get('name')} → invoice: {order['account_move_name']}")
            else:
                _logger.warning(f"⚠️ Order {order.get('name')} → NO invoice (account_move={am})")
        
        return orders

    # ── Payment Method ───────────────────────────────────────────────────────

    def _loader_params_pos_payment_method(self):
        result = super()._loader_params_pos_payment_method()
        fields = result['search_params']['fields']
        if 'gm_is_card' not in fields:
            fields.append('gm_is_card')
        if 'gm_is_dp' not in fields:
            fields.append('gm_is_dp')
        # Tambahkan journal_id agar tipe jurnal bisa diakses
        if 'journal_id' not in fields:
            fields.append('journal_id')
        return result

    def _get_pos_ui_pos_payment_method(self, params):
        payment_methods = super()._get_pos_ui_pos_payment_method(params)
        
        # Ambil semua journal_id yang terkait
        journal_ids = []
        for pm in payment_methods:
            jid = pm.get('journal_id')
            if jid and isinstance(jid, (list, tuple)) and len(jid) > 0:
                journal_ids.append(jid[0])
        
        # Load journal data (type, name)
        journals = {}
        if journal_ids:
            for journal in self.env['account.journal'].sudo().browse(journal_ids):
                journals[journal.id] = {'name': journal.name, 'type': journal.type}
        
        # Tambahkan journal_type ke setiap payment method
        for pm in payment_methods:
            jid = pm.get('journal_id')
            if jid and isinstance(jid, (list, tuple)) and len(jid) > 0:
                jid_val = jid[0]
                if jid_val in journals:
                    pm['journal_type'] = journals[jid_val]['type']
                else:
                    pm['journal_type'] = 'other'
            else:
                pm['journal_type'] = 'other'
        
        # Logging (opsional)
        cash_methods = [pm for pm in payment_methods if pm.get('journal_type') == 'cash']
        non_cash_methods = [pm for pm in payment_methods if pm.get('journal_type') != 'cash']
        _logger.info(f"💵 Cash methods: {len(cash_methods)}, Non-cash methods: {len(non_cash_methods)}")
        
        return payment_methods

    def _pos_ui_pos_payment_method(self, params):
        return self._get_pos_ui_pos_payment_method(params)

    # ── Company ──────────────────────────────────────────────────────────────

    def _loader_params_res_company(self):
        return {
            'search_params': {
                'domain': [('id', '=', self.env.company.id)],
                'fields': ['id', 'logo', 'name', 'street', 'street2', 'city', 'zip', 'country_id', 'vat'],
            }
        }

    def _get_pos_ui_res_company(self, params):
        try:
            records = self.env['res.company'].search_read(
                params['search_params']['domain'],
                params['search_params']['fields']
            )
            # Bulk-fetch country names
            country_ids = [r['country_id'] for r in records if isinstance(r.get('country_id'), int)]
            country_map = {}
            if country_ids:
                for c in self.env['res.country'].browse(country_ids):
                    country_map[c.id] = c.name
            for rec in records:
                val = rec.get('country_id')
                if isinstance(val, int):
                    rec['country_id'] = [val, country_map.get(val, '')] if val in country_map else False
                elif isinstance(val, (list, tuple)) and len(val) >= 2:
                    rec['country_id'] = [int(val[0]), str(val[1])]
            _logger.info("✅ Loaded res.company")
            return records
        except Exception as e:
            _logger.error(f"❌ Error loading res.company: {e}")
            return []

    def _pos_ui_res_company(self, params):
        return self._get_pos_ui_res_company(params)

    # ── HR Employee ──────────────────────────────────────────────────────────

    def _loader_params_hr_employee(self):
        basic_ids = self.config_id.basic_employee_ids.ids
        advanced_ids = self.config_id.advanced_employee_ids.ids
        allowed_ids = list(set(basic_ids + advanced_ids))
        domain = [('id', 'in', allowed_ids)] if allowed_ids else [('id', '=', 0)]
        _logger.info(
            f"🔍 POS '{self.config_id.name}': "
            f"basic_ids={basic_ids}, advanced_ids={advanced_ids}, allowed={allowed_ids}"
        )
        return {
            'search_params': {
                'domain': domain,
                'fields': [
                    'id', 'name', 'work_email', 'mobile_phone',
                    'job_title', 'pin', 'image_128',
                    'is_cashier', 'is_sales_person', 'is_pic',
                    'is_integrated', 'is_sales', 'vit_employee_code',
                ],
            }
        }

    def _get_pos_ui_hr_employee(self, params):
        try:
            if 'hr.employee' not in self.env:
                _logger.warning("⚠️ Model hr.employee not found")
                return []
            records = self.env['hr.employee'].search_read(
                params['search_params']['domain'],
                params['search_params']['fields'],
                limit=500
            )
            _logger.info(
                f"✅ Loaded {len(records)} hr.employee records "
                f"for POS '{self.config_id.name}' (ID: {self.config_id.id})"
            )
            return records
        except Exception as e:
            _logger.error(f"❌ Error loading hr.employee: {e}")
            return []

    def _pos_ui_hr_employee(self, params):
        return self._get_pos_ui_hr_employee(params)

    def _loader_params_hr_employee_config_settings(self):
        return {
            'search_params': {
                'domain': [],
                'fields': ['id', 'employee_id', 'is_cashier'],
            }
        }

    def _get_pos_ui_hr_employee_config_settings(self, params):
        try:
            if 'hr.employee.config.settings' not in self.env:
                _logger.warning("⚠️ Model hr.employee.config.settings not found")
                return []
            records = self.env['hr.employee.config.settings'].search_read(
                params['search_params']['domain'],
                params['search_params']['fields'],
                limit=500
            )
            # Bulk-fetch employee names
            emp_ids = [r['employee_id'] for r in records if isinstance(r.get('employee_id'), int)]
            emp_map = {}
            if emp_ids:
                for e in self.env['hr.employee'].browse(emp_ids):
                    emp_map[e.id] = e.name
            for rec in records:
                val = rec.get('employee_id')
                if isinstance(val, int):
                    rec['employee_id'] = [val, emp_map.get(val, '')] if val in emp_map else False
                elif isinstance(val, (list, tuple)) and len(val) >= 2:
                    rec['employee_id'] = [int(val[0]), str(val[1])]
            _logger.info(f"✅ Loaded {len(records)} hr.employee.config.settings")
            return records
        except Exception as e:
            _logger.error(f"❌ Error loading hr.employee.config.settings: {e}")
            return []

    def _pos_ui_hr_employee_config_settings(self, params):
        return self._get_pos_ui_hr_employee_config_settings(params)

    # # ── Multiple Barcode ─────────────────────────────────────────────────────

    # def _loader_params_multiple_barcode(self):
    #     return {
    #         'search_params': {
    #             'domain': [],
    #             'fields': ['id', 'barcode', 'product_id'],
    #         }
    #     }

    # def _get_pos_ui_multiple_barcode(self, params):
    #     try:
    #         if 'multiple.barcode' not in self.env:
    #             _logger.warning("⚠️ Model multiple.barcode not found")
    #             return []
    #         records = self.env['multiple.barcode'].search_read(
    #             params['search_params']['domain'],
    #             params['search_params']['fields'],
    #             limit=5000
    #         )
    #         # Bulk-fetch product display_name
    #         product_ids = [r['product_id'] for r in records if isinstance(r.get('product_id'), int)]
    #         product_map = {}
    #         if product_ids:
    #             for p in self.env['product.product'].browse(product_ids):
    #                 product_map[p.id] = p.display_name
    #         for rec in records:
    #             val = rec.get('product_id')
    #             if isinstance(val, int):
    #                 rec['product_id'] = [val, product_map.get(val, '')] if val in product_map else False
    #             elif isinstance(val, (list, tuple)) and len(val) >= 2:
    #                 rec['product_id'] = [int(val[0]), str(val[1])]
    #         _logger.info(f"✅ Loaded {len(records)} multiple.barcode records")
    #         return records
    #     except Exception as e:
    #         _logger.error(f"❌ Error loading multiple.barcode: {e}")
    #         return []

    # def _pos_ui_multiple_barcode(self, params):
    #     return self._get_pos_ui_multiple_barcode(params)

    # ── Barcode Config ───────────────────────────────────────────────────────

    def _loader_params_barcode_config(self):
        return {
            'search_params': {
                'domain': [],
                'fields': [
                    'digit_awal', 'digit_akhir', 'prefix_timbangan',
                    'panjang_barcode',
                ],
            }
        }

    def _get_pos_ui_barcode_config(self, params):
        try:
            if 'barcode.config' not in self.env:
                _logger.warning("⚠️ Model barcode.config not found")
                return []
            records = self.env['barcode.config'].search_read(
                params['search_params']['domain'],
                params['search_params']['fields'],
                limit=1
            )
            _logger.info("✅ Loaded barcode.config")
            return records
        except Exception as e:
            _logger.error(f"❌ Error loading barcode.config: {e}")
            return []

    def _pos_ui_barcode_config(self, params):
        return self._get_pos_ui_barcode_config(params)

    # ── Cashier Log ──────────────────────────────────────────────────────────

    # def _loader_params_pos_cashier_log(self):
    #     return {
    #         'search_params': {
    #             'domain': [('session_id', '=', self.id)],
    #             'fields': ['id', 'session_id', 'employee_id', 'state', 'timestamp'],
    #         }
    #     }

    # def _get_pos_ui_pos_cashier_log(self, params):
    #     try:
    #         if 'pos.cashier.log' not in self.env:
    #             _logger.warning("⚠️ Model pos.cashier.log not found")
    #             return []
    #         records = self.env['pos.cashier.log'].search_read(
    #             params['search_params'].get('domain', []),
    #             params['search_params']['fields']
    #         )
    #         # Bulk-fetch employee & session names
    #         emp_ids = [r['employee_id'] for r in records if isinstance(r.get('employee_id'), int)]
    #         sess_ids = [r['session_id'] for r in records if isinstance(r.get('session_id'), int)]
    #         emp_map = {e.id: e.name for e in self.env['hr.employee'].browse(emp_ids)} if emp_ids else {}
    #         sess_map = {s.id: s.name for s in self.env['pos.session'].browse(sess_ids)} if sess_ids else {}
    #         for rec in records:
    #             eid = rec.get('employee_id')
    #             if isinstance(eid, int):
    #                 rec['employee_id'] = [eid, emp_map.get(eid, '')] if eid in emp_map else False
    #             elif isinstance(eid, (list, tuple)) and len(eid) >= 2:
    #                 rec['employee_id'] = [int(eid[0]), str(eid[1])]
    #             sid = rec.get('session_id')
    #             if isinstance(sid, int):
    #                 rec['session_id'] = [sid, sess_map.get(sid, '')] if sid in sess_map else False
    #             elif isinstance(sid, (list, tuple)) and len(sid) >= 2:
    #                 rec['session_id'] = [int(sid[0]), str(sid[1])]
    #         _logger.info(f"✅ Loaded {len(records)} pos.cashier.log records")
    #         return records
    #     except Exception as e:
    #         _logger.error(f"❌ Error loading pos.cashier.log: {e}")
    #         return []

    # def _pos_ui_pos_cashier_log(self, params):
    #     return self._get_pos_ui_pos_cashier_log(params)

    # ── Config Settings ──────────────────────────────────────────────────────

    def _loader_params_res_config_settings(self):
        return {'search_params': {'fields': []}}

    def _get_pos_ui_res_config_settings(self, params):
        try:
            cfg = self.config_id

            # ✅ Debug — log semua nilai dari pos.config
            _logger.info(f"🔍 POS Config ID: {cfg.id}, Name: {cfg.name}")
            _logger.info(f"   manager_validation     = {cfg.manager_validation}")
            _logger.info(f"   enable_auto_rounding   = {cfg.enable_auto_rounding}")
            _logger.info(f"   rounding_value         = {cfg.rounding_value}")
            _logger.info(f"   rounding_product_id    = {cfg.rounding_product_id}")
            _logger.info(f"   validate_discount      = {cfg.validate_discount}")
            _logger.info(f"   validate_payment       = {cfg.validate_payment}")
            _logger.info(f"   validate_price_change  = {cfg.validate_price_change}")
            _logger.info(f"   validate_refund        = {cfg.validate_refund}")
            _logger.info(f"   manager_id             = {cfg.manager_id}")

            # ✅ AMAN — gunakan exists() untuk Many2one
            manager = cfg.manager_id if cfg.manager_id and cfg.manager_id.exists() else None
            rounding_product = cfg.rounding_product_id if cfg.rounding_product_id and cfg.rounding_product_id.exists() else None

            ir_config = self.env['ir.config_parameter'].sudo()
            total_digits_raw = ir_config.get_param('reward_point_total_digits', '16')
            decimal_digits_raw = ir_config.get_param('reward_point_decimal_digits', '4')

            result = {
                'manager_validation': cfg.manager_validation or False,
                'validate_discount_amount': cfg.validate_discount_amount or False,
                'validate_end_shift': cfg.validate_end_shift or False,
                'validate_closing_pos': cfg.validate_closing_pos or False,
                'validate_order_line_deletion': cfg.validate_order_line_deletion or False,
                'validate_discount': cfg.validate_discount or False,
                'validate_price_change': cfg.validate_price_change or False,
                'validate_order_deletion': cfg.validate_order_deletion or False,
                'validate_add_remove_quantity': cfg.validate_add_remove_quantity or False,
                'validate_payment': cfg.validate_payment or False,
                'validate_refund': cfg.validate_refund or False,
                'validate_close_session': cfg.validate_close_session or False,
                'validate_void_sales': cfg.validate_void_sales or False,
                'validate_member_schedule': cfg.validate_member_schedule or False,
                'validate_cash_drawer': cfg.validate_cash_drawer or False,
                'validate_reprint_receipt': cfg.validate_reprint_receipt or False,
                'validate_reprint_invoice': cfg.validate_reprint_invoice or False,
                'validate_discount_button': cfg.validate_discount_button or False,
                'one_time_password': cfg.one_time_password or False,
                'manager_pin': manager.pin if manager else '',
                'manager_name': manager.name if manager else '',
                'enable_auto_rounding': cfg.enable_auto_rounding or False,
                'rounding_value': cfg.rounding_value or 100,
                'rounding_product_id': {
                    'id': rounding_product.id,
                    'name': rounding_product.name,
                } if rounding_product else None,
                'reward_point_total_digits': int(total_digits_raw) if str(total_digits_raw).isdigit() else 16,
                'reward_point_decimal_digits': int(decimal_digits_raw) if str(decimal_digits_raw).isdigit() else 4,
            }

            _logger.info(f"✅ Loaded res.config.settings for POS '{cfg.name}'")
            return [result]

        except Exception as e:
            _logger.error(f"❌ Error loading res.config.settings: {e}")
            _logger.error(traceback.format_exc())
            return [{
                'manager_validation': False,
                'validate_discount_amount': False,
                'validate_end_shift': False,
                'validate_closing_pos': False,
                'validate_order_line_deletion': False,
                'validate_discount': False,
                'validate_price_change': False,
                'validate_order_deletion': False,
                'validate_add_remove_quantity': False,
                'validate_payment': False,
                'validate_refund': False,
                'validate_close_session': False,
                'validate_void_sales': False,
                'validate_member_schedule': False,
                'validate_cash_drawer': False,
                'validate_reprint_receipt': False,
                'validate_reprint_invoice': False,
                'validate_discount_button': False,
                'one_time_password': False,
                'manager_pin': '',
                'manager_name': '',
                'enable_auto_rounding': False,
                'rounding_value': 100,
                'rounding_product_id': None,
                'reward_point_total_digits': 16,
                'reward_point_decimal_digits': 4,
            }]

    def _pos_ui_res_config_settings(self, params):
        return self._get_pos_ui_res_config_settings(params)

    # ── Product ──────────────────────────────────────────────────────────────

    def _loader_params_product_product(self):
        result = super()._loader_params_product_product()
        for field in ('gm_is_pelunasan', 'gm_is_rounding', 'gm_is_dp', 'gm_is_fixed_price'):
            if field not in result['search_params']['fields']:
                result['search_params']['fields'].append(field)
                _logger.info(f"✅ Added {field} to product.product loader")
        _logger.info(f"📦 Product loader fields: {result['search_params']['fields']}")
        return result

    def _get_pos_ui_product_product(self, params):
        products = super()._get_pos_ui_product_product(params)
        pelunasan_products = [p for p in products if p.get('gm_is_pelunasan') is True]
        normal_products = [p for p in products if p.get('gm_is_pelunasan') is not True]
        _logger.info(f"📊 Product loading summary:")
        _logger.info(f"   Total products: {len(products)}")
        _logger.info(f"   Pelunasan products: {len(pelunasan_products)}")
        _logger.info(f"   Normal products: {len(normal_products)}")
        if pelunasan_products:
            _logger.info("🎯 Pelunasan products loaded:")
            for p in pelunasan_products[:10]:
                _logger.info(
                    f"   - {p.get('display_name')} "
                    f"(ID: {p.get('id')}, gm_is_pelunasan: {p.get('gm_is_pelunasan')})"
                )
            if len(pelunasan_products) > 10:
                _logger.info(f"   ... and {len(pelunasan_products) - 10} more")
        else:
            _logger.warning("⚠️ No pelunasan products found in loaded data!")
        sample_product = products[0] if products else None
        if sample_product:
            has_field = 'gm_is_pelunasan' in sample_product
            _logger.info(f"✅ Field 'gm_is_pelunasan' {'FOUND' if has_field else 'NOT FOUND'} in product data")
            if not has_field:
                _logger.error("❌ CRITICAL: Field 'gm_is_pelunasan' missing from product data!")
        return products

    def _pos_ui_product_product(self, params):
        return self._get_pos_ui_product_product(params)
    
    def _loader_params_loyalty_card(self):
        return {
            'search_params': {
                'domain': [],
                'fields': ['id', 'code', 'points', 'partner_id', 'program_id'],
            }
        }

    def _get_pos_ui_loyalty_card(self, params):
        cards = self.env['loyalty.card'].sudo().search_read(**params['search_params'])
        _logger.info(f"🎁 Loyalty cards: {len(cards)}")
        partner_ids = []
        for card in cards:
            _logger.info(f"   ID {card['id']}: points={card.get('points')}")
            pid = card.get('partner_id')
            if pid:
                if isinstance(pid, (list, tuple)):
                    partner_ids.append(pid[0])  # extract ID
                else:
                    partner_ids.append(pid)
        partner_map = {p.id: p.name for p in self.env['res.partner'].sudo().browse(partner_ids)}
        for card in cards:
            pid = card.get('partner_id')
            if pid:
                if isinstance(pid, (list, tuple)):
                    pid_val = pid[0]
                else:
                    pid_val = pid
                card['partner_id'] = [pid_val, partner_map.get(pid_val, '')]
        return cards

    # ── Partner ──────────────────────────────────────────────────────────────

    def _loader_params_res_partner(self):
        # ✅ Ganti self.env.company.id → self.company_id.id
        current_company_id = self.company_id.id
        base_domain = [
            ('active', '=', True),
            ('gm_bp_type', '=', 'customer'),
            '|',
            ('company_id', '=', current_company_id),
            ('company_id', '=', False),
        ]
        if self.config_id.default_partner_id:
            default_partner_id = self.config_id.default_partner_id.id
            domain = [
                '|',
                ('id', '=', default_partner_id),
                '&', '&',
                ('active', '=', True),
                ('gm_bp_type', '=', 'customer'),
                '|',
                ('company_id', '=', current_company_id),
                ('company_id', '=', False),
            ]
        else:
            domain = base_domain
        _logger.info(f"🔍 _loader_params_res_partner: company={current_company_id}, domain={domain}")
        return {
            'search_params': {
                'domain': domain,
                'fields': [
                    'name', 'street', 'city', 'state_id', 'country_id',
                    'vat', 'lang', 'phone', 'zip', 'mobile', 'email',
                    'barcode', 'write_date', 'property_account_position_id',
                    'property_product_pricelist', 'parent_name', 'category_id',
                    'vit_customer_group', 'gm_bp_type', 'company_id',
                ],
                'limit': 5000,
                'order': 'name ASC',
            }
        }

    def _get_pos_ui_res_partner(self, params):
        try:
            # ✅ Ganti self.env.company.id → self.company_id.id
            current_company_id = self.company_id.id

            partners = self.env['res.partner'].sudo().search_read(
                params['search_params'].get('domain', []),
                params['search_params']['fields'],
                limit=params['search_params'].get('limit', 10000),
                order=params['search_params'].get('order', 'name ASC'),
            )
            _logger.info(f"📊 Raw partners loaded: {len(partners)} (company={current_company_id})")

            # ── Dedup: company-specific > global ─────────────────────────────
            company_specific = {}
            global_only = {}
            for p in partners:
                cid = p.get('company_id')
                if isinstance(cid, (list, tuple)):
                    cid = cid[0]
                name_key = (p.get('name') or '').strip().lower()
                if cid == current_company_id:
                    company_specific[name_key] = p
                else:
                    if name_key not in global_only:
                        global_only[name_key] = p

            final_partners = list(company_specific.values())
            skipped = 0
            for name_key, p in global_only.items():
                if name_key not in company_specific:
                    final_partners.append(p)
                else:
                    skipped += 1
                    _logger.info(
                        f"[dedup] Skip global '{p.get('name')}' (id={p['id']}) "
                        f"— sudah ada versi company-specific"
                    )

            final_partners.sort(key=lambda x: (x.get('name') or '').lower())
            _logger.info(
                f"✅ After dedup: {len(final_partners)} partners "
                f"(company_specific={len(company_specific)}, "
                f"global_added={len(global_only) - skipped}, global_skipped={skipped})"
            )

            # ── Force-load default customer ───────────────────────────────────
            if self.config_id.default_partner_id:
                default_id = self.config_id.default_partner_id.id
                default_name = self.config_id.default_partner_id.name
                if not any(p['id'] == default_id for p in final_partners):
                    _logger.warning(
                        f"⚠️ Default customer '{default_name}' (ID: {default_id}) "
                        f"tidak ter-load! Force-loading..."
                    )
                    fallback = self.env['res.partner'].sudo().search_read(
                        [('id', '=', default_id)],
                        params['search_params']['fields'],
                        limit=1
                    )
                    if fallback:
                        final_partners.insert(0, fallback[0])
                        _logger.info(f"✅ Force-loaded default customer: '{default_name}'")
                    else:
                        _logger.error(f"❌ Partner ID {default_id} tidak ditemukan di database!")

            # ── Bulk pre-fetch semua relational IDs sekaligus ─────────────────
            state_ids, country_ids, fiscal_ids, pricelist_ids_raw = set(), set(), set(), set()
            for p in final_partners:
                if isinstance(p.get('state_id'), int):
                    state_ids.add(p['state_id'])
                if isinstance(p.get('country_id'), int):
                    country_ids.add(p['country_id'])
                if isinstance(p.get('property_account_position_id'), int):
                    fiscal_ids.add(p['property_account_position_id'])
                if isinstance(p.get('property_product_pricelist'), int):
                    pricelist_ids_raw.add(p['property_product_pricelist'])

            state_map = {r.id: r.name for r in self.env['res.country.state'].sudo().browse(list(state_ids))} if state_ids else {}
            country_map = {r.id: r.name for r in self.env['res.country'].sudo().browse(list(country_ids))} if country_ids else {}
            fiscal_map = {r.id: r.name for r in self.env['account.fiscal.position'].sudo().browse(list(fiscal_ids))} if fiscal_ids else {}

            # ✅ Kunci perbaikan: filter pricelist berdasarkan company_id session
            valid_pricelist_ids = set(
                self.env['product.pricelist'].sudo().search([
                    ('company_id', 'in', [False, current_company_id])
                ]).ids
            )
            pricelist_map = {
                r.id: r.name
                for r in self.env['product.pricelist'].sudo().browse(
                    list(pricelist_ids_raw & valid_pricelist_ids)
                )
            } if pricelist_ids_raw else {}

            # ── Apply relational fields ke setiap partner ─────────────────────
            for partner in final_partners:
                try:
                    # category_id (Many2many) — keep as list of ints
                    if isinstance(partner.get('category_id'), list):
                        partner['category_id'] = [
                            int(cid) for cid in partner['category_id']
                            if str(cid).isdigit()
                        ]

                    # state_id
                    val = partner.get('state_id')
                    if isinstance(val, int):
                        partner['state_id'] = [val, state_map[val]] if val in state_map else False
                    elif isinstance(val, (list, tuple)) and len(val) >= 2:
                        partner['state_id'] = [int(val[0]), str(val[1])]

                    # country_id
                    val = partner.get('country_id')
                    if isinstance(val, int):
                        partner['country_id'] = [val, country_map[val]] if val in country_map else False
                    elif isinstance(val, (list, tuple)) and len(val) >= 2:
                        partner['country_id'] = [int(val[0]), str(val[1])]

                    # property_account_position_id
                    val = partner.get('property_account_position_id')
                    if isinstance(val, int):
                        partner['property_account_position_id'] = [val, fiscal_map[val]] if val in fiscal_map else False
                    elif isinstance(val, (list, tuple)) and len(val) >= 2:
                        partner['property_account_position_id'] = [int(val[0]), str(val[1])]

                    # property_product_pricelist
                    val = partner.get('property_product_pricelist')
                    if isinstance(val, int):
                        if val not in valid_pricelist_ids:
                            partner['property_product_pricelist'] = False
                        else:
                            partner['property_product_pricelist'] = [val, pricelist_map.get(val, '')] if val in pricelist_map else False
                    elif isinstance(val, (list, tuple)) and len(val) >= 2:
                        partner['property_product_pricelist'] = [int(val[0]), str(val[1])]

                except Exception as e:
                    _logger.warning(f"⚠️ Error processing partner id={partner.get('id')}: {e}")

            _logger.info(f"✅ FINAL: {len(final_partners)} res.partner untuk company {current_company_id}")
            return final_partners

        except Exception as e:
            _logger.error(f"❌ CRITICAL in _get_pos_ui_res_partner: {e}")
            _logger.error(traceback.format_exc())
            return []

    def _pos_ui_res_partner(self, params):
        return self._get_pos_ui_res_partner(params)