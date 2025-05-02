from odoo import models, fields, api

class ResBank(models.Model):
    _inherit = 'res.bank'

    swift_code = fields.Char(string='SWIFT Code')
    iban = fields.Char(string='IBAN')
