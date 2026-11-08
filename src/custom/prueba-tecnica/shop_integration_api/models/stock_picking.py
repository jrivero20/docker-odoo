import json
import logging
from odoo import fields, models

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _action_done(self):
        res = super()._action_done()

        # Disparar webhook para entregas a clientes con pedidos relacionados
        for picking in self:
            if picking.picking_type_id.code == "outgoing" and picking.sale_id:
                try:
                    picking._trigger_delivery_webhook()
                except Exception as e:
                    # Garantía estricta: Si algo falla preparando el webhook,
                    # el usuario que valida la entrega jamás se bloquea ni ve un error en la interfaz.
                    _logger.exception("Error al encolar webhook de entrega para picking %s: %s", picking.name, e)

        return res

    def _trigger_delivery_webhook(self):
        """Prepara el payload y crea el registro en la cola de webhooks."""
        self.ensure_one()
        url = self.env["ir.config_parameter"].sudo().get_param("shop_integration.webhook_delivery_url")
        if not url:
            return

        payload = {
            "event": "order.delivery_validated",
            "order_id": self.sale_id.id,
            "order_name": self.sale_id.name,
            "client_order_ref": self.sale_id.client_order_ref or "",
            "picking_id": self.id,
            "picking_name": self.name,
            "delivery_date": str(self.date_done or fields.Datetime.now()),
            "lines": [
                {
                    "product_id": move.product_id.id,
                    "default_code": move.product_id.default_code or "",
                    "name": move.product_id.name,
                    "quantity_delivered": move.quantity,
                }
                for move in self.move_ids
            ],
        }

        webhook = self.env["shop.webhook.queue"].sudo().create({
            "event": "order.delivery_validated",
            "url": url.strip(),
            "payload": json.dumps(payload, ensure_ascii=False),
            "state": "pending",
        })

        # Intento inicial no bloqueante
        try:
            webhook.action_send()
        except Exception as e:
            _logger.warning("Intento inicial de webhook falló sin bloquear la entrega: %s", e)

