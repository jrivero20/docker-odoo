import json
import logging
from datetime import timedelta
import urllib.request
import urllib.error
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ShopWebhookQueue(models.Model):
    _name = "shop.webhook.queue"
    _description = "Cola y Reintentos de Webhooks Salientes"
    _order = "create_date desc, id desc"

    event = fields.Char(string="Evento", required=True)
    url = fields.Char(string="URL de Destino", required=True)
    payload = fields.Text(string="Payload JSON", required=True)
    state = fields.Selection(
        [
            ("pending", "Pendiente de Envío"),
            ("sent", "Entregado"),
            ("failed", "Fallido Definitivo"),
        ],
        string="Estado",
        default="pending",
        required=True,
        index=True,
    )
    attempts = fields.Integer(string="Intentos Realizados", default=0)
    max_attempts = fields.Integer(string="Máximo de Intentos", default=3)
    last_error = fields.Text(string="Último Error")
    next_retry = fields.Datetime(string="Próximo Reintento", default=fields.Datetime.now, index=True)

    def action_send(self):
        """Intenta entregar el webhook sin bloquear ni propagar excepciones."""
        for record in self:
            if record.state == "sent":
                continue

            record.attempts += 1
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "Odoo-Shop-Webhook/1.0",
            }
            body_bytes = record.payload.encode("utf-8") if record.payload else b"{}"

            req = urllib.request.Request(
                record.url,
                data=body_bytes,
                headers=headers,
                method="POST",
            )

            try:
                # Timeout de 3 segundos para evitar bloqueos si la tienda externa no responde
                with urllib.request.urlopen(req, timeout=3) as resp:
                    if 200 <= resp.status < 300:
                        record.write({
                            "state": "sent",
                            "last_error": False,
                        })
                        continue
                    else:
                        error_msg = f"HTTP {resp.status}"
            except urllib.error.HTTPError as e:
                error_msg = f"HTTPError {e.code}: {e.reason}"
            except Exception as e:
                error_msg = f"Error de red o conexión: {str(e)}"

            _logger.warning("Fallo al entregar webhook a %s (intento %s): %s", record.url, record.attempts, error_msg)

            # Si alcanzó el límite de intentos, marcar como fallido definitivo; si no, programar reintento
            if record.attempts >= record.max_attempts:
                record.write({
                    "state": "failed",
                    "last_error": error_msg,
                })
            else:
                backoff_minutes = 2 ** record.attempts
                record.write({
                    "state": "pending",
                    "last_error": error_msg,
                    "next_retry": fields.Datetime.now() + timedelta(minutes=backoff_minutes),
                })

    @api.model
    def _cron_process_pending_webhooks(self):
        """Acción planificada (cron) para procesar webhooks pendientes con backoff."""
        now = fields.Datetime.now()
        pending = self.search([
            ("state", "=", "pending"),
            ("next_retry", "<=", now),
        ], limit=50)
        if pending:
            pending.action_send()

