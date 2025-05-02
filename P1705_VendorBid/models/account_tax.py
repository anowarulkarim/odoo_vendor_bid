from odoo import fields, models, api

class AccountTax(models.Model):
    _inherit = 'account.tax'

    @api.model
    def _prepare_base_line_for_taxes_computation(self, record, **kwargs):
        base_line = super(AccountTax, self)._prepare_base_line_for_taxes_computation(record, **kwargs)
        if deli_charge := getattr(record, 'delivery_charge', None):
            quantity = base_line.get('quantity', 0.0)
            base_line['price_unit'] += (deli_charge / quantity) if quantity else deli_charge
        return base_line



