from odoo import models


class PosSession(models.Model):
    """The class PosSession is used to inherit pos.session"""
    _inherit = 'pos.session'

    def load_pos_data(self):
        """Load POS data and add `hr_employee` (sales only) to the response dictionary.
        
        ✅ Include `user_id` field agar JavaScript bisa mapping
           SO.user_id (res.users) → hr.employee.user_id → hr.employee
        """
        res = super().load_pos_data()
        res['hr_employee'] = self.env['hr.employee'].search_read(
            domain=[('is_sales', '=', True)],
            fields=['name', 'user_id'],  # ✅ user_id = Many2one ke res.users → [id, name]
        )
        return res