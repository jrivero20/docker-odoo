import json
from odoo.tests.common import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestShopIntegrationOrdersApi(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Usuario para API
        cls.user_api = cls.env["res.users"].create({
            "name": "Shop API Bot",
            "login": "shop_bot",
            "password": "shop_bot_password_123",
            "email": "shop_bot@test.com",
            "groups_id": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("sales_team.group_sale_salesman").id,
                cls.env.ref("stock.group_stock_user").id,
            ])],
        })

        # Generar API key nativa usando res.users.apikeys
        cls.raw_api_key = cls.env["res.users.apikeys"].with_user(cls.user_api)._generate(
            None, "Integration Bot Key"
        )

        # Cliente de prueba con RIF
        cls.customer = cls.env["res.partner"].create({
            "name": "Comercializadora El Sol C.A.",
            "vat": "J-30456789-0",
            "email": "contacto@elsol.com",
        })

        # Productos de prueba
        cls.prod_monitor = cls.env["product.product"].create({
            "name": "Monitor Curvo 27",
            "default_code": "MON-027",
            "list_price": 250.0,
            "detailed_type": "product",
            "active": True,
            "sale_ok": True,
        })

        cls.prod_teclado = cls.env["product.product"].create({
            "name": "Teclado Mecánico RGB",
            "default_code": "TEC-RGB",
            "list_price": 60.0,
            "detailed_type": "product",
            "active": True,
            "sale_ok": True,
        })

    def _post_order(self, payload, token=None, headers=None):
        req_headers = {"Content-Type": "application/json"}
        if token is not None:
            req_headers["Authorization"] = f"Bearer {token}"
        elif headers and "Authorization" in headers:
            req_headers["Authorization"] = headers["Authorization"]

        if headers:
            for k, v in headers.items():
                if k != "Authorization":
                    req_headers[k] = v

        data_str = json.dumps(payload) if isinstance(payload, (dict, list)) else payload
        return self.url_open(
            "/api/v1/orders",
            data=data_str.encode("utf-8") if data_str else None,
            headers=req_headers,
        )

    def test_01_unauthorized_without_key_or_invalid_key(self):
        """Sin clave o con clave inválida retorna HTTP 401 y código UNAUTHORIZED."""
        # 1. Sin cabecera
        res_no_key = self._post_order({"vat": self.customer.vat})
        self.assertEqual(res_no_key.status_code, 401)
        data_no_key = res_no_key.json()
        self.assertEqual(data_no_key["error"]["code"], "UNAUTHORIZED")

        # 2. Con clave inválida
        res_bad_key = self._post_order({"vat": self.customer.vat}, token="clave_falsa_invalida_12345")
        self.assertEqual(res_bad_key.status_code, 401)
        data_bad_key = res_bad_key.json()
        self.assertEqual(data_bad_key["error"]["code"], "UNAUTHORIZED")

    def test_02_create_order_success(self):
        """Crea pedido de venta exitosamente y valida datos devueltos."""
        payload = {
            "vat": self.customer.vat,
            "client_order_ref": "ECOMMERCE-1001",
            "lines": [
                {"default_code": "MON-027", "qty": 2},
                {"default_code": "TEC-RGB", "qty": 3},
            ],
        }

        res = self._post_order(payload, token=self.raw_api_key)
        self.assertEqual(res.status_code, 201)
        data = res.json()

        self.assertIn("id", data)
        self.assertEqual(data["client_order_ref"], "ECOMMERCE-1001")
        self.assertEqual(data["state"], "draft")
        self.assertEqual(data["partner"]["vat"], self.customer.vat)
        self.assertEqual(len(data["lines"]), 2)

        # Montos: base imponible = (2 * 250) + (3 * 60) = 500 + 180 = 680
        self.assertEqual(data["amount_untaxed"], 680.0)

        # Verificar registro creado en base de datos
        order = self.env["sale.order"].browse(data["id"])
        self.assertTrue(order.exists())
        self.assertEqual(data["amount_total"], order.amount_total)
        self.assertEqual(order.partner_id.id, self.customer.id)
        self.assertEqual(len(order.order_line), 2)

    def test_03_customer_not_found(self):
        """RIF inexistente retorna HTTP 422 con campo 'vat' y CUSTOMER_NOT_FOUND."""
        payload = {
            "vat": "J-99999999-9",
            "client_order_ref": "ECOMMERCE-1002",
            "lines": [
                {"default_code": "MON-027", "qty": 1},
            ],
        }

        res = self._post_order(payload, token=self.raw_api_key)
        self.assertEqual(res.status_code, 422)
        data = res.json()
        self.assertEqual(data["error"]["code"], "CUSTOMER_NOT_FOUND")
        self.assertEqual(data["error"]["field"], "vat")
        self.assertIn("J-99999999-9", data["error"]["message"])

    def test_04_product_not_found(self):
        """Producto inexistente retorna HTTP 422 con campo exacto lines[i].default_code."""
        payload = {
            "vat": self.customer.vat,
            "client_order_ref": "ECOMMERCE-1003",
            "lines": [
                {"default_code": "MON-027", "qty": 1},
                {"default_code": "NO-EXISTE-XYZ", "qty": 2},
            ],
        }

        res = self._post_order(payload, token=self.raw_api_key)
        self.assertEqual(res.status_code, 422)
        data = res.json()
        self.assertEqual(data["error"]["code"], "PRODUCT_NOT_FOUND")
        self.assertEqual(data["error"]["field"], "lines[1].default_code")
        self.assertIn("NO-EXISTE-XYZ", data["error"]["message"])

    def test_05_invalid_quantity_zero_or_negative(self):
        """Cantidad cero o negativa retorna HTTP 422 con campo exacto lines[i].qty."""
        # Cantidad cero
        payload_zero = {
            "vat": self.customer.vat,
            "client_order_ref": "ECOMMERCE-1004",
            "lines": [
                {"default_code": "MON-027", "qty": 0},
            ],
        }
        res_zero = self._post_order(payload_zero, token=self.raw_api_key)
        self.assertEqual(res_zero.status_code, 422)
        data_zero = res_zero.json()
        self.assertEqual(data_zero["error"]["code"], "INVALID_QUANTITY")
        self.assertEqual(data_zero["error"]["field"], "lines[0].qty")

        # Cantidad negativa
        payload_neg = {
            "vat": self.customer.vat,
            "client_order_ref": "ECOMMERCE-1005",
            "lines": [
                {"default_code": "TEC-RGB", "qty": -3},
            ],
        }
        res_neg = self._post_order(payload_neg, token=self.raw_api_key)
        self.assertEqual(res_neg.status_code, 422)
        data_neg = res_neg.json()
        self.assertEqual(data_neg["error"]["code"], "INVALID_QUANTITY")
        self.assertEqual(data_neg["error"]["field"], "lines[0].qty")

    def test_06_api_call_logging_and_no_key_exposure(self):
        """Verifica que cada llamada queda registrada en shop.api.log (éxito y fallo) sin guardar la clave."""
        # Limpiar logs previos para aislamiento
        self.env["shop.api.log"].search([]).unlink()

        # 1. Llamada fallida por falta de autenticación
        self._post_order({"vat": "J-00000000-0"})

        # 2. Llamada fallida por error 422
        self._post_order({
            "vat": "J-99999999-9",
            "lines": [{"default_code": "MON-027", "qty": 1}],
        }, token=self.raw_api_key)

        # 3. Llamada exitosa 201
        self._post_order({
            "vat": self.customer.vat,
            "lines": [{"default_code": "MON-027", "qty": 1}],
        }, token=self.raw_api_key)

        # Buscar logs generados
        logs = self.env["shop.api.log"].search([("endpoint", "=", "/api/v1/orders")], order="id asc")
        self.assertGreaterEqual(len(logs), 3, "Deben haberse registrado al menos 3 llamadas en el log")

        status_codes = [log.status_code for log in logs]
        self.assertIn(401, status_codes, "Llamada sin clave debe quedar registrada con 401")
        self.assertIn(422, status_codes, "Llamada con error de validación debe quedar con 422")
        self.assertIn(201, status_codes, "Llamada exitosa debe quedar con 201")

        # Verificar duración y que NO se almacena la API key
        for log in logs:
            self.assertGreaterEqual(log.duration_ms, 0.0)
            if log.request_payload:
                self.assertNotIn(self.raw_api_key, log.request_payload, "El log NUNCA debe guardar la clave API")
            if log.response_payload:
                self.assertNotIn(self.raw_api_key, log.response_payload, "El log NUNCA debe guardar la clave API")
