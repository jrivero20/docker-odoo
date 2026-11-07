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


---

## Tramo B — Creación de Pedidos y Auditoría de Llamadas

### 1. Autenticación NATIVA con API Keys (`res.users.apikeys`)
- **Cabecera Requerida**: `Authorization: Bearer <api_key>`
- Implementación respaldada directamente por el modelo nativo `res.users.apikeys` de Odoo 17 (`_check_credentials(scope="rpc", key=token)`).
- Si la cabecera no se suministra o la clave no es válida, el servidor responde **HTTP 401 Unauthorized**:
  ```json
  {
    "error": {
      "code": "UNAUTHORIZED",
      "message": "No se proporcionó la cabecera 'Authorization: Bearer <key>' requerida."
    }
  }
  ```

---

### 2. Creación de Pedidos de Venta
- **URL**: `POST /api/v1/orders`
- **Autenticación**: `Authorization: Bearer <api_key>`
- **Content-Type**: `application/json`

#### Payload de Petición
```json
{
  "vat": "J-30456789-0",
  "client_order_ref": "ECOMMERCE-1001",
  "lines": [
    {
      "default_code": "MON-027",
      "qty": 2
    },
    {
      "default_code": "TEC-RGB",
      "qty": 3
    }
  ]
}
```

#### Supuesto de Diseño: Estado del Pedido
> [!IMPORTANT]
> **Supuesto Documentado**: Los pedidos creados vía API quedan registrados en estado de **Cotización (`draft`)**.
> **Justificación de Negocio**: Esto garantiza que el departamento de ventas y logística pueda verificar disponibilidad física de almacén, condiciones de entrega y políticas de crédito del cliente antes de confirmar el pedido y reservar formalmente el inventario.

#### Respuesta Exitosa (HTTP 201 Created)
```json
{
  "id": 142,
  "name": "S00142",
  "client_order_ref": "ECOMMERCE-1001",
  "state": "draft",
  "partner": {
    "id": 89,
    "name": "Comercializadora El Sol C.A.",
    "vat": "J-30456789-0"
  },
  "amount_untaxed": 680.0,
  "amount_tax": 102.0,
  "amount_total": 782.0,
  "lines": [
    {
      "product_id": 501,
      "default_code": "MON-027",
      "name": "Monitor Curvo 27",
      "qty": 2.0,
      "price_unit": 250.0,
      "price_subtotal": 500.0
    },
    {
      "product_id": 502,
      "default_code": "TEC-RGB",
      "name": "Teclado Mecánico RGB",
      "qty": 3.0,
      "price_unit": 60.0,
      "price_subtotal": 180.0
    }
  ]
}
```

#### Manejo de Errores Específicos (HTTP 422 Unprocessable Entity)
Cumple estrictamente con el formato estandarizado indicando el campo exacto del error:

- **Cliente no encontrado por RIF (`vat`)**:
  ```json
  {
    "error": {
      "code": "CUSTOMER_NOT_FOUND",
      "field": "vat",
      "message": "No existe ningún cliente registrado con el RIF J-99999999-9"
    }
  }
  ```
- **Producto inexistente en línea específica**:
  ```json
  {
    "error": {
      "code": "PRODUCT_NOT_FOUND",
      "field": "lines[1].default_code",
      "message": "No existe un producto con el código NO-EXISTE-XYZ"
    }
  }
  ```
- **Cantidad cero o negativa en línea específica**:
  ```json
  {
    "error": {
      "code": "INVALID_QUANTITY",
      "field": "lines[0].qty",
      "message": "La cantidad del producto MON-027 debe ser mayor que cero."
    }
  }
  ```

---

### 3. Modelo de Registro y Auditoría de Llamadas (`shop.api.log`)
Cada llamada recibida en los endpoints de la API queda registrada en el modelo `shop.api.log`, accesible desde el menú **Ventas > Configuración > Logs API Tienda**.

- **Campos registrados**:
  - `endpoint`: URL invocada (ej. `/api/v1/orders`).
  - `method`: Método HTTP (`POST`, `GET`).
  - `status_code`: Código HTTP de respuesta devuelto (ej. 200, 201, 401, 422).
  - `duration_ms`: Duración exacta de la petición en milisegundos.
  - `user_id`: Usuario identificado tras la validación de la API Key.
  - `request_payload`: Cuerpo JSON de la petición entrante (sanitizado).
  - `response_payload`: Respuesta enviada al cliente.
  - `ip_address`: Dirección IP de origen.
  - `error_message`: Detalle técnico del error en peticiones fallidas.

> [!CAUTION]
> **Seguridad y Privacidad**:
> 1. **Aislamiento transaccional**: El log se registra en un cursor independiente (`request.env.registry.cursor()`). Esto asegura que incluso si la transacción de negocio falla con rollback (HTTP 401, 422, 500), el registro de log persiste intacto en la base de datos.
> 2. **Cero exposición de credenciales**: La clave API de la cabecera `Authorization` jamás se guarda ni se propaga en los campos del log.
