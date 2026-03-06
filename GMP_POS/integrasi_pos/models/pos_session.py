import logging
from datetime import datetime, timedelta
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
        Nilai counted, final_count, money_difference tetap dari super().
        """
        result = super().get_sale_details(date_start, date_stop, config_ids, session_ids)

        # ── DEBUG: log semua cash_moves dari super() ─────────────────────────
        for payment in result.get("payments", []):
            if "cash_moves" in payment:
                _logger.info(
                    f"[ReportSaleDetails] payment='{payment.get('name', '')}' "
                    f"cash='{payment.get('cash', '')}' "
                    f"final_count={payment.get('final_count')} "
                    f"money_counted={payment.get('money_counted')} "
                    f"cash_moves={payment.get('cash_moves')}"
                )

        # Hilangkan cash_move yang merupakan "difference - opening" saja.
        # Baris ini muncul karena Odoo membuat entry selisih saat balance_start
        # di-set berbeda dari sesi sebelumnya.
        # JANGAN filter "Cash Opening" — itu adalah baris saldo awal yang valid.
        def _is_opening_difference(name):
            name_lower = name.lower()
            # Hanya filter jika mengandung "difference" DAN "opening"
            return (
                "difference" in name_lower
                and "opening" in name_lower
            )

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
        """
        Dipanggil dari UI saat user klik Close.
        counted_cash = nilai yang diinput user di field Counted.
        HANYA update cash_register_balance_end_real.
        """
        self.ensure_one()

        # ── LOG AWAL ────────────────────────────────────────────────────
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

        # Pastikan counted_cash adalah float valid
        safe_counted = float(counted_cash) if counted_cash else 0.0
        self.cash_register_balance_end_real = safe_counted

        # ── LOG AKHIR ────────────────────────────────────────────────────
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
        """
        Override saat transisi ke closing_control.
        balance_start hanya di-set dari total_modal jika BELUM ada nilai
        (yaitu saat pertama kali sesi dibuka tanpa input manual).
        """
        bank_payment_method_diffs = bank_payment_method_diffs or {}
        for session in self:
            total_modal = sum(
                self.env['end.shift'].search([('session_id', '=', session.id)]).mapped('modal')
            )
            # Hanya update jika cash_control aktif, total_modal > 0,
            # DAN balance_start belum di-set secara manual (masih 0)
            if (session.config_id.cash_control
                    and total_modal > 0
                    and not session.cash_register_balance_start):
                session.cash_register_balance_start = total_modal
                _logger.info(
                    f"🔐 Session {session.name}: balance_start auto-set to {total_modal}"
                )
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
        
        # Only add models that exist and are properly configured
        additional_models = []
        
        # Check if each model exists before adding
        model_checks = [
            'loyalty.program',
            'loyalty.program.schedule', 
            'loyalty.member',
            'loyalty.reward',
            'loyalty.rule',
            'res.partner',
            'res.config.settings',
            'res.company',
            'barcode.config',
            'hr.employee',
            'hr.employee.config.settings',
        ]
        
        for model_name in model_checks:
            try:
                if model_name in self.env:
                    # Test if model is accessible
                    self.env[model_name].check_access_rights('read', raise_exception=False)
                    additional_models.append(model_name)
                    _logger.info(f"✅ Added model {model_name} to POS UI models")
            except Exception as e:
                _logger.warning(f"⚠️ Skipping model {model_name}: {e}")
        
        res += additional_models
        return res

    # def _loader_params_pos_order_line(self):
    #     return {
    #         'search_params': {
    #             'domain': [],
    #             'fields': [
    #                 'id',
    #                 'order_id',
    #                 'product_id', 
    #                 'qty',
    #                 'price_unit',
    #                 'price_subtotal',
    #                 'price_subtotal_incl',
    #                 'discount',
    #                 'line_number',
    #             ],
    #         }
    #     }

    # def _get_pos_ui_pos_order_line(self, params):
    #     try:
    #         records = self.env['pos.order.line'].search_read(
    #             params['search_params'].get('domain', []),
    #             params['search_params']['fields'],
    #             limit=1000  # Add limit to prevent timeout
    #         )
            
    #         # Process relational fields
    #         for rec in records:
    #             # Handle order_id
    #             if rec.get('order_id'):
    #                 if isinstance(rec['order_id'], int):
    #                     order = self.env['pos.order'].browse(rec['order_id'])
    #                     rec['order_id'] = [rec['order_id'], order.name if order.exists() else '']
    #                 elif isinstance(rec['order_id'], list) and len(rec['order_id']) >= 2:
    #                     rec['order_id'] = [int(rec['order_id'][0]), str(rec['order_id'][1])]
                
    #             # Handle product_id  
    #             if rec.get('product_id'):
    #                 if isinstance(rec['product_id'], int):
    #                     product = self.env['product.product'].browse(rec['product_id'])
    #                     rec['product_id'] = [rec['product_id'], product.display_name if product.exists() else '']
    #                 elif isinstance(rec['product_id'], list) and len(rec['product_id']) >= 2:
    #                     rec['product_id'] = [int(rec['product_id'][0]), str(rec['product_id'][1])]
                    
    #             # Ensure line_number is properly set
    #             if 'line_number' not in rec or not rec['line_number']:
    #                 rec['line_number'] = 1
                    
    #         _logger.info(f"✅ Loaded {len(records)} pos.order.line records")
    #         return records
    #     except Exception as e:
    #         _logger.error(f"❌ Error loading pos.order.line: {e}")
    #         return []

    # def _pos_ui_pos_order_line(self, params):
    #     return self._get_pos_ui_pos_order_line(params)

    def _loader_params_pos_payment_method(self):
        """
        Override untuk menambahkan gm_is_card field
        """
        result = super()._loader_params_pos_payment_method()
        
        # Tambahkan gm_is_card ke fields jika belum ada
        if 'gm_is_card' not in result['search_params']['fields']:
            result['search_params']['fields'].append('gm_is_card')
            _logger.info("✅ Added gm_is_card to pos.payment.method loader")

        if 'gm_is_dp' not in result['search_params']['fields']:
            result['search_params']['fields'].append('gm_is_dp')
            _logger.info("✅ Added gm_is_dp to pos.payment.method loader")
        
        return result

    def _get_pos_ui_pos_payment_method(self, params):
        """
        Override untuk logging payment method dengan gm_is_card
        """
        payment_methods = super()._get_pos_ui_pos_payment_method(params)
        
        # Log payment methods dengan gm_is_card
        card_methods = [pm for pm in payment_methods if pm.get('gm_is_card')]
        non_card_methods = [pm for pm in payment_methods if not pm.get('gm_is_card')]

        dp_methods = [pm for pm in payment_methods if pm.get('gm_is_dp')]
    
        if dp_methods:
            _logger.info(f"💰 DP Payment Methods (gm_is_dp=True):")
            for pm in dp_methods:
                _logger.info(f"   - {pm.get('name')} (ID: {pm.get('id')})")
        
        _logger.info(f"📊 Payment Method Loading Summary:")
        _logger.info(f"   Total payment methods: {len(payment_methods)}")
        _logger.info(f"   Card methods (gm_is_card=True): {len(card_methods)}")
        _logger.info(f"   Non-card methods: {len(non_card_methods)}")
        
        if card_methods:
            _logger.info(f"💳 Card payment methods:")
            for pm in card_methods:
                _logger.info(f"   - {pm.get('name')} (ID: {pm.get('id')}, gm_is_card: True)")
        
        return payment_methods
    
    def _pos_ui_pos_payment_method(self, params):
        return self._get_pos_ui_pos_payment_method(params)
    
    def _loader_params_res_company(self):
        return {
            'search_params': {
                'domain': [('id', '=', self.env.company.id)],
                'fields': [
                    'id', 'logo', 'name', 'street', 'street2', 'city', 'zip', 'country_id', 'vat', 
                ],
            }
        }

    def _get_pos_ui_res_company(self, params):
        try:
            records = self.env['res.company'].search_read(
                params['search_params']['domain'],
                params['search_params']['fields']
            )
            
            # Process relational fields
            for rec in records:
                if rec.get('country_id'):
                    if isinstance(rec['country_id'], int):
                        country = self.env['res.country'].browse(rec['country_id'])
                        rec['country_id'] = [rec['country_id'], country.name if country.exists() else '']
                    elif isinstance(rec['country_id'], list) and len(rec['country_id']) >= 2:
                        rec['country_id'] = [int(rec['country_id'][0]), str(rec['country_id'][1])]
                        
            _logger.info(f"✅ Loaded res.company")
            return records
        except Exception as e:
            _logger.error(f"❌ Error loading res.company: {e}")
            return []

    def _pos_ui_res_company(self, params):
        return self._get_pos_ui_res_company(params)
    
    def _loader_params_hr_employee(self):
        """Load HR employees for salesperson selection"""
        return {
            'search_params': {
                'domain': [],
                'fields': ['id', 'name', 'work_email', 'mobile_phone', 'job_title', 'pin', 'image_128'],
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
            _logger.info(f"✅ Loaded {len(records)} hr.employee records")
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

            # Convert relational fields to [id, name]
            for rec in records:
                if rec.get('employee_id'):
                    if isinstance(rec['employee_id'], list) and len(rec['employee_id']) >= 2:
                        rec['employee_id'] = [int(rec['employee_id'][0]), str(rec['employee_id'][1])]
                    elif isinstance(rec['employee_id'], int):
                        employee = self.env['hr.employee'].browse(rec['employee_id'])
                        rec['employee_id'] = [rec['employee_id'], employee.name if employee.exists() else '']
                        
            _logger.info(f"✅ Loaded {len(records)} hr.employee.config.settings")
            return records
        except Exception as e:
            _logger.error(f"❌ Error loading hr.employee.config.settings: {e}")
            return []

    def _pos_ui_hr_employee_config_settings(self, params):
        return self._get_pos_ui_hr_employee_config_settings(params)

    def _loader_params_multiple_barcode(self):
        return {
            'search_params': {
                'domain': [],
                'fields': ['id', 'barcode', 'product_id'],
            }
        }

    def _get_pos_ui_multiple_barcode(self, params):
        try:
            if 'multiple.barcode' not in self.env:
                _logger.warning("⚠️ Model multiple.barcode not found")
                return []
                
            records = self.env['multiple.barcode'].search_read(
                params['search_params']['domain'],
                params['search_params']['fields'],
                limit=5000
            )
            
            for rec in records:
                if rec.get('product_id'):
                    if isinstance(rec['product_id'], list) and len(rec['product_id']) >= 2:
                        rec['product_id'] = [int(rec['product_id'][0]), str(rec['product_id'][1])]
                    elif isinstance(rec['product_id'], int):
                        product = self.env['product.product'].browse(rec['product_id'])
                        rec['product_id'] = [rec['product_id'], product.display_name if product.exists() else '']
                        
            _logger.info(f"✅ Loaded {len(records)} multiple.barcode records")
            return records
        except Exception as e:
            _logger.error(f"❌ Error loading multiple.barcode: {e}")
            return []

    def _pos_ui_multiple_barcode(self, params):
        return self._get_pos_ui_multiple_barcode(params)
    
    def _loader_params_barcode_config(self):
        return {
            'search_params': {
                'domain': [],
                'fields': [
                    'digit_awal',
                    'digit_akhir', 
                    'prefix_timbangan',
                    'panjang_barcode',
                    'multiple_barcode_activate',
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
            _logger.info(f"✅ Loaded barcode.config")
            return records
        except Exception as e:
            _logger.error(f"❌ Error loading barcode.config: {e}")
            return []

    def _pos_ui_barcode_config(self, params):
        return self._get_pos_ui_barcode_config(params)
    
    def _loader_params_pos_cashier_log(self):
        return {
            'search_params': {
                'domain': [('session_id', '=', self.id)],
                'fields': [
                    'id',
                    'session_id',
                    'employee_id',
                    'state',
                    'timestamp',
                ],
            }
        }

    def _get_pos_ui_pos_cashier_log(self, params):
        try:
            if 'pos.cashier.log' not in self.env:
                _logger.warning("⚠️ Model pos.cashier.log not found")
                return []
                
            records = self.env['pos.cashier.log'].search_read(
                params['search_params'].get('domain', []),
                params['search_params']['fields']
            )

            for rec in records:
                if rec.get('employee_id'):
                    if isinstance(rec['employee_id'], int):
                        emp = self.env['hr.employee'].browse(rec['employee_id'])
                        rec['employee_id'] = [rec['employee_id'], emp.name if emp.exists() else '']
                    elif isinstance(rec['employee_id'], list) and len(rec['employee_id']) >= 2:
                        rec['employee_id'] = [int(rec['employee_id'][0]), str(rec['employee_id'][1])]

                if rec.get('session_id'):
                    if isinstance(rec['session_id'], int):
                        session = self.env['pos.session'].browse(rec['session_id'])
                        rec['session_id'] = [rec['session_id'], session.name if session.exists() else '']
                    elif isinstance(rec['session_id'], list) and len(rec['session_id']) >= 2:
                        rec['session_id'] = [int(rec['session_id'][0]), str(rec['session_id'][1])]
                        
            _logger.info(f"✅ Loaded {len(records)} pos.cashier.log records")
            return records
        except Exception as e:
            _logger.error(f"❌ Error loading pos.cashier.log: {e}")
            return []

    def _pos_ui_pos_cashier_log(self, params):
        return self._get_pos_ui_pos_cashier_log(params)

    def _loader_params_res_config_settings(self):
        return {'search_params': {'fields': []}}

    def _get_pos_ui_res_config_settings(self, params):
        try:
            config = self.env['ir.config_parameter'].sudo()

            # Safely get manager_id
            manager_id = config.get_param('pos.manager_id')
            manager = None
            if manager_id and str(manager_id).isdigit():
                try:
                    manager = self.env['hr.employee'].browse(int(manager_id))
                    if not manager.exists():
                        manager = None
                except Exception:
                    manager = None

            # Safely get rounding_product_id
            rounding_product_id = config.get_param('pos.rounding_product_id')
            rounding_product = None
            if rounding_product_id and str(rounding_product_id).isdigit():
                try:
                    rounding_product = self.env['product.product'].browse(int(rounding_product_id))
                    if not rounding_product.exists():
                        rounding_product = None
                except Exception:
                    rounding_product = None

            # Get digits config safely
            total_digits = config.get_param('reward_point_total_digits', '16')
            decimal_digits = config.get_param('reward_point_decimal_digits', '4')

            result = {
                'manager_validation': config.get_param('pos.manager_validation', 'False') == 'True',
                'validate_discount_amount': config.get_param('pos.validate_discount_amount', 'False') == 'True',
                'validate_end_shift': config.get_param('pos.validate_end_shift', 'False') == 'True',
                'validate_closing_pos': config.get_param('pos.validate_closing_pos', 'False') == 'True',
                'validate_order_line_deletion': config.get_param('pos.validate_order_line_deletion', 'False') == 'True',
                'validate_discount': config.get_param('pos.validate_discount', 'False') == 'True',
                'validate_price_change': config.get_param('pos.validate_price_change', 'False') == 'True',
                'validate_order_deletion': config.get_param('pos.validate_order_deletion', 'False') == 'True',
                'validate_add_remove_quantity': config.get_param('pos.validate_add_remove_quantity', 'False') == 'True',
                'validate_payment': config.get_param('pos.validate_payment', 'False') == 'True',
                'validate_refund': config.get_param('pos.validate_refund', 'False') == 'True',
                'validate_close_session': config.get_param('pos.validate_close_session', 'False') == 'True',
                'validate_void_sales': config.get_param('pos.validate_void_sales', 'False') == 'True',
                'validate_member_schedule': config.get_param('pos.validate_member_schedule', 'False') == 'True',
                'validate_cash_drawer': config.get_param('pos.validate_cash_drawer', 'False') == 'True',
                'validate_reprint_receipt': config.get_param('pos.validate_reprint_receipt', 'False') == 'True',
                'validate_discount_button': config.get_param('pos.validate_discount_button', 'False') == 'True',
                'allow_multiple_global_discounts': config.get_param('pos.allow_multiple_global_discounts', 'False') == 'True',
                'one_time_password': config.get_param('pos.one_time_password', 'False') == 'True',
                'multiple_barcode_activate': config.get_param('pos.multiple_barcode_activate', 'False') == 'True',
                'validate_pricelist': config.get_param('pos.validate_pricelist', 'False') == 'True',
                'reward_point_total_digits': int(total_digits) if str(total_digits).isdigit() else 16,
                'reward_point_decimal_digits': int(decimal_digits) if str(decimal_digits).isdigit() else 4,
                'manager_pin': manager.pin if manager else '',
                'manager_name': manager.name if manager else '',
                
                # ✅ TAMBAHAN UNTUK AUTO ROUNDING
                'enable_auto_rounding': config.get_param('pos.enable_auto_rounding', 'False') == 'True',
                'rounding_value': int(config.get_param('pos.rounding_value', '100')) if config.get_param('pos.rounding_value', '100').isdigit() else 100,
                'rounding_product_id': {
                    'id': rounding_product.id if rounding_product else None,
                    'name': rounding_product.name if rounding_product else None,
                } if rounding_product else None,
            }
            
            _logger.info("✅ Loaded res.config.settings with rounding config")
            if result['enable_auto_rounding']:
                _logger.info(f"   🔄 Auto Rounding: ENABLED")
                _logger.info(f"   💯 Rounding Value: {result['rounding_value']}")
                _logger.info(f"   📦 Rounding Product: {result['rounding_product_id']['name'] if result['rounding_product_id'] else 'NOT SET'}")
            else:
                _logger.info(f"   🔄 Auto Rounding: DISABLED")
                
            return [result]
        except Exception as e:
            _logger.error(f"❌ Error loading res.config.settings: {e}")
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
                'validate_discount_button': False,
                'allow_multiple_global_discounts': False,
                'one_time_password': False,
                'multiple_barcode_activate': False,
                'validate_pricelist': False,
                'reward_point_total_digits': 16,
                'reward_point_decimal_digits': 4,
                'manager_pin': '',
                'manager_name': '',
                # ✅ DEFAULT UNTUK ROUNDING
                'enable_auto_rounding': False,
                'rounding_value': 100,
                'rounding_product_id': None,
            }]

    def _pos_ui_res_config_settings(self, params):
        return self._get_pos_ui_res_config_settings(params)
    
    def _loader_params_product_product(self):
        """
        Override untuk menambahkan gm_is_pelunasan dengan logging detail
        """
        result = super()._loader_params_product_product()
        
        # Tambahkan gm_is_pelunasan ke fields
        if 'gm_is_pelunasan' not in result['search_params']['fields']:
            result['search_params']['fields'].append('gm_is_pelunasan')
            _logger.info("✅ Added gm_is_pelunasan to product.product loader")
        
        if 'gm_is_rounding' not in result['search_params']['fields']:
            result['search_params']['fields'].append('gm_is_rounding')
            _logger.info("✅ Added gm_is_rounding to product.product loader")

        if 'gm_is_dp' not in result['search_params']['fields']:
            result['search_params']['fields'].append('gm_is_dp')
            _logger.info("✅ Added gm_is_dp to product.product loader")
        
        _logger.info(f"📦 Product loader fields: {result['search_params']['fields']}")
        
        return result

    def _get_pos_ui_product_product(self, params):
        """
        Override untuk logging detail produk pelunasan yang di-load
        """
        products = super()._get_pos_ui_product_product(params)
        
        # Count dan log produk dengan gm_is_pelunasan
        pelunasan_products = []
        normal_products = []
        
        for product in products:
            if product.get('gm_is_pelunasan') is True:
                pelunasan_products.append(product)
            else:
                normal_products.append(product)
        
        # Detailed logging
        _logger.info(f"📊 Product loading summary:")
        _logger.info(f"   Total products: {len(products)}")
        _logger.info(f"   Pelunasan products: {len(pelunasan_products)}")
        _logger.info(f"   Normal products: {len(normal_products)}")
        
        if pelunasan_products:
            _logger.info(f"🎯 Pelunasan products loaded:")
            for p in pelunasan_products[:10]:  # Log max 10 untuk avoid spam
                _logger.info(
                    f"   - {p.get('display_name')} "
                    f"(ID: {p.get('id')}, "
                    f"gm_is_pelunasan: {p.get('gm_is_pelunasan')})"
                )
            if len(pelunasan_products) > 10:
                _logger.info(f"   ... and {len(pelunasan_products) - 10} more")
        else:
            _logger.warning("⚠️ No pelunasan products found in loaded data!")
            _logger.warning("   This might indicate:")
            _logger.warning("   1. No products have gm_is_pelunasan = True")
            _logger.warning("   2. Field 'gm_is_pelunasan' not in product.product model")
            _logger.warning("   3. Field not properly configured")
        
        # Validasi field availability
        sample_product = products[0] if products else None
        if sample_product:
            has_field = 'gm_is_pelunasan' in sample_product
            _logger.info(
                f"✅ Field 'gm_is_pelunasan' {'FOUND' if has_field else 'NOT FOUND'} "
                f"in product data"
            )
            if not has_field:
                _logger.error(
                    "❌ CRITICAL: Field 'gm_is_pelunasan' missing from product data! "
                    "Receipt filtering will NOT work!"
                )
        
        return products
    
    def _pos_ui_product_product(self, params):
        return self._get_pos_ui_product_product(params)

    def _loader_params_res_partner(self):
        domain = [
            ('active', '=', True),
            ('gm_bp_type', '=', 'customer'),
        ]

        _logger.info(f"🔍 _loader_params_res_partner CALLED, domain={domain}")  # ← tambah ini

        if self.config_id.default_partner_id:
            default_partner_id = self.config_id.default_partner_id.id
            domain = [
                '|',
                ('id', '=', default_partner_id),
                '&',
                ('active', '=', True),
                ('gm_bp_type', '=', 'customer'),
            ]
            _logger.info(f"🔍 Modified domain with default_partner: {domain}")  # ← dan ini

        return {
            'search_params': {
                'domain': domain,
                'fields': [
                    'name', 'street', 'city', 'state_id', 'country_id',
                    'vat', 'lang', 'phone', 'zip', 'mobile', 'email',
                    'barcode', 'write_date', 'property_account_position_id',
                    'property_product_pricelist', 'parent_name', 'category_id',
                    'vit_customer_group', 'gm_bp_type',
                ],
                'limit': 10000,
                'order': 'name ASC',
            }
        }

    def _get_pos_ui_res_partner(self, params):
        """
        Override dengan:
        1. Force-load default customer jika tidak ter-load
        2. Extensive logging untuk debugging
        3. Proper error handling
        """
        try:
            # Load partners dari database
            partners = self.env['res.partner'].search_read(
                params['search_params'].get('domain', []),
                params['search_params']['fields'],
                limit=params['search_params'].get('limit', 10000),
                order=params['search_params'].get('order', 'name ASC')
            )
            
            _logger.info(f"📊 Initial partners loaded: {len(partners)}")
            
            if len(partners) == 0:
                _logger.error("❌ CRITICAL: NO PARTNERS LOADED!")
                _logger.error("   Customer list will be EMPTY in POS!")
                _logger.error("   Check domain filters and partner data!")
            else:
                # Log sample partners
                sample_names = [p['name'] for p in partners[:5]]
                _logger.info(f"   Sample partners: {sample_names}")
            
            # ✅ CRITICAL: Validate dan force-load default customer
            if self.config_id.default_partner_id:
                default_id = self.config_id.default_partner_id.id
                default_name = self.config_id.default_partner_id.name
                
                # Check apakah default customer sudah ter-load
                is_loaded = any(p['id'] == default_id for p in partners)
                
                if is_loaded:
                    _logger.info(f"✅ Default customer '{default_name}' (ID: {default_id}) already loaded")
                else:
                    _logger.warning(f"⚠️ Default customer '{default_name}' (ID: {default_id}) NOT in results!")
                    _logger.warning(f"   This should NOT happen with proper domain!")
                    _logger.warning(f"   Attempting force-load...")
                    
                    # Force load the default customer
                    try:
                        default_partner = self.env['res.partner'].search_read(
                            [('id', '=', default_id)],
                            params['search_params']['fields'],
                            limit=1
                        )
                        
                        if default_partner:
                            # Insert at beginning of list
                            partners.insert(0, default_partner[0])
                            _logger.info(f"✅ FORCE-LOADED default customer: '{default_name}'")
                            _logger.info(f"   Total partners now: {len(partners)}")
                        else:
                            _logger.error(f"❌ Cannot force-load default customer!")
                            _logger.error(f"   Partner ID {default_id} does not exist in database!")
                            _logger.error(f"   Possible causes:")
                            _logger.error(f"   1. Partner has been deleted")
                            _logger.error(f"   2. Wrong ID in pos.config.default_partner_id")
                            _logger.error(f"   3. Database corruption")
                            
                            # Check if partner exists at all
                            partner_exists = self.env['res.partner'].search_count([('id', '=', default_id)])
                            if partner_exists:
                                partner = self.env['res.partner'].browse(default_id)
                                _logger.error(f"   Partner EXISTS but search_read failed!")
                                _logger.error(f"   Partner active: {partner.active}")
                                _logger.error(f"   Partner name: {partner.name}")
                            else:
                                _logger.error(f"   Partner does NOT exist in database!")
                            
                    except Exception as e:
                        _logger.error(f"❌ Error force-loading default customer: {e}")
                        _logger.error(f"   Traceback: {traceback.format_exc()}")
            else:
                _logger.warning("⚠️ No default_partner_id configured in POS config")
            
            # Process relational fields
            for partner in partners:
                try:
                    # Handle category_id (Many2many)
                    if partner.get('category_id') and isinstance(partner['category_id'], list):
                        partner['category_id'] = [int(cid) for cid in partner['category_id'] if str(cid).isdigit()]
                    
                    # Handle other relational fields (Many2one)
                    for field in ['state_id', 'country_id', 'property_account_position_id', 'property_product_pricelist']:
                        if partner.get(field):
                            if isinstance(partner[field], int):
                                # Convert int to [id, name] format
                                try:
                                    if field == 'state_id':
                                        record = self.env['res.country.state'].browse(partner[field])
                                    elif field == 'country_id':
                                        record = self.env['res.country'].browse(partner[field])
                                    elif field == 'property_account_position_id':
                                        record = self.env['account.fiscal.position'].browse(partner[field])
                                    elif field == 'property_product_pricelist':
                                        record = self.env['product.pricelist'].browse(partner[field])
                                    
                                    if record.exists():
                                        partner[field] = [partner[field], record.name]
                                except Exception as e:
                                    _logger.warning(f"⚠️ Error converting {field} for partner {partner.get('name')}: {e}")
                            elif isinstance(partner[field], list) and len(partner[field]) >= 2:
                                # Already in [id, name] format, normalize
                                partner[field] = [int(partner[field][0]), str(partner[field][1])]
                                
                except Exception as e:
                    _logger.warning(f"⚠️ Error processing partner {partner.get('id')}: {e}")
                    continue
            
            # ✅ FINAL LOG
            _logger.info(f"✅ FINAL: Successfully loaded {len(partners)} res.partner records")
            
            if len(partners) > 0:
                _logger.info(f"   First 5 partners: {[p['name'] for p in partners[:5]]}")
            else:
                _logger.error(f"❌ CRITICAL: Final partner list is EMPTY!")
            
            return partners
            
        except Exception as e:
            _logger.error(f"❌ CRITICAL ERROR in _get_pos_ui_res_partner: {e}")
            _logger.error(f"   Traceback: {traceback.format_exc()}")
            _logger.error(f"   This will cause POS to have NO customers!")
            return []

    def _pos_ui_res_partner(self, params):
        """
        Entry point untuk partner loading
        """
        return self._get_pos_ui_res_partner(params)

    def _loader_params_loyalty_program(self):
        return {
            'search_params': {
                'domain': [('active', '=', True)],
                'fields': [
                    'name', 'program_type', 'active', 'trigger', 'rule_ids',
                    'is_nominative', 'limit_usage', 'total_order_count',
                    'max_usage', 'pricelist_ids', 'date_from', 'date_to',
                ],
            }
        }

    def _get_pos_ui_loyalty_program(self, params):
        try:
            if 'loyalty.program' not in self.env:
                _logger.warning("⚠️ Model loyalty.program not found")
                return []
                
            programs = self.env['loyalty.program'].search_read(
                params['search_params'].get('domain', []),
                params['search_params']['fields'],
                limit=100
            )
            
            for program in programs:
                program['active'] = True
                
                # Handle pricelist_ids
                if program.get('pricelist_ids') and isinstance(program['pricelist_ids'], list):
                    program['pricelist_ids'] = [int(pid) for pid in program['pricelist_ids'] if str(pid).isdigit()]
                
                # Handle rule_ids
                if program.get('rule_ids') and isinstance(program['rule_ids'], list):
                    program['rule_ids'] = [int(rid) for rid in program['rule_ids'] if str(rid).isdigit()]
                    
            _logger.info(f"✅ Loaded {len(programs)} loyalty.program records")
            return programs
        except Exception as e:
            _logger.error(f"❌ Error loading loyalty.program: {e}")
            return []

    def _pos_ui_loyalty_program(self, params):
        return self._get_pos_ui_loyalty_program(params)
    
    def _loader_params_loyalty_reward(self):
        return {
            'search_params': {
                'domain': [('program_id.active', '=', True)],
                'fields': ['name', 'reward_type', 'discount', 'program_id', 'reward_product_ids', 'discount_line_product_id'],
            }
        }

    def _get_pos_ui_loyalty_reward(self, params):
        try:
            if 'loyalty.reward' not in self.env:
                _logger.warning("⚠️ Model loyalty.reward not found")
                return []
            
            records = self.env['loyalty.reward'].search_read(
                params['search_params'].get('domain', []),
                params['search_params']['fields'],
                limit=500
            )

            for rec in records:
                # Process program_id
                if rec.get('program_id'):
                    if isinstance(rec['program_id'], int):
                        program = self.env['loyalty.program'].browse(rec['program_id'])
                        rec['program_id'] = [rec['program_id'], program.name if program.exists() else '']
                    elif isinstance(rec['program_id'], list) and len(rec['program_id']) >= 2:
                        rec['program_id'] = [int(rec['program_id'][0]), str(rec['program_id'][1])]

                # Process discount_line_product_id
                if rec.get('discount_line_product_id'):
                    if isinstance(rec['discount_line_product_id'], int):
                        product = self.env['product.product'].browse(rec['discount_line_product_id'])
                        if product.exists():
                            rec['discount_line_product_id'] = [product.id, product.display_name]
                            if not product.available_in_pos:
                                _logger.warning(
                                    f"⚠️ Discount product '{product.display_name}' "
                                    f"(ID {product.id}) not available in POS"
                                )
                        else:
                            rec['discount_line_product_id'] = False
                    elif isinstance(rec['discount_line_product_id'], list) and len(rec['discount_line_product_id']) >= 2:
                        rec['discount_line_product_id'] = [int(rec['discount_line_product_id'][0]), str(rec['discount_line_product_id'][1])]
                
                # Process reward_product_ids
                if rec.get('reward_product_ids') and isinstance(rec['reward_product_ids'], list):
                    rec['reward_product_ids'] = [int(pid) for pid in rec['reward_product_ids'] if str(pid).isdigit()]
                    
            _logger.info(f"✅ Loaded {len(records)} loyalty.reward records")
            return records
        except Exception as e:
            _logger.error(f"❌ Error loading loyalty.reward: {e}")
            return []

    def _pos_ui_loyalty_reward(self, params):
        return self._get_pos_ui_loyalty_reward(params)

    def _loader_params_loyalty_rule(self):
        return {
            'search_params': {
                'domain': [('program_id.active', '=', True)],
                'fields': ['name', 'program_id', 'reward_point_amount', 'reward_point_mode', 
                          'minimum_qty', 'minimum_amount', 'product_ids', 'product_domain'],
            }
        }

    def _get_pos_ui_loyalty_rule(self, params):
        try:
            if 'loyalty.rule' not in self.env:
                _logger.warning("⚠️ Model loyalty.rule not found")
                return []
                
            records = self.env['loyalty.rule'].search_read(
                params['search_params'].get('domain', []),
                params['search_params']['fields'],
                limit=500
            )
            
            for rec in records:
                # Process program_id
                if rec.get('program_id'):
                    if isinstance(rec['program_id'], int):
                        program = self.env['loyalty.program'].browse(rec['program_id'])
                        rec['program_id'] = [rec['program_id'], program.name if program.exists() else '']
                    elif isinstance(rec['program_id'], list) and len(rec['program_id']) >= 2:
                        rec['program_id'] = [int(rec['program_id'][0]), str(rec['program_id'][1])]
                
                # Process product_ids
                if rec.get('product_ids') and isinstance(rec['product_ids'], list):
                    rec['product_ids'] = [int(pid) for pid in rec['product_ids'] if str(pid).isdigit()]
                    
            _logger.info(f"✅ Loaded {len(records)} loyalty.rule records")
            return records
        except Exception as e:
            _logger.error(f"❌ Error loading loyalty.rule: {e}")
            return []

    def _pos_ui_loyalty_rule(self, params):
        return self._get_pos_ui_loyalty_rule(params)

    def _loader_params_loyalty_member(self):
        return {
            'search_params': {
                'domain': [('member_program_id.active', '=', True)],
                'fields': ['member_program_id', 'member_pos'],
            }
        }

    def _get_pos_ui_loyalty_member(self, params):
        try:
            if 'loyalty.member' not in self.env:
                _logger.warning("⚠️ Model loyalty.member not found")
                return []
                
            records = self.env['loyalty.member'].search_read(
                params['search_params'].get('domain', []),
                params['search_params']['fields'],
                limit=5000
            )
            
            for rec in records:
                # Process member_program_id
                if rec.get('member_program_id'):
                    if isinstance(rec['member_program_id'], int):
                        program = self.env['loyalty.program'].browse(rec['member_program_id'])
                        rec['member_program_id'] = [rec['member_program_id'], program.name if program.exists() else '']
                    elif isinstance(rec['member_program_id'], list) and len(rec['member_program_id']) >= 2:
                        rec['member_program_id'] = [int(rec['member_program_id'][0]), str(rec['member_program_id'][1])]
                    
                # Process member_pos
                if rec.get('member_pos'):
                    if isinstance(rec['member_pos'], int):
                        partner = self.env['res.partner'].browse(rec['member_pos'])
                        rec['member_pos'] = [rec['member_pos'], partner.name if partner.exists() else '']
                    elif isinstance(rec['member_pos'], list) and len(rec['member_pos']) >= 2:
                        rec['member_pos'] = [int(rec['member_pos'][0]), str(rec['member_pos'][1])]
                    
            _logger.info(f"✅ Loaded {len(records)} loyalty.member records")
            return records
        except Exception as e:
            _logger.error(f"❌ Error loading loyalty.member: {e}")
            return []

    def _pos_ui_loyalty_member(self, params):
        return self._get_pos_ui_loyalty_member(params)

    def _loader_params_loyalty_program_schedule(self):
        return {
            'search_params': {
                'domain': [('program_id.active', '=', True)],
                'fields': ['days', 'time_start', 'time_end', 'program_id'],
            }
        }

    def _get_pos_ui_loyalty_program_schedule(self, params):
        try:
            if 'loyalty.program.schedule' not in self.env:
                _logger.warning("⚠️ Model loyalty.program.schedule not found")
                return []
                
            records = self.env['loyalty.program.schedule'].search(
                params['search_params'].get('domain', []),
                limit=100
            )
            
            result = []
            for rec in records:
                if rec.program_id and rec.program_id.active:
                    result.append({
                        'id': rec.id,
                        'days': rec.days,
                        'time_start': rec.time_start,
                        'time_end': rec.time_end,
                        'program_id': [rec.program_id.id, rec.program_id.name],
                    })
                    
            _logger.info(f"✅ Loaded {len(result)} loyalty.program.schedule records")
            return result
        except Exception as e:
            _logger.error(f"❌ Error loading loyalty.program.schedule: {e}")
            return []

    def _pos_ui_loyalty_program_schedule(self, params):
        
        return self._get_pos_ui_loyalty_program_schedule(params)