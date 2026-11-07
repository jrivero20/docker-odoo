from odoo import fields, models


class ShopApiLog(models.Model):
    _name = "shop.api.log"
    _description = "Registro de Llamadas API de Tienda"
    _order = "create_date desc, id desc"

    endpoint = fields.Char(string="Endpoint", required=True, readonly=True)
    method = fields.Char(string="Método", required=True, readonly=True)
    user_id = fields.Many2one("res.users", string="Usuario", readonly=True, ondelete="set null")
    status_code = fields.Integer(string="Código de Respuesta", required=True, readonly=True)
    duration_ms = fields.Float(string="Duración (ms)", digits=(12, 2), readonly=True)
    request_payload = fields.Text(string="Payload de Petición", readonly=True)
    response_payload = fields.Text(string="Payload de Respuesta", readonly=True)
    error_message = fields.Text(string="Mensaje de Error", readonly=True)
    ip_address = fields.Char(string="Dirección IP", readonly=True)

