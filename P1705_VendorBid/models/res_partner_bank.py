from odoo import models, fields, api

class ResPartnerBank(models.Model):
    _inherit = 'res.partner.bank'

    branch_address = fields.Char(string='Branch Address')




