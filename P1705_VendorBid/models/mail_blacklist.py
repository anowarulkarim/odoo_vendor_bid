from odoo import models, fields, api

class BlackList(models.Model):
    _inherit = 'mail.blacklist'

    reason = fields.Char(string='Reason', default='Blacklisted')
