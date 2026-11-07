from datetime import datetime, timedelta, timezone
from odoo.tests.common import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestShopIntegrationProductsApi(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_api = cls.env["res.users"].create({
            "name": "API User",
            "login": "api_user",
            "password": "api_password_123",
            "email": "api_user@test.com",
            "groups_id": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("sales_team.group_sale_salesman").id,
                cls.env.ref("stock.group_stock_user").id,
            ])],
        })

        # Categorías
        cls.categ_elec = cls.env["product.category"].create({"name": "Electrónica API"})
        cls.categ_hogar = cls.env["product.category"].create({"name": "Hogar API"})

        # Almacén y ubicación de stock
        cls.stock_location = cls.env.ref("stock.stock_location_stock")

        # Productos de prueba
        cls.prod_active_saleable = cls.env["product.product"].create({
            "name": "Laptop Pro 15",
            "default_code": "LAP-001",
            "list_price": 1200.0,
            "detailed_type": "product",
            "categ_id": cls.categ_elec.id,
            "active": True,
            "sale_ok": True,
        })

        cls.prod_inactive = cls.env["product.product"].create({
            "name": "Old Desktop PC",
            "default_code": "PC-OLD",
            "list_price": 400.0,
            "detailed_type": "product",
            "categ_id": cls.categ_elec.id,
            "active": False,
            "sale_ok": True,
        })

        cls.prod_no_sale = cls.env["product.product"].create({
            "name": "Internal Cable",
            "default_code": "CAB-INT",
            "list_price": 10.0,
            "detailed_type": "product",
            "categ_id": cls.categ_elec.id,
            "active": True,
            "sale_ok": False,
        })

        cls.prod_hogar = cls.env["product.product"].create({
            "name": "Cafetera Express",
            "default_code": "CAF-002",
            "list_price": 85.0,
            "detailed_type": "product",
            "categ_id": cls.categ_hogar.id,
            "active": True,
            "sale_ok": True,
        })

        # Ajuste de stock: Agregar 15 unidades a Laptop Pro 15
        cls.env["stock.quant"]._update_available_quantity(
            cls.prod_active_saleable, cls.stock_location, 15.0
        )

    def setUp(self):
        super().setUp()
        self.authenticate("api_user", "api_password_123")

    def test_01_get_products_active_and_saleable_only(self):
        """Verifica que solo se retornen productos activos y vendibles."""
        res = self.url_open("/api/v1/products")
        self.assertEqual(res.status_code, 200)

        data = res.json()
        self.assertIsInstance(data, list)
        product_ids = [p["id"] for p in data]

        self.assertIn(self.prod_active_saleable.id, product_ids)
        self.assertIn(self.prod_hogar.id, product_ids)
        self.assertNotIn(self.prod_inactive.id, product_ids, "Los productos inactivos no deben aparecer")
        self.assertNotIn(self.prod_no_sale.id, product_ids, "Los productos con sale_ok=False no deben aparecer")

        # Verificar estructura de campos
        laptop_item = next(p for p in data if p["id"] == self.prod_active_saleable.id)
        self.assertEqual(laptop_item["code"], "LAP-001")
        self.assertEqual(laptop_item["name"], "Laptop Pro 15")
        self.assertEqual(laptop_item["price"], 1200.0)
        self.assertEqual(laptop_item["qty_available"], 15.0)

    def test_02_filter_by_category(self):
        """Verifica filtrado por category_id."""
        res = self.url_open(f"/api/v1/products?category_id={self.categ_elec.id}")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        product_ids = [p["id"] for p in data]

        self.assertIn(self.prod_active_saleable.id, product_ids)
        self.assertNotIn(self.prod_hogar.id, product_ids)

    def test_03_filter_in_stock(self):
        """Verifica el filtro «solo con stock»."""
        res = self.url_open("/api/v1/products?in_stock=true")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        product_ids = [p["id"] for p in data]

        # Laptop tiene 15 unidades de stock
        self.assertIn(self.prod_active_saleable.id, product_ids)
        # Cafetera tiene 0 de stock
        self.assertNotIn(self.prod_hogar.id, product_ids)

    def test_04_filter_updated_since(self):
        """Verifica el filtro «modificados desde» una fecha."""
        past_date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        future_date = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")

        res_past = self.url_open(f"/api/v1/products?updated_since={past_date}")
        self.assertEqual(res_past.status_code, 200)
        data_past = res_past.json()
        self.assertTrue(len(data_past) > 0)

        res_future = self.url_open(f"/api/v1/products?updated_since={future_date}")
        self.assertEqual(res_future.status_code, 200)
        data_future = res_future.json()
        self.assertEqual(len(data_future), 0, "No debería haber productos modificados en una fecha futura")

    def test_05_combined_filters(self):
        """Verifica la combinación de categoría, stock y updated_since."""
        past_date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        url = f"/api/v1/products?category_id={self.categ_elec.id}&in_stock=true&updated_since={past_date}"
        res = self.url_open(url)
        self.assertEqual(res.status_code, 200)
        data = res.json()

        product_ids = [p["id"] for p in data]
        self.assertIn(self.prod_active_saleable.id, product_ids)
        self.assertNotIn(self.prod_hogar.id, product_ids)

    def test_06_invalid_date_format_returns_400_not_500(self):
        """Una fecha mal escrita debe devolver HTTP 400 claro con formato de error, jamás HTTP 500."""
        res = self.url_open("/api/v1/products?updated_since=invalid-date-format")
        self.assertEqual(res.status_code, 400, "Debe retornar 400 Bad Request")
        data = res.json()
        self.assertIn("error", data)
        self.assertEqual(data["error"]["code"], "INVALID_DATE_FORMAT")
        self.assertEqual(data["error"]["field"], "updated_since")

    def test_07_invalid_category_returns_error(self):
        """IDs de categoría inválidos o no existentes retornan errores claros."""
        res_text = self.url_open("/api/v1/products?category_id=not_an_int")
        self.assertEqual(res_text.status_code, 400)
        self.assertEqual(res_text.json()["error"]["code"], "INVALID_CATEGORY_ID")

        res_not_found = self.url_open("/api/v1/products?category_id=999999")
        self.assertEqual(res_not_found.status_code, 404)
        self.assertEqual(res_not_found.json()["error"]["code"], "CATEGORY_NOT_FOUND")

