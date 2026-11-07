import json
import logging
import time
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


def json_response(data, status=200):
    return Response(
        json.dumps(data, ensure_ascii=False),
        status=status,
        content_type="application/json;charset=utf-8",
    )


def error_response(code, message, field=None, status=422):
    error_body = {
        "error": {
            "code": code,
            "message": message,
        }
    }
    if field:
        error_body["error"]["field"] = field
    return json_response(error_body, status=status)


def authenticate_api_key():
    """Valida la API key enviada en la cabecera Authorization: Bearer <key>

    utilizando el modelo nativo res.users.apikeys de Odoo.
    Retorna una tupla (user, error_response). Si es exitosa, error_response es None.
    """
    auth_header = request.httprequest.headers.get("Authorization", "")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None, error_response(
            code="UNAUTHORIZED",
            message="No se proporcionó la cabecera 'Authorization: Bearer <key>' requerida.",
            status=401,
        )

    api_key = auth_header[7:].strip()
    if not api_key:
        return None, error_response(
            code="UNAUTHORIZED",
            message="La clave API proporcionada está vacía.",
            status=401,
        )

    try:
        user_id = request.env["res.users.apikeys"].sudo()._check_credentials(
            scope="rpc", key=api_key
        )
    except Exception as e:
        _logger.warning("Error validando API key: %s", e)
        user_id = None

    if not user_id:
        return None, error_response(
            code="UNAUTHORIZED",
            message="API Key inválida o revocada.",
            status=401,
        )

    user = request.env["res.users"].sudo().browse(user_id)
    if not user.exists() or not user.active:
        return None, error_response(
            code="UNAUTHORIZED",
            message="El usuario asociado a esta API Key está inactivo o no existe.",
            status=401,
        )

    return user, None


def record_api_log(endpoint, method, status_code, duration_ms, user_id=None, request_payload=None, response_payload=None, error_message=None):
    """Registra la llamada en shop.api.log en una transacción independiente.

    Garantiza que llamadas fallidas o con rollback queden persistidas sin almacenar claves.
    """
    try:
        # Asegurarse de que el payload no contenga claves
        sanitized_req = None
        if request_payload:
            if isinstance(request_payload, (dict, list)):
                sanitized_req = json.dumps(request_payload, ensure_ascii=False)
            else:
                sanitized_req = str(request_payload)

        sanitized_res = None
        if response_payload:
            if isinstance(response_payload, (dict, list)):
                sanitized_res = json.dumps(response_payload, ensure_ascii=False)
            else:
                sanitized_res = str(response_payload)

        client_ip = request.httprequest.environ.get("REMOTE_ADDR") if request else None

        with request.env.registry.cursor() as log_cr:
            log_env = request.env(cr=log_cr)
            log_env["shop.api.log"].sudo().create({
                "endpoint": endpoint,
                "method": method,
                "user_id": user_id,
                "status_code": status_code,
                "duration_ms": round(duration_ms, 2),
                "request_payload": sanitized_req,
                "response_payload": sanitized_res,
                "error_message": error_message,
                "ip_address": client_ip,
            })
            log_cr.commit()
    except Exception as e:
        _logger.exception("Error al persistir shop.api.log: %s", e)

