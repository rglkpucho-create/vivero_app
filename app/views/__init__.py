"""
EcoSistem Views Package — Registro de Blueprints Modulares.

Estructura:
  - auth.py        → Autenticación (login, registro, logout)
  - dashboard.py   → Dashboard y motor IA
  - inventario.py  → CRUD inventario, APIs
  - compras.py     → Pedidos, proveedores, sedes
  - produccion.py  → Cultivos, labores, especies
  - ventas.py      → POS, facturas, clientes
  - pecuario.py    → Animales, salud, producción pecuaria
  - superadmin.py  → Panel del proveedor del software (empresas, licencias)
  - helpers.py     → Funciones compartidas (FIFO, imágenes, multi-empresa)
"""
from datetime import datetime
from flask import Blueprint
from ..extensions import db

from .auth import auth_bp
from .dashboard import dashboard_bp
from .inventario import inventario_bp
from .compras import compras_bp
from .produccion import produccion_bp
from .ventas import ventas_bp
from .pecuario import pecuario_bp
from .admin import admin_bp
from .superadmin import superadmin_bp
from .tienda import tienda_bp
from .mano_obra import mano_obra_bp
from .reportes import reportes_bp
from .cotizaciones import cotizaciones_bp
from .cartera import cartera_bp
from .etiquetas import etiquetas_bp

# Blueprint principal para compatibilidad
main_bp = Blueprint('main', __name__)


def register_blueprints(app):
    """Registra todos los blueprints en la app Flask."""
    
    # Context processor a nivel de APP (disponible para TODOS los templates)
    @app.context_processor
    def inject_globals():
        from flask_login import current_user
        from flask import session
        from sqlalchemy import or_
        from ..models import Empresa, Venta
        from .helpers import filtrar_por_empresa, obtener_empresa_activa
        
        superadmin_empresas = []
        superadmin_selected_empresa_name = "Todas las Empresas"
        pedidos_web_pendientes_count = 0
        empresa_activa = None
        
        if current_user.is_authenticated:
            empresa_activa = obtener_empresa_activa()
            try:
                pedidos_web_pendientes_count = filtrar_por_empresa(Venta.query, Venta).filter(
                    or_(
                        Venta.numero_factura.ilike('WEB-%'),
                        Venta.estado == 'Pedido Web'
                    ),
                    Venta.estado.in_(['Borrador', 'Pedido Web'])
                ).count()
            except Exception:
                pedidos_web_pendientes_count = 0

            if current_user.es_superadmin:
                superadmin_empresas = Empresa.query.order_by(Empresa.nombre).all()
                sel_id = session.get('superadmin_empresa_id')
                if sel_id:
                    emp = db.session.get(Empresa, sel_id)
                    if emp:
                        superadmin_selected_empresa_name = emp.nombre
                    
        return dict(
            datetime=datetime,
            superadmin_empresas=superadmin_empresas,
            superadmin_selected_empresa_name=superadmin_selected_empresa_name,
            pedidos_web_pendientes_count=pedidos_web_pendientes_count,
            empresa_activa=empresa_activa
        )
    
    # Middleware: verificar licencia en CADA request autenticado
    @app.before_request
    def verificar_licencia_middleware():
        from flask_login import current_user
        from flask import render_template as rt
        if current_user.is_authenticated and not current_user.es_superadmin:
            if current_user.empresa and not current_user.empresa.licencia_activa:
                from flask_login import logout_user
                logout_user()
                return rt('licencia_suspendida.html'), 403
    
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(inventario_bp)
    app.register_blueprint(compras_bp)
    app.register_blueprint(produccion_bp)
    app.register_blueprint(ventas_bp)
    app.register_blueprint(pecuario_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(superadmin_bp)
    app.register_blueprint(tienda_bp)
    app.register_blueprint(mano_obra_bp)
    app.register_blueprint(reportes_bp)
    app.register_blueprint(cotizaciones_bp)
    app.register_blueprint(cartera_bp)
    app.register_blueprint(etiquetas_bp)
