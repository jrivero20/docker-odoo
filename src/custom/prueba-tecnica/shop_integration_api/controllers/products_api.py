import json
from datetime import datetime, timezone
from odoo import http
from odoo.http import request, Response


class ShopIntegrationProductsController(http.Controller):

    def _json_response(self, data, status=200):
        return Response(
            json.dumps(data, ensure_ascii=False),
            status=status,
            content_type="application/json;charset=utf-8",
        )

    def _error_response(self, code, message, field=None, status=422):
        error_body = {
            "error": {
                "code": code,
                "message": message,
            }
        }
        if field:
            error_body["error"]["field"] = field
        return self._json_response(error_body, status=status)

    @http.route("/api/v1/products", type="http", auth="user", methods=["GET"], csrf=False)
    def get_products(self, **kwargs):
        """Consulta de catálogo de productos con stock disponible y filtros opcionales.

        Filtros:
        - category_id: Filtra productos de esa categoría y subcategorías (child_of).
        - in_stock: Si es 'true' o '1', solo productos con cantidad disponible > 0.
        - updated_since: Fecha ISO 8601 (ej. 'YYYY-MM-DD' o 'YYYY-MM-DDTHH:MM:SS').
        """
        domain = [
            ("active", "=", True),
            ("sale_ok", "=", True),
        ]

        # 1. Filtro por categoría
        category_id = kwargs.get("category_id")
        if category_id:
            try:
                categ_id_int = int(category_id)
            except (ValueError, TypeError):
                return self._error_response(
                    code="INVALID_CATEGORY_ID",
                    field="category_id",
                    message="El parámetro 'category_id' debe ser un número entero válido.",
                    status=400,
                )

            category = request.env["product.category"].browse(categ_id_int)
            if not category.exists():
                return self._error_response(
                    code="CATEGORY_NOT_FOUND",
                    field="category_id",
                    message=f"No existe ninguna categoría de producto con el id {categ_id_int}.",
                    status=404,
                )
            domain.append(("categ_id", "child_of", categ_id_int))

        # 2. Filtro «solo con stock»
        in_stock = kwargs.get("in_stock")
        if in_stock in ("true", "1", "True", True):
            domain.append(("qty_available", ">", 0))

        # 3. Filtro «modificados desde» una fecha
        updated_since = kwargs.get("updated_since")
        if updated_since:
            try:
                clean_str = updated_since.strip().replace("Z", "+00:00")
                parsed_dt = datetime.fromisoformat(clean_str)
                # Convertir a UTC naive para coincidir con el campo write_date de PostgreSQL en Odoo
                if parsed_dt.tzinfo is not None:
                    parsed_dt = parsed_dt.astimezone(timezone.utc).replace(tzinfo=None)
                domain.append(("write_date", ">=", parsed_dt))
            except (ValueError, TypeError):
                return self._error_response(
                    code="INVALID_DATE_FORMAT",
                    field="updated_since",
                    message="El parámetro 'updated_since' no tiene un formato de fecha válido. Use el estándar ISO 8601 (ej. 'YYYY-MM-DD' o 'YYYY-MM-DDTHH:MM:SS').",
                    status=400,
                )

        Product = request.env["product.product"]
        total_records = Product.search_count(domain)

        # Soporte para paginación (si se solicitan page o limit)
        page_param = kwargs.get("page")
        limit_param = kwargs.get("limit")

        if page_param or limit_param:
            try:
                page = max(1, int(page_param or 1))
                limit = max(1, int(limit_param or 20))
            except (ValueError, TypeError):
                return self._error_response(
                    code="INVALID_PAGINATION",
                    message="Los parámetros 'page' y 'limit' deben ser enteros positivos.",
                    status=400,
                )

            offset = (page - 1) * limit
            products = Product.search(domain, offset=offset, limit=limit, order="id asc")
            total_pages = (total_records + limit - 1) // limit if limit else 1

            next_page = page + 1 if page < total_pages else None
            prev_page = page - 1 if page > 1 else None

            products_data = [
                {
                    "id": p.id,
                    "code": p.default_code or "",
                    "name": p.name,
                    "price": p.list_price,
                    "qty_available": p.qty_available,
                }
                for p in products
            ]

            return self._json_response({
                "total": total_records,
                "page": page,
                "limit": limit,
                "total_pages": total_pages,
                "next": next_page,
                "prev": prev_page,
                "products": products_data,
            })

        # Sin paginación explícita (respuesta directa de la lista de productos)
        products = Product.search(domain, order="id asc")
        products_data = [
            {
                "id": p.id,
                "code": p.default_code or "",
                "name": p.name,
                "price": p.list_price,
                "qty_available": p.qty_available,
            }
            for p in products
        ]

        return self._json_response(products_data)

