# API de Integración para Tienda en Línea (`shop_integration_api`)

Módulo de integración REST API para la sincronización de catálogo de productos, existencias en tiempo real y recepción de pedidos de venta desde plataformas de comercio electrónico externas.

---

## Tramo A — Catálogo de Productos y Existencias

### Endpoint
- **URL**: `GET /api/v1/products`
- **Autenticación**: `auth="user"` (Sesión activa de usuario autenticado en Odoo).
- **Alcance de Registros**: Retorna únicamente productos vendibles y activos (`sale_ok = True` y `active = True`).

### Parámetros de Consulta (Query Params)
Todos los filtros son opcionales y pueden utilizarse de forma individual o combinada:

| Parámetro | Tipo | Descripción | Ejemplo |
| :--- | :--- | :--- | :--- |
| `category_id` | Entero | Filtra productos pertenecientes a la categoría indicada o a cualquiera de sus subcategorías (`child_of`). | `?category_id=5` |
| `in_stock` | Booleano | Si es `true` o `1`, restringe el listado exclusivamente a productos con stock disponible (`qty_available > 0`). | `?in_stock=true` |
| `updated_since` | ISO 8601 | Filtra productos modificados a partir de la fecha y hora proporcionada (`write_date >= fecha`). Convierte zonas horarias a UTC. | `?updated_since=2026-11-01T00:00:00Z` |
| `page` | Entero | (Opcional) Número de página para navegación paginada. | `?page=1` |
| `limit` | Entero | (Opcional) Límite de registros por página. | `?limit=20` |

### Respuestas

#### Respuesta Exitosa (HTTP 200 OK)
Formato de lista estándar:
```json
[
  {
    "id": 105,
    "code": "LAP-001",
    "name": "Laptop Pro 15",
    "price": 1200.0,
    "qty_available": 15.0
  },
  {
    "id": 106,
    "code": "CAF-002",
    "name": "Cafetera Express",
    "price": 85.0,
    "qty_available": 0.0
  }
]
```

Si se usan parámetros de paginación (`page` o `limit`):
```json
{
  "total": 45,
  "page": 1,
  "limit": 20,
  "total_pages": 3,
  "next": 2,
  "prev": null,
  "products": [ ... ]
}
```

#### Respuestas de Error
Formato consistente y predecible para clientes API:
- **HTTP 400 Bad Request** (Fecha inválida):
  ```json
  {
    "error": {
      "code": "INVALID_DATE_FORMAT",
      "field": "updated_since",
      "message": "El parámetro 'updated_since' no tiene un formato de fecha válido. Use el estándar ISO 8601 (ej. 'YYYY-MM-DD' o 'YYYY-MM-DDTHH:MM:SS')."
    }
  }
  ```
- **HTTP 400 Bad Request** (ID de categoría no numérico):
  ```json
  {
    "error": {
      "code": "INVALID_CATEGORY_ID",
      "field": "category_id",
      "message": "El parámetro 'category_id' debe ser un número entero válido."
    }
  }
  ```
- **HTTP 404 Not Found** (Categoría inexistente):
  ```json
  {
    "error": {
      "code": "CATEGORY_NOT_FOUND",
      "field": "category_id",
      "message": "No existe ninguna categoría de producto con el id 999999."
    }
  }
  ```

---

## Pruebas Automatizadas
Suite implementada en `tests/test_products_api.py` utilizando `HttpCase`:
- `test_01_get_products_active_and_saleable_only`: Verifica exclusión de productos inactivos o no vendibles y estructura del payload.
- `test_02_filter_by_category`: Verifica aislamiento por categoría.
- `test_03_filter_in_stock`: Verifica filtro `in_stock=true`.
- `test_04_filter_updated_since`: Verifica filtro de fecha pasada y futura.
- `test_05_combined_filters`: Verifica combinación simultánea de los 3 filtros.
- `test_06_invalid_date_format_returns_400_not_500`: Comprueba que una fecha mal formada retorna HTTP 400 con código `INVALID_DATE_FORMAT` en vez de explotar en error interno 500.
- `test_07_invalid_category_returns_error`: Comprueba validación de identificadores de categoría (400 y 404).

