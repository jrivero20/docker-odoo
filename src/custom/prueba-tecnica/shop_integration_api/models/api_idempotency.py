from odoo import fields, models


class ShopApiIdempotency(models.Model):
    _name = "shop.api.idempotency"
    _description = "Registro de Idempotencia de API"
    _order = "create_date desc, id desc"

    key = fields.Char(string="Idempotency Key", required=True, index=True)
    request_hash = fields.Char(string="Hash de la Petición", required=True, index=True)
    order_id = fields.Many2one("sale.order", string="Pedido Creado", ondelete="set null")
    response_json = fields.Text(string="Respuesta JSON Almacenada", required=True)

    _sql_constraints = [
        ("key_uniq", "unique(key)", "La clave de idempotencia debe ser única."),
    ]

