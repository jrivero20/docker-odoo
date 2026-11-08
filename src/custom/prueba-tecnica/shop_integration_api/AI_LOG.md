# Bitácora de Desarrollo Asistido por IA (`AI_LOG.md`) — `shop_integration_api`

## Tramo A — Catálogo de Productos y Existencias

### Decisiones de Diseño y Arquitectura
1. **Controlador HTTP REST (`ShopIntegrationProductsController`)**:
   - Implementado en [products_api.py](file:///c:/Users/PC/Desktop/pruebaBinaural/src/custom/prueba-tecnica/shop_integration_api/controllers/products_api.py).
   - Utiliza `auth="user"` garantizando autenticación por sesión Odoo.
   - Restringe la búsqueda por defecto con el dominio `[('active', '=', True), ('sale_ok', '=', True)]`.
2. **Tratamiento de Fechas y Zonas Horarias**:
   - Odoo almacena `write_date` en UTC naive en PostgreSQL.
   - Para evitar inconsistencias de desfase horario, se analiza la cadena ISO 8601 con `datetime.fromisoformat()` y se normaliza a UTC naive antes de armar el dominio.
   - En caso de error de sintaxis en la fecha, se intercepta la excepción para devolver un error estructurado HTTP 400 (`INVALID_DATE_FORMAT`), evitando un error HTTP 500 no controlado.
3. **Validación de Categorías y Jerarquías**:
   - Se usa el operador `child_of` para que al filtrar por una categoría padre se incluyan automáticamente todas sus subcategorías.
   - Se valida numéricamente el parámetro y se verifica la existencia del registro (`.exists()`), retornando HTTP 400 o 404 según corresponda.
4. **Seguridad y Permisos de Acceso en Tests**:
   - Para que el usuario de integración pueda consultar existencias en `stock.quant` / `stock.move` sin violar listas de control de acceso (ACLs), el usuario de API requiere los grupos `sales_team.group_sale_salesman` y `stock.group_stock_user`.
5. **Cobertura con HttpCase**:
   - Implementados 7 casos de prueba que cubren filtrado individual, combinado, estructura de respuesta y manejo de errores. Todos pasan con éxito en la base de datos limpia.



---

## Tramo B — Creación de Pedidos, API Keys y Log de Auditoría

### Decisiones de Diseño y Arquitectura
1. **Autenticación Nativa con `res.users.apikeys`**:
   - Para no duplicar mecanismos de hashing o tablas propietarias de credenciales, se aprovechó la arquitectura nativa de Odoo 17 mediante `res.users.apikeys._check_credentials(scope="rpc", key=api_key)`.
   - Se intercepta la cabecera `Authorization: Bearer <key>`. Si está ausente o no es válida, la API responde con HTTP 401 en formato JSON predecible, evitando redirects web a la pantalla de login.
2. **Validación Exhaustiva y Localización de Errores**:
   - Cada línea de pedido se valida individualmente informando el índice exacto en el campo `field`: `lines[i].default_code` o `lines[i].qty`.
   - Búsqueda de clientes por `vat` tolerante a mayúsculas/minúsculas pero estricta en concordancia.
   - Cantidades verificadas para ser números positivos (`qty > 0`).
3. **Decisión de Negocio sobre el Estado del Pedido (`sale.order`)**:
   - Se optó por dejar el pedido en estado Cotización (`draft`). Justificación: permite al equipo comercial y de almacén validar existencias físicas, líneas arancelarias y disponibilidad real antes de pasar al estado `sale` (bloqueo de inventario y facturación).
4. **Persistencia Inmune de Logs (`shop.api.log`)**:
   - Para cumplir el requerimiento de que *"cada llamada queda en el log, también las que fallan"*, se implementó `record_api_log()` utilizando un cursor de base de datos aislado (`with request.env.registry.cursor() as log_cr`). Si el controlador aborta por un error 422 o 401, el rollback de la transacción principal no anula el registro de auditoría.
   - Se filtran y sanitizan las cargas de datos, garantizando que ninguna API Key sea persistida en texto claro.
5. **Resultados de Pruebas Automatizadas**:
   - Suite completa de 13 pruebas ejecutadas contra `prueba_limpia`:
     - 7 pruebas del Tramo A (`test_products_api.py`)
     - 6 pruebas del Tramo B (`test_orders_api.py`)
   - 100% de éxito: `0 failed, 0 error(s) of 13 tests`.


---

## Tramo C — Optimización, Idempotencia, Webhooks y OpenAPI

### Decisiones de Diseño y Arquitectura
1. **Control de Idempotencia Canónico**:
   - Para evaluar si el contenido es idéntico independientemente del orden de las claves JSON enviadas por el cliente, se serializa el payload canónicamente con `json.dumps(payload, sort_keys=True, separators=(',', ':'))` y se genera un hash SHA-256.
   - Modelo `shop.api.idempotency`: almacena la clave, el hash, el pedido asociado y la respuesta original para reentregarla de forma instantánea sin regenerar registros.
   - Si la clave coincide pero el hash no, se emite un HTTP 409 Conflict explícito.
2. **Mitigación del Problema N+1 en Stock**:
   - Se reemplazó el acceso directo a nivel de objeto por `products.read(["id", "default_code", "name", "list_price", "qty_available"])`, lo cual dispara la evaluación agrupada en lote en PostgreSQL por medio del motor ORM de Odoo 17.
   - La prueba automatizada `test_04_query_count_does_not_grow_with_product_count` verifica cuantitativamente que pasar de 2 a 12 productos mantiene el número de consultas a la base de datos en orden O(1).
3. **Resiliencia y Asincronía en Webhooks de Entrega**:
   - La entrega de mercancía es una operación crítica en almacén. En ningún caso debe verse supeditada al estado de salud de la plataforma de e-commerce.
   - Se interceptó `stock.picking._action_done()` encolando el evento en el modelo `shop.webhook.queue`. El intento inicial se ejecuta con timeout corto protegido; ante fallas de conectividad, una acción planificada (`ir.cron`) reintenta la entrega con backoff sin perturbar al operario en Odoo.
4. **Especificación OpenAPI 3.0**:
   - Entregada en `openapi.yaml`, detallando cabeceras de autorización, contratos de petición y respuesta, modelos de datos, códigos de error y la estructura de eventos de entrega.
5. **Cobertura Total de Pruebas**:
   - 18 pruebas ejecutadas sobre la base de datos `prueba_limpia` (7 de catálogo + 6 de órdenes + 5 de características avanzadas).
   - 100% de éxito: `0 failed, 0 error(s) of 18 tests`.
