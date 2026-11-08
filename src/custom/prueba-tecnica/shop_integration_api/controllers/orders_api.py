import hashlib
import json
import time
from odoo import http
from odoo.http import request
from .common import (
    authenticate_api_key,
    error_response,
    json_response,
    record_api_log,
)


class ShopIntegrationOrdersController(http.Controller):

    @http.route("/api/v1/orders", type="http", auth="public", methods=["POST"], csrf=False)
    def create_order(self, **kwargs):
        """Creación de pedidos de venta desde la tienda en línea.

        Autenticación: Authorization: Bearer <key> (nativa con res.users.apikeys).
        Idempotencia: Idempotency-Key en la cabecera HTTP.
        Payload esperado:
        {
            "vat": "J-12345678-0",
            "client_order_ref": "TIENDA-1001",
            "lines": [
                {"default_code": "LAP-001", "qty": 2},
                {"default_code": "CAF-002", "qty": 1}
            ]
        }
        """
        start_time = time.time()
        endpoint = "/api/v1/orders"
        method = "POST"
        raw_body = request.httprequest.data

        # 1. Autenticación con API Key nativa de Odoo
        user, auth_err = authenticate_api_key()
        if auth_err:
            duration_ms = (time.time() - start_time) * 1000
            record_api_log(
                endpoint=endpoint,
                method=method,
                status_code=401,
                duration_ms=duration_ms,
                user_id=None,
                request_payload=raw_body.decode("utf-8", errors="ignore") if raw_body else None,
                response_payload=auth_err.response[0] if auth_err.response else None,
                error_message="Error de autenticación: API key ausente o inválida",
            )
            return auth_err

        env = request.env(user=user.id)

        # 2. Parseo del cuerpo JSON
        try:
            payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except Exception:
            err = error_response(
                code="INVALID_JSON",
                message="El cuerpo de la petición debe ser un objeto JSON válido.",
                status=400,
            )
            duration_ms = (time.time() - start_time) * 1000
            record_api_log(
                endpoint=endpoint,
                method=method,
                status_code=400,
                duration_ms=duration_ms,
                user_id=user.id,
                request_payload=raw_body.decode("utf-8", errors="ignore") if raw_body else None,
                response_payload=err.response[0] if err.response else None,
                error_message="JSON malformado",
            )
            return err

        # 3. Verificación de Idempotencia (Tramo C)
        idempotency_key = request.httprequest.headers.get("Idempotency-Key", "").strip()
        current_hash = None
        if idempotency_key:
            canonical_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            current_hash = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()

            idem_record = env["shop.api.idempotency"].sudo().search(
                [("key", "=", idempotency_key)], limit=1
            )
            if idem_record:
                if idem_record.request_hash == current_hash:
                    # Misma clave y mismo contenido: devuelve el pedido original sin duplicar
                    cached_response = json.loads(idem_record.response_json)
                    duration_ms = (time.time() - start_time) * 1000
                    record_api_log(
                        endpoint=endpoint,
                        method=method,
                        status_code=200,
                        duration_ms=duration_ms,
                        user_id=user.id,
                        request_payload=payload,
                        response_payload=cached_response,
                        error_message="Petición idempotente: pedido ya existente retornado",
                    )
                    return json_response(cached_response, status=200)
                else:
                    # Misma clave con contenido diferente: HTTP 409 Conflict
                    err = error_response(
                        code="IDEMPOTENCY_CONFLICT",
                        message=f"La clave de idempotencia '{idempotency_key}' ya fue utilizada previamente con un contenido diferente.",
                        status=409,
                    )
                    duration_ms = (time.time() - start_time) * 1000
                    record_api_log(
                        endpoint=endpoint,
                        method=method,
                        status_code=409,
                        duration_ms=duration_ms,
                        user_id=user.id,
                        request_payload=payload,
                        response_payload=err.response[0] if err.response else None,
                        error_message=f"Conflicto de idempotencia en clave {idempotency_key}",
                    )
                    return err

        # 4. Validación de RIF del cliente (vat)
        vat = payload.get("vat")
        if not vat or not str(vat).strip():
            err = error_response(
                code="MISSING_FIELD",
                field="vat",
                message="El campo 'vat' (RIF del cliente) es obligatorio.",
                status=422,
            )
            duration_ms = (time.time() - start_time) * 1000
            record_api_log(
                endpoint=endpoint,
                method=method,
                status_code=422,
                duration_ms=duration_ms,
                user_id=user.id,
                request_payload=payload,
                response_payload=err.response[0] if err.response else None,
                error_message="Campo vat faltante",
            )
            return err

        vat_clean = str(vat).strip()
        partner = env["res.partner"].search(
            ["|", ("vat", "=", vat_clean), ("vat", "=ilike", vat_clean), ("active", "=", True)],
            limit=1,
        )
        if not partner:
            err = error_response(
                code="CUSTOMER_NOT_FOUND",
                field="vat",
                message=f"No existe ningún cliente registrado con el RIF {vat_clean}",
                status=422,
            )
            duration_ms = (time.time() - start_time) * 1000
            record_api_log(
                endpoint=endpoint,
                method=method,
                status_code=422,
                duration_ms=duration_ms,
                user_id=user.id,
                request_payload=payload,
                response_payload=err.response[0] if err.response else None,
                error_message=f"Cliente con RIF {vat_clean} no encontrado",
            )
            return err

        # 5. Validación de líneas de productos (lines)
        lines = payload.get("lines")
        if not lines or not isinstance(lines, list) or len(lines) == 0:
            err = error_response(
                code="INVALID_LINES",
                field="lines",
                message="El pedido debe contener al menos una línea de producto válida.",
                status=422,
            )
            duration_ms = (time.time() - start_time) * 1000
            record_api_log(
                endpoint=endpoint,
                method=method,
                status_code=422,
                duration_ms=duration_ms,
                user_id=user.id,
                request_payload=payload,
                response_payload=err.response[0] if err.response else None,
                error_message="Líneas de pedido vacías o inválidas",
            )
            return err

        # Validar individualmente cada línea
        validated_lines = []
        for idx, line in enumerate(lines):
            if not isinstance(line, dict):
                err = error_response(
                    code="INVALID_LINE_FORMAT",
                    field=f"lines[{idx}]",
                    message=f"El elemento de la línea {idx} debe ser un objeto JSON.",
                    status=422,
                )
                duration_ms = (time.time() - start_time) * 1000
                record_api_log(
                    endpoint=endpoint,
                    method=method,
                    status_code=422,
                    duration_ms=duration_ms,
                    user_id=user.id,
                    request_payload=payload,
                    response_payload=err.response[0] if err.response else None,
                    error_message=f"Formato inválido en línea {idx}",
                )
                return err

            code = line.get("default_code")
            if not code or not str(code).strip():
                err = error_response(
                    code="MISSING_PRODUCT_CODE",
                    field=f"lines[{idx}].default_code",
                    message=f"Debe especificar el código de producto en la línea {idx}.",
                    status=422,
                )
                duration_ms = (time.time() - start_time) * 1000
                record_api_log(
                    endpoint=endpoint,
                    method=method,
                    status_code=422,
                    duration_ms=duration_ms,
                    user_id=user.id,
                    request_payload=payload,
                    response_payload=err.response[0] if err.response else None,
                    error_message=f"Código de producto ausente en línea {idx}",
                )
                return err

            code_clean = str(code).strip()
            product = env["product.product"].search(
                [("default_code", "=", code_clean), ("sale_ok", "=", True), ("active", "=", True)],
                limit=1,
            )
            if not product:
                err = error_response(
                    code="PRODUCT_NOT_FOUND",
                    field=f"lines[{idx}].default_code",
                    message=f"No existe un producto con el código {code_clean}",
                    status=422,
                )
                duration_ms = (time.time() - start_time) * 1000
                record_api_log(
                    endpoint=endpoint,
                    method=method,
                    status_code=422,
                    duration_ms=duration_ms,
                    user_id=user.id,
                    request_payload=payload,
                    response_payload=err.response[0] if err.response else None,
                    error_message=f"Producto {code_clean} no encontrado",
                )
                return err

            qty = line.get("qty")
            try:
                qty_val = float(qty)
            except (ValueError, TypeError):
                err = error_response(
                    code="INVALID_QUANTITY",
                    field=f"lines[{idx}].qty",
                    message=f"La cantidad indicada en la línea {idx} no es un número válido.",
                    status=422,
                )
                duration_ms = (time.time() - start_time) * 1000
                record_api_log(
                    endpoint=endpoint,
                    method=method,
                    status_code=422,
                    duration_ms=duration_ms,
                    user_id=user.id,
                    request_payload=payload,
                    response_payload=err.response[0] if err.response else None,
                    error_message=f"Cantidad no numérica en línea {idx}",
                )
                return err

            if qty_val <= 0:
                err = error_response(
                    code="INVALID_QUANTITY",
                    field=f"lines[{idx}].qty",
                    message=f"La cantidad del producto {code_clean} debe ser mayor que cero.",
                    status=422,
                )
                duration_ms = (time.time() - start_time) * 1000
                record_api_log(
                    endpoint=endpoint,
                    method=method,
                    status_code=422,
                    duration_ms=duration_ms,
                    user_id=user.id,
                    request_payload=payload,
                    response_payload=err.response[0] if err.response else None,
                    error_message=f"Cantidad cero o negativa en línea {idx}",
                )
                return err

            validated_lines.append((product, qty_val))

        # 6. Creación del pedido de venta
        client_ref = payload.get("client_order_ref") or False
        order_line_commands = [
            (
                0,
                0,
                {
                    "product_id": prod.id,
                    "product_uom_qty": qty_num,
                    "price_unit": prod.list_price,
                },
            )
            for prod, qty_num in validated_lines
        ]

        order_vals = {
            "partner_id": partner.id,
            "client_order_ref": client_ref,
            "order_line": order_line_commands,
        }

        # Supuesto documentado: El pedido se crea en estado cotización ('draft')
        # para que ventas valide inventario físico y despacho antes de confirmar.
        order = env["sale.order"].create(order_vals)

        response_data = {
            "id": order.id,
            "name": order.name,
            "client_order_ref": order.client_order_ref or "",
            "state": order.state,
            "partner": {
                "id": partner.id,
                "name": partner.name,
                "vat": partner.vat or "",
            },
            "amount_untaxed": order.amount_untaxed,
            "amount_tax": order.amount_tax,
            "amount_total": order.amount_total,
            "lines": [
                {
                    "product_id": line.product_id.id,
                    "default_code": line.product_id.default_code or "",
                    "name": line.product_id.name,
                    "qty": line.product_uom_qty,
                    "price_unit": line.price_unit,
                    "price_subtotal": line.price_subtotal,
                }
                for line in order.order_line
            ],
        }

        # Guardar registro de idempotencia si se proporcionó cabecera
        if idempotency_key and current_hash:
            env["shop.api.idempotency"].sudo().create({
                "key": idempotency_key,
                "request_hash": current_hash,
                "order_id": order.id,
                "response_json": json.dumps(response_data, ensure_ascii=False),
            })

        duration_ms = (time.time() - start_time) * 1000
        record_api_log(
            endpoint=endpoint,
            method=method,
            status_code=201,
            duration_ms=duration_ms,
            user_id=user.id,
            request_payload=payload,
            response_payload=response_data,
            error_message=None,
        )

        return json_response(response_data, status=201)
