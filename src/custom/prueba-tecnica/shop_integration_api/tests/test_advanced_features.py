import json
from unittest.mock import patch
from odoo.tests.common import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestShopIntegrationAdvancedFeatures(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.user_api = cls.env["res.users"].create({
            "name": "Advanced Shop Bot",
            "login": "adv_shop_bot",
            "password": "adv_password_123",
            "email": "adv_bot@test.com",
            "groups_id": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("sales_team.group_sale_salesman").id,
                cls.env.ref("stock.group_stock_user").id,
            ])],
        })

        cls.raw_api_key = cls.env["res.users.apikeys"].with_user(cls.user_api)._generate(
            None, "Advanced Key"
        )

        cls.customer = cls.env["res.partner"].create({
            "name": "Distribuidora Los Andes C.A.",
            "vat": "J-40123456-7",
            "email": "contacto@losandes.com",
        })

        cls.prod_a = cls.env["product.product"].create({
            "name": "Router Gigabit 1",
            "default_code": "RTR-001",
            "list_price": 45.0,
            "detailed_type": "product",
            "active": True,
            "sale_ok": True,
        })

        cls.prod_b = cls.env["product.product"].create({
            "name": "Switch 8 Puertos 2",
            "default_code": "SW-002",
            "list_price": 30.0,
            "detailed_type": "product",
            "active": True,
            "sale_ok": True,
        })

    def _post_order(self, payload, idempotency_key=None):
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.raw_api_key}",
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        return self.url_open(
            "/api/v1/orders",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
        )

    def test_01_idempotency_same_key_same_content_returns_same_order(self):
        """Misma clave de idempotencia y mismo contenido devuelve el mismo pedido sin duplicar."""
        idempotency_key = "IDEM-TEST-1001"
        payload = {
            "vat": self.customer.vat,
            "client_order_ref": "ECOMMERCE-IDEM-1",
            "lines": [
                {"default_code": "RTR-001", "qty": 2},
            ],
        }

        # Primera petición: Crea el pedido (201)
        res1 = self._post_order(payload, idempotency_key=idempotency_key)
        self.assertEqual(res1.status_code, 201)
        data1 = res1.json()
        order_id_1 = data1["id"]

        # Segunda petición con la MISMA clave y MISMO contenido: Retorna el pedido existente (200)
        res2 = self._post_order(payload, idempotency_key=idempotency_key)
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        order_id_2 = data2["id"]

        self.assertEqual(order_id_1, order_id_2, "No debe crearse un segundo pedido")
        self.assertEqual(data1["name"], data2["name"])

        # Verificar en base de datos que solo existe un pedido con esa referencia
        orders = self.env["sale.order"].search([("client_order_ref", "=", "ECOMMERCE-IDEM-1")])
        self.assertEqual(len(orders), 1, "Debe existir un único registro en sale.order")

    def test_02_idempotency_same_key_different_content_returns_409(self):
        """Misma clave de idempotencia con diferente contenido devuelve HTTP 409 Conflict."""
        idempotency_key = "IDEM-TEST-CONFLICT-2002"
        payload_orig = {
            "vat": self.customer.vat,
            "client_order_ref": "ECOMMERCE-IDEM-2",
            "lines": [
                {"default_code": "RTR-001", "qty": 1},
            ],
        }

        # Primera petición: Crea el pedido (201)
        res1 = self._post_order(payload_orig, idempotency_key=idempotency_key)
        self.assertEqual(res1.status_code, 201)

        # Segunda petición: Misma clave, pero contenido distinto (cambia la cantidad a 5)
        payload_diff = {
            "vat": self.customer.vat,
            "client_order_ref": "ECOMMERCE-IDEM-2",
            "lines": [
                {"default_code": "RTR-001", "qty": 5},
            ],
        }
        res2 = self._post_order(payload_diff, idempotency_key=idempotency_key)
        self.assertEqual(res2.status_code, 409, "Debe retornar 409 Conflict")
        data2 = res2.json()
        self.assertIn("error", data2)
        self.assertEqual(data2["error"]["code"], "IDEMPOTENCY_CONFLICT")

    def test_03_products_pagination_metadata(self):
        """Verifica la respuesta paginada con metadatos: total, page, limit, total_pages, next, prev."""
        self.authenticate("adv_shop_bot", "adv_password_123")

        res = self.url_open("/api/v1/products?page=1&limit=1")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertIn("total", data)
        self.assertIn("page", data)
        self.assertIn("limit", data)
        self.assertIn("total_pages", data)
        self.assertIn("next", data)
        self.assertIn("prev", data)
        self.assertIn("products", data)

        self.assertEqual(data["page"], 1)
        self.assertEqual(data["limit"], 1)
        self.assertEqual(len(data["products"]), 1)
        self.assertIsNone(data["prev"])
        if data["total"] > 1:
            self.assertEqual(data["next"], 2)

    def test_04_query_count_does_not_grow_with_product_count(self):
        """Verifica que el número de consultas a la base de datos no crece con la cantidad de productos (O(1))."""
        # Crear una categoría aislada
        categ_bench = self.env["product.category"].create({"name": "Bench Queries API"})

        # Crear 2 productos
        for i in range(2):
            self.env["product.product"].create({
                "name": f"Item Bench A-{i}",
                "default_code": f"BCH-A-{i}",
                "categ_id": categ_bench.id,
                "detailed_type": "product",
                "active": True,
                "sale_ok": True,
            })

        # Medir consultas para 2 productos
        query_count_start = self.cr.sql_log_count
        products_2 = self.env["product.product"].search([("categ_id", "=", categ_bench.id)])
        data_2 = products_2.read(["id", "default_code", "name", "list_price", "qty_available"])
        queries_for_2 = self.cr.sql_log_count - query_count_start
        self.assertEqual(len(data_2), 2)

        # Crear 10 productos adicionales en la misma categoría (total 12 productos)
        for i in range(2, 12):
            self.env["product.product"].create({
                "name": f"Item Bench B-{i}",
                "default_code": f"BCH-B-{i}",
                "categ_id": categ_bench.id,
                "detailed_type": "product",
                "active": True,
                "sale_ok": True,
            })

        # Medir consultas para 12 productos
        query_count_start = self.cr.sql_log_count
        products_12 = self.env["product.product"].search([("categ_id", "=", categ_bench.id)])
        data_12 = products_12.read(["id", "default_code", "name", "list_price", "qty_available"])
        queries_for_12 = self.cr.sql_log_count - query_count_start
        self.assertEqual(len(data_12), 12)

        # El número de consultas con 12 productos no debe ser mayor que con 2 productos (complejidad O(1) batch prefetch)
        self.assertLessEqual(
            queries_for_12,
            queries_for_2,
            f"El número de consultas a la BD no debe crecer con la cantidad de productos. Para 2: {queries_for_2}, para 12: {queries_for_12}",
        )

    def test_05_outgoing_webhook_resilient_when_store_is_down(self):
        """Si la tienda está caída, la validación del albarán de entrega NO se bloquea ni genera error."""
        # 1. Configurar URL de webhook ficticia que falle/esté caída
        self.env["ir.config_parameter"].sudo().set_param(
            "shop_integration.webhook_delivery_url", "http://127.0.0.1:59999/down-webhook-endpoint"
        )

        # 2. Crear pedido de venta
        order = self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "client_order_ref": "WH-TEST-001",
            "order_line": [
                (0, 0, {"product_id": self.prod_a.id, "product_uom_qty": 2.0}),
            ],
        })

        # Confirmar el pedido para que Odoo genere el stock.picking de salida
        order.action_confirm()
        picking = order.picking_ids
        self.assertTrue(picking, "Debe haberse generado el albarán de salida")

        # Asignar y completar cantidad entregada
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty

        # 3. Validar la entrega. No debe levantar excepciones a pesar de que la URL de webhook no responda
        try:
            picking.button_validate()
        except Exception as e:
            self.fail(f"La validación del albarán falló con error: {e}. Quien valida no debe quedar bloqueado.")

        # Verificar que el albarán quedó validado
        self.assertEqual(picking.state, "done", "El albarán debe completarse normalmente")

        # 4. Verificar que se creó el registro en la cola de webhooks
        webhook_logs = self.env["shop.webhook.queue"].search([
            ("url", "=", "http://127.0.0.1:59999/down-webhook-endpoint"),
        ])
        self.assertTrue(webhook_logs, "Debe existir un registro en la cola de webhooks")
        self.assertEqual(webhook_logs[0].state, "pending", "Debe quedar en estado pendiente tras intento fallido")
        self.assertGreaterEqual(webhook_logs[0].attempts, 1)
        self.assertTrue(webhook_logs[0].last_error, "Debe registrar el detalle del fallo de conexión")

