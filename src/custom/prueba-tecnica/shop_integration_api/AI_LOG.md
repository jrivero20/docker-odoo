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

