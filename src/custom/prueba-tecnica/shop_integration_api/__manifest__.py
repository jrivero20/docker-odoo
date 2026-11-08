{
    "name": "API de Integración para Tienda en Línea",
    "summary": "Endpoints REST y webhooks para sincronización de catálogo, stock y pedidos",
    "version": "17.0.1.0.0",
    "category": "Sales/Sales",
    "author": "Binaural",
    "license": "LGPL-3",
    "depends": ["base", "sale_management", "stock", "sale_stock"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron_data.xml",
        "views/api_log_views.xml",
    ],
    "installable": True,
    "application": True,
}

