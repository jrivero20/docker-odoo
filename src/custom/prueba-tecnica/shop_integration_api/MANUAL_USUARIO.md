# Manual de Usuario e Integración: API de Tienda en Línea (`shop_integration_api`)

Este manual describe el funcionamiento, consumo y monitoreo del módulo **shop_integration_api**, diseñado para conectar una tienda en línea (e-commerce externo, app móvil o portal B2B) con Odoo 17.

---

## 1. Arquitectura y Seguridad

Todas las peticiones a la API REST requieren autenticación mediante **API Key** nativa de Odoo enviada en la cabecera HTTP:

```http
Authorization: Bearer <TU_CLAVE_API>
Content-Type: application/json
```

### Cómo generar una API Key en Odoo 17
1. Inicie sesión en Odoo con un usuario con permisos de Ventas e Inventario.
2. Haga clic en la esquina superior derecha (icono de perfil / nombre de usuario) y seleccione **Mis Preferencias** (o diríjase a **Ajustes > Usuarios y Compañías > Usuarios**).
3. Seleccione la pestaña **Seguridad de la cuenta** (o **Claves de API**).
4. En la sección **Claves de API**, haga clic en **Nueva clave de API**.
5. Asigne una descripción (ej. `Integracion Tienda Web`) y confirme su contraseña maestra.
6. Copie la clave generada inmediatamente (no volverá a mostrarse).

---

## 2. Consumo de Endpoints (Guía para Desarrolladores y Evaluadores)

### A. Catálogo de Productos y Existencias (`GET /api/v1/products`)

Permite al frontend obtener el catálogo de productos disponibles para la venta con sus precios, impuestos y existencias de almacén en tiempo real.

- **URL:** `http://<servidor-odoo>:8069/api/v1/products`
- **Método:** `GET`
- **Cabeceras:** `Authorization: Bearer <API_KEY>`

#### Parámetros Opcionales de Consulta (Query Params):
| Parámetro | Tipo | Descripción | Ejemplo |
| :--- | :--- | :--- | :--- |
| `category_id` | Entero | Filtra por ID de categoría de producto. | `?category_id=3` |
| `in_stock` | Booleano | `true` para mostrar solo productos con stock disponible > 0. | `?in_stock=true` |
| `updated_since` | Fecha ISO | Devuelve productos modificados a partir de esa fecha. | `?updated_since=2026-01-01T00:00:00` |
| `page` | Entero | Número de página (por defecto: `1`). | `?page=1` |
| `limit` | Entero | Registros por página (por defecto: `20`, máx: `100`). | `?limit=10` |

#### Ejemplo de Petición con cURL:
```bash
curl -X GET "http://localhost:8069/api/v1/products?in_stock=true&limit=5" \
  -H "Authorization: Bearer mi_clave_secreta"
```

#### Ejemplo de Respuesta Exitosa (HTTP 200):
```json
{
  "total": 1,
  "page": 1,
  "limit": 5,
  "pages": 1,
  "data": [
    {
      "id": 14,
      "default_code": "PROD-001",
      "name": "Aceite Sintético 5W30",
      "list_price": 25.0,
      "currency": "USD",
      "categ_id": [3, "Lubricantes"],
      "qty_available": 48.0,
      "uom": "Unidades",
      "taxes": ["IVA 16%"],
      "write_date": "2026-11-07 18:22:10"
    }
  ]
}
```

---

### B. Creación de Pedidos de Venta (`POST /api/v1/orders`)

Permite a la tienda en línea registrar órdenes de compra en Odoo de forma transaccional e idempotente.

- **URL:** `http://<servidor-odoo>:8069/api/v1/orders`
- **Método:** `POST`
- **Cabeceras Obligatorias:**
  - `Authorization: Bearer <API_KEY>`
  - `Content-Type: application/json`
  - `Idempotency-Key: <UUID_UNICO>` *(Evita cobros o pedidos duplicados ante caídas de red)*.

#### Estructura del Payload JSON:
```json
{
  "client_order_ref": "WEB-98421",
  "customer": {
    "vat": "J-12345678-0",
    "name": "Distribuidora Los Andes C.A.",
    "email": "compras@losandes.com",
    "phone": "+58 414 1234567",
    "street": "Av. Francisco de Miranda, Edif. Centro"
  },
  "lines": [
    {
      "product_id": 14,
      "product_uom_qty": 2.0,
      "price_unit": 25.0
    }
  ],
  "note": "Entregar en horario de oficina de 8am a 4pm."
}
```

#### Lógica de Negocio y Reglas de Validación:
1. **Identificación de Cliente:** Si el cliente con ese RIF/VAT ya existe en Odoo, la orden se vincula directamente; si no existe, Odoo lo crea automáticamente con los datos suministrados.
2. **Idempotencia:** Si la tienda envía la misma petición dos veces con la misma `Idempotency-Key`, la segunda petición devolverá la orden creada previamente sin duplicarla.
3. **Validación de Líneas:**
   - La lista de líneas no puede estar vacía.
   - Cada producto debe existir y estar activo para ventas.
   - La cantidad (`product_uom_qty`) debe ser mayor a 0.

#### Ejemplo de Respuesta Exitosa (HTTP 201 Created):
```json
{
  "id": 89,
  "name": "S00089",
  "client_order_ref": "WEB-98421",
  "state": "draft",
  "amount_untaxed": 50.0,
  "amount_tax": 8.0,
  "amount_total": 58.0,
  "currency": "USD",
  "partner": {
    "id": 42,
    "name": "Distribuidora Los Andes C.A.",
    "vat": "J-12345678-0"
  },
  "lines": [
    {
      "product_id": 14,
      "product_name": "Aceite Sintético 5W30",
      "qty": 2.0,
      "price_unit": 25.0,
      "subtotal": 50.0
    }
  ]
}
```

---

## 3. Monitoreo y Auditoría en Tiempo Real desde la Interfaz de Odoo

Para el equipo de soporte funcional y administradores de Odoo, el módulo incluye una consola de auditoría integrada:

1. Ingrese a Odoo y navegue a **Ventas > Configuración > Logs API Tienda**.
2. Podrá visualizar una tabla cronológica con todas las transacciones realizadas por la API:
   - **Fecha y Hora:** Momento exacto de la petición.
   - **Método y Endpoint:** `GET /api/v1/products` o `POST /api/v1/orders`.
   - **Código HTTP:** Identificador visual con colores (Verde para `200/201`, Rojo para errores `400/401/404/500`).
   - **Duración (ms):** Tiempo de respuesta del servidor en milisegundos.
   - **Usuario e IP:** Auditoría de origen.

### Inspección a detalle de una petición
Al abrir cualquier registro del log, se accede al formulario de diagnóstico:
- **Pestaña "Payload Enviado":** JSON exacto recibido desde la tienda web.
- **Pestaña "Respuesta Devuelta":** JSON exacto retornado por Odoo.
- **Pestaña "Error":** Si la petición falló, muestra la traza técnica y el mensaje de error para soporte inmediato.

---

## 4. Webhooks Salientes: Notificación de Despacho (Tramo C)

Cuando el equipo de almacén valida y despacha un pedido generado por la tienda:
1. En **Inventario / Albaranes de Entrega**, al validar el despacho (`stock.picking`), Odoo dispara automáticamente un webhook saliente hacia la URL configurada de la tienda.
2. La carga útil contiene el número de pedido, albarán, transportista y número de guía de seguimiento.
3. El paquete se asegura mediante una firma criptográfica en la cabecera `X-Shop-Signature` utilizando HMAC-SHA256 para certificar la autenticidad del mensaje.

