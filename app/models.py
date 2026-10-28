from .extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone

# ==================================================
# 0. MODELO EMPRESA (MULTI-TENANT / LICENCIAS)
# ==================================================

class Empresa(db.Model):
    """
    Cada cliente que compra/alquila el software EcoSistem.
    Ej: 'Vivero Ecológico', 'Mundo Verde', 'Finca La Esperanza'
    El proveedor del software (SuperAdmin) controla la licencia.
    """
    id = db.Column(db.Integer, primary_key=True)
    
    # Datos de la empresa cliente
    nombre = db.Column(db.String(150), nullable=False)
    nit_rut = db.Column(db.String(30))
    razon_social = db.Column(db.String(200))
    telefono = db.Column(db.String(30))
    email = db.Column(db.String(100))
    direccion = db.Column(db.String(300))
    ciudad = db.Column(db.String(100))
    logo_url = db.Column(db.String(255))
    sitio_web = db.Column(db.String(200))
    
    # Personalización del Sitio Web y Catálogo Online Pro
    slogan = db.Column(db.String(255))
    descripcion_web = db.Column(db.Text)
    sobre_nosotros_largo = db.Column(db.Text)
    servicios_texto = db.Column(db.Text)
    banner_url = db.Column(db.String(300))
    color_tema = db.Column(db.String(20), default='#10b981')
    whatsapp_pedidos = db.Column(db.String(30))
    horario_atencion = db.Column(db.String(150))
    mostrar_precios_web = db.Column(db.Boolean, default=True)
    mostrar_catalogo_web = db.Column(db.Boolean, default=True)  # Decidir si publica catálogo digital o solo web
    tienda_activa = db.Column(db.Boolean, default=True)
    
    # Redes Sociales & Métricas de Impacto del Vivero
    instagram_url = db.Column(db.String(255))
    facebook_url = db.Column(db.String(255))
    tiktok_url = db.Column(db.String(255))
    anios_experiencia = db.Column(db.String(30), default='10+ Años')
    plantas_entregadas = db.Column(db.String(50), default='50,000+')
    hectareas_o_variedades = db.Column(db.String(50), default='150+ Especies')
    
    # Control de licencia y SaaS
    licencia_activa = db.Column(db.Boolean, default=True)
    fecha_registro = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    fecha_vencimiento = db.Column(db.Date, nullable=True)
    plan_nombre = db.Column(db.String(80), default='Plan Pro Vivero')
    precio_suscripcion = db.Column(db.Float, default=150000.0)
    ciclo_pago = db.Column(db.String(30), default='Mensual')
    notas_admin = db.Column(db.Text)  # Notas privadas del proveedor del software
    
    # Relaciones
    usuarios = db.relationship('Usuario', backref='empresa', lazy=True)
    pagos_suscripcion = db.relationship('PagoSuscripcion', backref='empresa', lazy=True, cascade='all, delete-orphan', order_by='desc(PagoSuscripcion.fecha_pago)')

    @property
    def plan_config(self):
        """Retorna la configuración de capacidades y límites del plan contratado."""
        p_norm = (self.plan_nombre or 'Plan Cosecha Pro').lower()
        if 'semilla' in p_norm or 'básico' in p_norm or 'basico' in p_norm:
            return PLANES_SAAS['Plan Semilla']
        elif 'hacienda' in p_norm or 'empresarial' in p_norm or 'ganad' in p_norm:
            return PLANES_SAAS['Plan Agro-Hacienda']
        else:
            return PLANES_SAAS['Plan Cosecha Pro']

    def verificar_limite_usuarios(self):
        """Verifica si la empresa puede crear otro usuario según su plan."""
        from .models import Usuario
        limite = self.plan_config['max_usuarios']
        actual = Usuario.query.filter_by(empresa_id=self.id).count()
        if actual >= limite:
            return False, f"Tu {self.plan_config['nombre']} permite hasta {limite} usuarios ({actual} registrados). Actualiza tu plan para invitar más colaboradores.", actual, limite
        return True, "", actual, limite

    def verificar_limite_sedes(self):
        """Verifica si la empresa puede crear otra sede física."""
        from .models import Sede
        limite = self.plan_config['max_sedes']
        actual = Sede.query.filter_by(empresa_id=self.id).count()
        if actual >= limite:
            return False, f"Tu {self.plan_config['nombre']} permite máximo {limite} sede(s) ({actual} registradas). Actualiza a Plan Cosecha Pro o Agro-Hacienda para añadir más sedes.", actual, limite
        return True, "", actual, limite

    def verificar_limite_lotes(self):
        """Verifica si la empresa puede abrir un nuevo lote de cultivo activo."""
        from .models import LoteProduccion
        limite = self.plan_config['max_lotes']
        actual = LoteProduccion.query.filter_by(empresa_id=self.id, estado='Activo').count()
        if actual >= limite:
            return False, f"Has alcanzado el límite de {limite} lotes activos de tu {self.plan_config['nombre']}. Actualiza a Plan Cosecha Pro para gestionar lotes ilimitados.", actual, limite
        return True, "", actual, limite

    def permite_modulo(self, modulo):
        """Verifica si un módulo funcional está habilitado en el plan."""
        if modulo == 'pecuario':
            return self.plan_config.get('permite_pecuario', False)
        elif modulo == 'mano_obra':
            return self.plan_config.get('permite_mano_obra', True)
        elif modulo == 'tienda_web':
            return self.plan_config.get('permite_tienda_web', True)
        return True

    def __repr__(self):
        return f'<Empresa {self.nombre}>'

# ==================================================
# DICCIONARIO MAESTRO DE PLANES COMERCIALES SAAS (COLOMBIA)
# ==================================================

PLANES_SAAS = {
    'Plan Semilla': {
        'id': 'semilla',
        'nombre': 'Plan Semilla',
        'subtitulo': 'Viveros Pequeños y Productores Familiares',
        'badge': 'Básico Emprendedor',
        'descripcion': 'Ideal para viveros locales, ventas de orquídeas/suculentas o fincas familiares con 1 o 2 trabajadores.',
        'precio_mensual': 59000,
        'precio_semestral': 319000,
        'precio_anual': 590000,
        'ahorro_anual': 'Ahorras 2 meses ($118.000 COP)',
        'max_usuarios': 2,
        'max_sedes': 1,
        'max_lotes': 50,
        'permite_pecuario': False,
        'permite_mano_obra': True,
        'permite_tienda_web': True,
        'permite_qr_trazabilidad': True,
        'color': '#059669',
        'icon': 'bi-sprout',
        'destacado': False,
        'caracteristicas': [
            'Hasta 2 Usuarios (Dueño + 1 Empleado)',
            '1 Sede / Finca principal',
            'Hasta 50 Lotes de cultivo activos',
            'Facturación POS y Ventas de mostrador',
            'Catálogo Digital Web con pedidos directos a WhatsApp',
            'Inventario básico de insumos y plantas',
            'Soporte por WhatsApp en horario comercial'
        ]
    },
    'Plan Cosecha Pro': {
        'id': 'cosecha_pro',
        'nombre': 'Plan Cosecha Pro',
        'subtitulo': 'Viveros Comerciales y Tiendas Botánicas',
        'badge': 'El Más Elegido ⭐',
        'descripcion': 'Para viveros comerciales, tiendas botánicas con local y fincas con venta al público y cuadrillas de campo.',
        'precio_mensual': 119000,
        'precio_semestral': 599000,
        'precio_anual': 1190000,
        'ahorro_anual': 'Ahorras $238.000 COP al año',
        'max_usuarios': 5,
        'max_sedes': 2,
        'max_lotes': 999999,
        'permite_pecuario': False,
        'permite_mano_obra': True,
        'permite_tienda_web': True,
        'permite_qr_trazabilidad': True,
        'color': '#10b981',
        'icon': 'bi-flower1',
        'destacado': True,
        'caracteristicas': [
            'Hasta 5 Usuarios con roles diferenciados',
            'Hasta 2 Sedes (ej. Producción + Local comercial)',
            'Lotes de Cultivo Ilimitados',
            'Códigos QR de Trazabilidad Botánica Pública',
            'Módulo de Mano de Obra y Liquidación de Jornales',
            'Página Web Propia Completa con Carrito a WhatsApp',
            'Gestión de Proveedores, Sedes y Órdenes de Compra',
            'Reportes de Rentabilidad y Utilidades por Cultivo',
            'Soporte Prioritario por WhatsApp'
        ]
    },
    'Plan Agro-Hacienda': {
        'id': 'agro_hacienda',
        'nombre': 'Plan Agro-Hacienda',
        'subtitulo': 'Agroempresas, Reforestación y Ganadería',
        'badge': 'Empresarial & Ganadero',
        'descripcion': 'Para agroempresas de gran escala, viveros de reforestación masiva y haciendas con producción agrícola y animal.',
        'precio_mensual': 229000,
        'precio_semestral': 1190000,
        'precio_anual': 2290000,
        'ahorro_anual': 'Ahorras $458.000 COP al año',
        'max_usuarios': 999999,
        'max_sedes': 999999,
        'max_lotes': 999999,
        'permite_pecuario': True,
        'permite_mano_obra': True,
        'permite_tienda_web': True,
        'permite_qr_trazabilidad': True,
        'color': '#3b82f6',
        'icon': 'bi-trophy',
        'destacado': False,
        'caracteristicas': [
            'Usuarios Ilimitados con auditoría forense',
            'Sedes, Viveros y Fincas Ilimitadas',
            'Módulo Pecuario & Animales Completo (Pesajes, vacunas, partos)',
            'Módulo de Cultivos & Lotes Ilimitados',
            'Mano de Obra Avanzada (Contratistas y múltiples cuadrillas)',
            'E-commerce Multi-tienda con gestión de pedidos web en vivo',
            'Capacitación Virtual Personalizada para el equipo',
            'Soporte VIP Directo 24/7'
        ]
    }
}

# ==================================================
# 0.1 MODELO DE PAGOS DE LICENCIA SAAS
# ==================================================

class PagoSuscripcion(db.Model):
    """
    Registro histórico y financiero de los pagos de suscripción/licencia
    que cada empresa cliente realiza al propietario del software EcoSistem.
    """
    __tablename__ = 'pago_suscripcion'
    
    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresa.id'), nullable=False)
    
    numero_recibo = db.Column(db.String(50), unique=True, nullable=False)  # Ej: REC-2026-0001
    fecha_pago = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    monto = db.Column(db.Float, nullable=False)  # Monto pagado en COP
    metodo_pago = db.Column(db.String(50), default='Transferencia Bancaria') # Nequi, Daviplata, Bancolombia, PSE, Efectivo, Tarjeta
    referencia = db.Column(db.String(100)) # Referencia o código de transacción
    
    # Cobertura y Plan
    plan = db.Column(db.String(80), default='Plan Pro Vivero')
    meses_cobertura = db.Column(db.Integer, default=1)
    fecha_inicio = db.Column(db.Date, nullable=False)
    fecha_fin = db.Column(db.Date, nullable=False)
    
    estado = db.Column(db.String(30), default='Aprobado') # Aprobado, Pendiente, Anulado
    concepto = db.Column(db.String(255)) # Ej: 'Suscripción Semestral EcoSistem Cloud'
    notas = db.Column(db.Text)
    registrado_por = db.Column(db.String(100), default='Propietario / SuperAdmin')
    
    fecha_creacion = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<PagoSuscripcion {self.numero_recibo} - ${self.monto}>'


# ==================================================
# 1. MODELOS DE USUARIOS Y AUTENTICACIÓN
# ==================================================

class Rol(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), unique=True, nullable=False)
    descripcion = db.Column(db.String(255))
    nivel = db.Column(db.Integer, default=4) # 0: SuperAdmin, 1: Admin, 2: Gerente, 3: Operario, 4: Visor
    usuarios = db.relationship('Usuario', backref='rol', lazy=True)

    def __repr__(self):
        return f'<Rol {self.nombre}>'

class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre_completo = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    telefono = db.Column(db.String(20))
    rol_id = db.Column(db.Integer, db.ForeignKey('rol.id'), nullable=True)
    fecha_registro = db.Column(db.Date, default=lambda: datetime.now(timezone.utc))
    activo = db.Column(db.Boolean, default=True)
    ultimo_login = db.Column(db.DateTime)
    
    # Multi-empresa
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresa.id'), nullable=True)
    es_superadmin = db.Column(db.Boolean, default=False)  # Solo el proveedor del software

    def set_password(self, password):
        # Usamos pbkdf2:sha256 explícitamente para asegurar que el hash mida menos de 100 caracteres
        # y evitar el problema de truncamiento de MySQL (scrypt mide más de 160).
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generar_token_recuperacion(self):
        from itsdangerous import URLSafeTimedSerializer
        from flask import current_app
        s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        return s.dumps(self.email, salt='password-reset-salt')

    @property
    def es_admin(self):
        if self.es_superadmin:
            return True
        return self.rol and self.rol.nivel == 1

    def tiene_permiso(self, nivel_requerido):
        if self.es_superadmin:
            return True
        if not self.rol: return False
        return self.rol.nivel <= nivel_requerido

    def __repr__(self):
        return f'<Usuario {self.email}>'

class AuditoriaLog(db.Model):
    """Registro de TODAS las acciones destructivas o financieras."""
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=True)
    usuario = db.relationship('Usuario')
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresa.id'), nullable=True)
    accion = db.Column(db.String(50))     # CREAR, EDITAR, ELIMINAR, VENTA, COMPRA, LOGIN
    modulo = db.Column(db.String(50))
    detalle = db.Column(db.Text)
    ip_origen = db.Column(db.String(45))

# ==================================================
# 2. GESTIÓN DE TERCEROS Y CONFIGURACIÓN
# ==================================================

class Proveedor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresa.id'), nullable=True, index=True)
    razon_social = db.Column(db.String(100), nullable=False)
    nit_rut = db.Column(db.String(20), nullable=False)
    contacto_nombre = db.Column(db.String(100))
    telefono = db.Column(db.String(20))
    email = db.Column(db.String(100))
    direccion = db.Column(db.String(200))
    pedidos = db.relationship('PedidoCompra', backref='proveedor', lazy=True)

    def __repr__(self):
        return f'<Proveedor {self.razon_social}>'

class Sede(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresa.id'), nullable=True, index=True)
    nombre = db.Column(db.String(100), nullable=False)  # Ej: "Finca La Esperanza", "Vivero Central"
    tipo = db.Column(db.String(50))  # Finca, Vivero, Bodega
    ubicacion_geo = db.Column(db.String(200))
    lotes = db.relationship('LoteProduccion', backref='sede', lazy=True)
    pedidos = db.relationship('PedidoCompra', backref='sede', lazy=True)

    def __repr__(self):
        return f'<Sede {self.nombre}>'

class UnidadMedida(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), nullable=False)  # Litro, Kilogramo, Bulto
    abreviatura = db.Column(db.String(10), nullable=False)  # L, Kg, Bto, Und

    def __repr__(self):
        return f'<Unidad {self.abreviatura}>'

# ==================================================
# 3. GESTIÓN DE INVENTARIOS (INSUMOS Y MERCANCÍA)
# ==================================================

class Insumo(db.Model):
    """
    CATÁLOGO MAESTRO:
    Aquí se guardan tanto los insumos de consumo (Abono) 
    como la MERCANCÍA PARA VENTA (Materas, Herramientas, Plantas revendidas).
    """
    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresa.id'), nullable=True, index=True)
    
    # SKU / Código de Barras para el POS
    codigo = db.Column(db.String(50), nullable=True, index=True) 
    
    nombre = db.Column(db.String(100), nullable=False)
    
    # Tipo define el uso: 'Insumo' (Gasto) vs 'Comercial'/'Matera' (Venta)
    tipo = db.Column(db.String(50)) 
    
    unidad_medida_id = db.Column(db.Integer, db.ForeignKey('unidad_medida.id'))
    unidad = db.relationship('UnidadMedida')
    
    stock_minimo = db.Column(db.Float, default=0.0)
    cantidad_actual = db.Column(db.Float, default=0.0) # Inventario Físico Real
    costo_promedio = db.Column(db.Float, default=0.0)  # Costo Ponderado para calcular margen
    imagen_url = db.Column(db.String(255))
    precio_venta = db.Column(db.Float, default=0.0)

    lotes_stock = db.relationship('LoteInsumo', backref='insumo', lazy=True)
    movimientos = db.relationship('MovimientoInventario', backref='insumo', lazy=True)
    inventarios_sedes = db.relationship('InventarioSede', backref='insumo_relacionado', lazy=True)

    def __repr__(self):
        return f'<Insumo {self.nombre}>'

class InventarioSede(db.Model):
    """
    Control de inventario específico por Sede.
    Permite saber cuánto de un Insumo global hay en cada finca/local.
    """
    __table_args__ = (
        db.UniqueConstraint('insumo_id', 'sede_id', name='uq_inventario_insumo_sede'),
    )
    
    id = db.Column(db.Integer, primary_key=True)
    insumo_id = db.Column(db.Integer, db.ForeignKey('insumo.id'), nullable=False, index=True)
    sede_id = db.Column(db.Integer, db.ForeignKey('sede.id'), nullable=False, index=True)
    cantidad = db.Column(db.Float, default=0.0)

    # Relaciones extra explícitas
    sede = db.relationship('Sede', backref='inventarios')

    @property
    def empresa_id(self):
        return self.sede.empresa_id if self.sede else None

class LoteInsumo(db.Model):
    """
    Entradas de mercancía (Compras). 
    Útil para trazabilidad si Pepito compra plantas para revender.
    """
    id = db.Column(db.Integer, primary_key=True)
    insumo_id = db.Column(db.Integer, db.ForeignKey('insumo.id'), nullable=False)
    pedido_id = db.Column(db.Integer, db.ForeignKey('pedido_compra.id'), nullable=True)
    fecha_compra = db.Column(db.Date)
    cantidad_inicial = db.Column(db.Float, nullable=False)
    cantidad_actual = db.Column(db.Float, nullable=False)
    costo_unitario = db.Column(db.Float, nullable=False)
    fecha_vencimiento = db.Column(db.Date, nullable=True)

    @property
    def empresa_id(self):
        return self.insumo.empresa_id if self.insumo else None

class MovimientoInventario(db.Model):
    """
    KARDEX: Historial de todos los movimientos.
    Aquí quedan registrados los 'Ajustes Iniciales' de las materas.
    """
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    tipo_movimiento = db.Column(db.String(50), index=True) # Compra, Venta, Ajuste Inventario
    cantidad = db.Column(db.Float)
    costo_unitario = db.Column(db.Float)
    referencia = db.Column(db.String(100)) # "Ajuste Inicial", "Venta #123"
    insumo_id = db.Column(db.Integer, db.ForeignKey('insumo.id'))

    @property
    def empresa_id(self):
        return self.insumo.empresa_id if self.insumo else None

# ==================================================
# 4. GESTIÓN DE COMPRAS (REABASTECIMIENTO)
# ==================================================

class PedidoCompra(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresa.id'), nullable=True, index=True)
    numero_orden = db.Column(db.String(50), unique=True)
    proveedor_id = db.Column(db.Integer, db.ForeignKey('proveedor.id'), nullable=False)
    sede_id = db.Column(db.Integer, db.ForeignKey('sede.id'), nullable=True)
    fecha_solicitud = db.Column(db.Date)
    fecha_recepcion = db.Column(db.Date, nullable=True)
    
    # Campo para la planificación de llegadas
    fecha_entrega_estimada = db.Column(db.Date, nullable=True) 

    estado = db.Column(db.String(20), default='Borrador', index=True)
    total_estimado = db.Column(db.Float, default=0.0)
    detalles = db.relationship('DetallePedidoCompra', backref='pedido', lazy=True)

class DetallePedidoCompra(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey('pedido_compra.id'))
    insumo_id = db.Column(db.Integer, db.ForeignKey('insumo.id'))
    insumo = db.relationship('Insumo')
    cantidad_solicitada = db.Column(db.Float)
    cantidad_recibida = db.Column(db.Float, default=0)
    precio_unitario = db.Column(db.Float)

    @property
    def empresa_id(self):
        return self.pedido.empresa_id if self.pedido else None

# ==================================================
# 5. MÓDULO DE PRODUCCIÓN (CULTIVOS PROPIOS)
# ==================================================

class Especie(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresa.id'), nullable=True, index=True)
    nombre_comun = db.Column(db.String(100), nullable=False)
    nombre_cientifico = db.Column(db.String(100))
    dias_ciclo_estimado = db.Column(db.Integer)
    detalles_cuidado = db.Column(db.Text)
    imagen_url = db.Column(db.String(255))
    precio_venta_sugerido = db.Column(db.Float, default=0.0) # Valor comercial por unidad
    
    producto_cosecha_id = db.Column(db.Integer, db.ForeignKey('insumo.id'), nullable=True)
    
    lotes = db.relationship('LoteProduccion', backref='especie', lazy=True)
    producto_cosecha = db.relationship('Insumo', foreign_keys=[producto_cosecha_id])

    def __repr__(self):
        return f'<Especie {self.nombre_comun}>'

class LoteProduccion(db.Model):
    """
    Lo que Pepito SIEMBRA y CULTIVA.
    """
    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresa.id'), nullable=True, index=True)
    codigo_lote = db.Column(db.String(50), unique=True)
    especie_id = db.Column(db.Integer, db.ForeignKey('especie.id'))
    sede_id = db.Column(db.Integer, db.ForeignKey('sede.id'))
    
    fecha_siembra = db.Column(db.Date)
    fecha_cosecha_est = db.Column(db.Date, nullable=True)
    
    cantidad_sembrada = db.Column(db.Integer)
    cantidad_actual = db.Column(db.Integer) # Plantas vivas disponibles
    
    ubicacion = db.Column(db.String(100))
    
    # Propósito: 'Venta Plantula' (Vivero) o 'Produccion Fruto' (Cultivo Permanente)
    proposito = db.Column(db.String(20), default='Venta Plantula')
    
    estado = db.Column(db.String(30), index=True) # En Crecimiento, Disponible, Finalizado
    
    costo_total = db.Column(db.Float, default=0.0)
    
    labores = db.relationship('LaborCampo', backref='lote', lazy=True)
    ventas_realizadas = db.relationship('DetalleVenta', backref='lote_origen', lazy=True)

class LaborCampo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lote_id = db.Column(db.Integer, db.ForeignKey('lote_produccion.id'))
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    usuario = db.relationship('Usuario')
    
    fecha = db.Column(db.Date)
    tipo_labor = db.Column(db.String(50))
    descripcion = db.Column(db.Text)
    imagen_url = db.Column(db.String(255)) # Foto de evidencia
    
    consumos = db.relationship('ConsumoInsumo', backref='labor', lazy=True)

    @property
    def empresa_id(self):
        return self.lote.empresa_id if self.lote else None

class ConsumoInsumo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    labor_id = db.Column(db.Integer, db.ForeignKey('labor_campo.id'))
    insumo_id = db.Column(db.Integer, db.ForeignKey('insumo.id'))
    insumo = db.relationship('Insumo')
    
    cantidad = db.Column(db.Float)
    subtotal = db.Column(db.Float)

    @property
    def empresa_id(self):
        return self.labor.lote.empresa_id if self.labor and self.labor.lote else None

# ==================================================
# 6. MÓDULO DE VENTAS (POS)
# ==================================================

class Cliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresa.id'), nullable=True, index=True)
    nombre = db.Column(db.String(100), nullable=False)
    tipo_documento = db.Column(db.String(20), default='CC')
    documento = db.Column(db.String(20))
    telefono = db.Column(db.String(20))
    email = db.Column(db.String(100))
    direccion = db.Column(db.String(200))
    ciudad = db.Column(db.String(100), default='')
    ventas = db.relationship('Venta', backref='cliente', lazy=True)

class Venta(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresa.id'), nullable=True, index=True)
    empresa = db.relationship('Empresa')
    numero_factura = db.Column(db.String(50), unique=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'))
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    usuario = db.relationship('Usuario')
    
    fecha = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    estado = db.Column(db.String(20), index=True)
    subtotal = db.Column(db.Float, default=0.0)
    descuento = db.Column(db.Float, default=0.0)
    impuestos = db.Column(db.Float, default=0.0)
    total = db.Column(db.Float, default=0.0)
    metodo_pago = db.Column(db.String(50), default='Efectivo')
    
    tipo_venta = db.Column(db.String(20), default='Contado')
    es_electronica = db.Column(db.Boolean, default=False)
    fecha_vencimiento = db.Column(db.Date, nullable=True)
    abono = db.Column(db.Float, default=0.0)
    saldo = db.Column(db.Float, default=0.0)
    observaciones = db.Column(db.Text, nullable=True)
    
    detalles = db.relationship('DetalleVenta', backref='venta', lazy=True)

class DetalleVenta(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    venta_id = db.Column(db.Integer, db.ForeignKey('venta.id'))
    
    # 1. Venta de Cosecha Propia (Lotes)
    lote_id = db.Column(db.Integer, db.ForeignKey('lote_produccion.id'), nullable=True)
    
    # 2. Venta de Mercancía/Insumos (Materas, Tierra, Herramientas)
    insumo_id = db.Column(db.Integer, db.ForeignKey('insumo.id'), nullable=True)
    insumo = db.relationship('Insumo')

    # 3. Venta Pecuaria / Ganado / Lotes de Animales
    animal_id = db.Column(db.Integer, db.ForeignKey('lote_animal.id'), nullable=True)
    animal = db.relationship('LoteAnimal', backref=db.backref('ventas_asociadas', lazy=True))

    cantidad = db.Column(db.Float)
    precio_venta_unitario = db.Column(db.Float)
    costo_produccion_unitario = db.Column(db.Float)
    descuento_pct = db.Column(db.Float, default=0.0)
    iva_pct = db.Column(db.Float, default=0.0)
    
    subtotal = db.Column(db.Float)
    ganancia = db.Column(db.Float)

    @property
    def empresa_id(self):
        return self.venta.empresa_id if self.venta else None

# ==================================================
# 7. MÓDULO PECUARIO (ANIMALES) - NIVEL PRO
# ==================================================

class RazaAnimal(db.Model):
    """
    Ficha Técnica precargada de una raza/especie animal.
    Eq. al modelo Especie de cultivos.
    """
    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresa.id'), nullable=True, index=True)
    nombre = db.Column(db.String(100), nullable=False)           # Ej. Vaca Holstein
    especie = db.Column(db.String(50))                           # Bovino, Porcino, Caprino, etc.
    proposito_ideal = db.Column(db.String(100))                  # Producción de Leche, Doble Propósito
    rendimiento_est = db.Column(db.String(100))                  # 25 L/día, 1.2 kg/día
    ciclo_tecnico = db.Column(db.String(100))                    # 305 días lactancia
    cuidados_tecnicos = db.Column(db.Text)                       # Vacunas obligatorias, dieta específica
    imagen_url = db.Column(db.String(255))
    valor_mercado_estimado = db.Column(db.Float, default=0.0) # Valor comercial base
    
    animales = db.relationship('LoteAnimal', backref='raza_rel', lazy=True)

    def __repr__(self):
        return f'<RazaAnimal {self.nombre}>'

class LoteAnimal(db.Model):
    """
    Representa un animal individual (Vaca #01) o un grupo (Galpón Pollos).
    """
    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresa.id'), nullable=True, index=True)
    codigo = db.Column(db.String(50), unique=True) # Arete, Número, ID
    nombre = db.Column(db.String(100))             # "La Lola", "Lote Engorde Dic"
    
    tipo = db.Column(db.String(50))                # Individual / Grupal
    especie = db.Column(db.String(50))             # Bovino, Avícola, Porcino, Caprino (Texto libre o automático)
    raza = db.Column(db.String(50))                # Legacy: Holstein, Angus, Criolla (Texto libre)
    raza_id = db.Column(db.Integer, db.ForeignKey('raza_animal.id'), nullable=True) # Ficha Técnica oficial
    
    genero = db.Column(db.String(20))              # 'Macho' o 'Hembra'
    ubicacion = db.Column(db.String(100))          # 'Corral 1', 'Galpón 2', 'Marranera 1'

    fecha_nacimiento = db.Column(db.Date)          # Vital para saber edad exacta
    fecha_ingreso = db.Column(db.Date)             # Fecha compra o nacimiento en finca
    
    # Cantidad: Si es una vaca es 1. Si es un galpón son 500.
    cantidad_inicial = db.Column(db.Integer, default=1)
    cantidad_actual = db.Column(db.Integer, default=1) 
    
    peso_actual = db.Column(db.Float, default=0.0) # Dato clave para venta de carne
    
    sede_id = db.Column(db.Integer, db.ForeignKey('sede.id'))
    sede = db.relationship('Sede')
    
    proposito = db.Column(db.String(50))           # Leche, Cría, Engorde, Huevo
    estado = db.Column(db.String(30))              # Activo, Enfermo, Cuarentena, Vendido, Muerto
    
    imagen_url = db.Column(db.String(255)) 

    # Costos acumulados (Comida + Medicina + Valor Compra)
    costo_acumulado = db.Column(db.Float, default=0.0)

    # Relaciones
    producciones = db.relationship('ProduccionAnimal', backref='animal', lazy=True)
    consumos = db.relationship('ConsumoAnimal', backref='animal', lazy=True)
    eventos_salud = db.relationship('EventoSanitario', backref='animal', lazy=True)

class ProduccionAnimal(db.Model):
    """
    Lo que el animal nos da: Leche, Huevos, Lana.
    """
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    lote_animal_id = db.Column(db.Integer, db.ForeignKey('lote_animal.id'))
    
    # Producto generado (Debe existir en Inventario como Mercancía)
    producto_id = db.Column(db.Integer, db.ForeignKey('insumo.id')) 
    producto = db.relationship('Insumo')
    
    cantidad = db.Column(db.Float)
    observaciones = db.Column(db.String(200))

    @property
    def empresa_id(self):
        return self.animal.empresa_id if self.animal else None

class ConsumoAnimal(db.Model):
    """
    Lo que el animal gasta: Comida, Sal, Suplementos.
    """
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, default=lambda: datetime.now(timezone.utc))
    lote_animal_id = db.Column(db.Integer, db.ForeignKey('lote_animal.id'))
    
    # Insumo consumido (Debe existir en Inventario como Insumo)
    insumo_id = db.Column(db.Integer, db.ForeignKey('insumo.id'))
    insumo = db.relationship('Insumo')
    
    cantidad = db.Column(db.Float)
    costo_calculado = db.Column(db.Float) # Se calcula con FIFO al momento del registro

    @property
    def empresa_id(self):
        return self.animal.empresa_id if self.animal else None

class EventoSanitario(db.Model):
    """
    DETALLE PROFESIONAL: Historial médico.
    Vacunas, Purgas, Partos, Enfermedades.
    """
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, default=lambda: datetime.now(timezone.utc))
    lote_animal_id = db.Column(db.Integer, db.ForeignKey('lote_animal.id'))
    
    tipo = db.Column(db.String(50)) # Vacunación, Enfermedad, Parto, Pesaje, Vet
    descripcion = db.Column(db.Text)
    costo_servicio = db.Column(db.Float, default=0.0) # Si pagaste al veterinario
    imagen_url = db.Column(db.String(255)) # Foto de evidencia medica
    
    # Si la vacuna salió del inventario, también genera un ConsumoAnimal, 
    # pero aquí queda el registro clínico.

    @property
    def empresa_id(self):
        return self.animal.empresa_id if self.animal else None


# ==================================================
# 7. MODELOS DE MANO DE OBRA Y NÓMINA (FINCA / VIVERO)
# ==================================================

class Trabajador(db.Model):
    """
    Colaboradores y trabajadores del vivero o finca.
    Modalidades:
      - 'Jornal': Pago por día de trabajo.
      - 'Destajo': Pago por tarea / unidad (ej: guadañar potrero, podar árboles, embolsar).
      - 'Fijo': Sueldo periódico (mensual / quincenal).
    """
    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresa.id'), nullable=False)
    empresa = db.relationship('Empresa', backref='trabajadores')
    
    nombre_completo = db.Column(db.String(120), nullable=False)
    documento = db.Column(db.String(30)) # Cédula de Ciudadanía / Identificación
    telefono = db.Column(db.String(30))
    cargo = db.Column(db.String(80)) # Guadañador, Podador, Injertador, Jornalero, Encargado, Administrador
    modalidad = db.Column(db.String(30), default='Jornal') # 'Jornal', 'Destajo', 'Fijo'
    tarifa_base = db.Column(db.Float, default=0.0) # Tarifa de jornal diario, o sueldo base
    sede_id = db.Column(db.Integer, db.ForeignKey('sede.id'), nullable=True)
    sede = db.relationship('Sede')
    
    activo = db.Column(db.Boolean, default=True)
    fecha_ingreso = db.Column(db.Date, default=lambda: datetime.now(timezone.utc).date())
    observaciones = db.Column(db.Text)
    
    pagos = db.relationship('PagoManoObra', backref='trabajador', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Trabajador {self.nombre_completo} ({self.modalidad})>'


class PagoManoObra(db.Model):
    """
    Registro y liquidación de pagos por labores agrícolas, jornales o sueldos.
    Permite calcular: (cantidad * tarifa_unitaria) + bonificaciones - deducciones = total_pagar
    """
    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresa.id'), nullable=False)
    empresa = db.relationship('Empresa')
    
    trabajador_id = db.Column(db.Integer, db.ForeignKey('trabajador.id'), nullable=False)
    
    fecha_registro = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    fecha_labor = db.Column(db.Date, nullable=False, default=lambda: datetime.now(timezone.utc).date())
    
    modalidad = db.Column(db.String(30), nullable=False) # 'Jornal', 'Destajo', 'Fijo'
    labor_realizada = db.Column(db.String(200), nullable=False) # Ej: 'Guadañar potreros bajos', 'Poda de 120 cítricos', 'Sueldo 1ra Quincena Octubre'
    
    # Vinculación opcional a Lote de producción (cultivo) o Sede
    lote_id = db.Column(db.Integer, db.ForeignKey('lote_produccion.id'), nullable=True)
    lote = db.relationship('LoteProduccion')
    
    sede_id = db.Column(db.Integer, db.ForeignKey('sede.id'), nullable=True)
    sede = db.relationship('Sede')
    
    # Liquidación económica
    cantidad = db.Column(db.Float, default=1.0) # Ej: 2.0 días, 100 plantas, 1 quincena
    unidad_medida = db.Column(db.String(30), default='Días') # 'Días', 'Plantas', 'Horas', 'Labor global', 'Mes', 'Quincena'
    tarifa_unitaria = db.Column(db.Float, default=0.0) # Tarifa acordada por unidad o día
    
    bonificaciones = db.Column(db.Float, default=0.0) # Horas extras, incentivos
    deducciones = db.Column(db.Float, default=0.0) # Anticipos, préstamos
    total_pagar = db.Column(db.Float, default=0.0)
    
    estado = db.Column(db.String(20), default='Pagado') # 'Pagado', 'Pendiente'
    fecha_pago = db.Column(db.Date, nullable=True)
    metodo_pago = db.Column(db.String(50), default='Efectivo') # Efectivo, Nequi, Daviplata, Transferencia Bancaria
    
    comprobante_numero = db.Column(db.String(50)) # Ej: 'REC-MO-1792...'
    notas = db.Column(db.Text)
    
    registrado_por_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=True)
    registrado_por = db.relationship('Usuario')

    def __repr__(self):
        return f'<PagoManoObra #{self.id} {self.labor_realizada} - ${self.total_pagar}>'


# ==================================================
# 11. MODELO DE TESTIMONIOS Y CALIFICACIONES WEB
# ==================================================

class TestimonioWeb(db.Model):
    """
    Calificaciones y opiniones públicas de clientes sobre el vivero en su sitio web.
    """
    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresa.id'), nullable=False)
    empresa = db.relationship('Empresa', backref=db.backref('testimonios_web', lazy=True, cascade='all, delete-orphan'))
    
    nombre_cliente = db.Column(db.String(100), nullable=False)
    proyecto_o_ciudad = db.Column(db.String(150), default='Cliente Verificado')
    calificacion = db.Column(db.Integer, default=5) # 1 a 5 estrellas
    comentario = db.Column(db.Text, nullable=False)
    
    fecha = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    aprobado = db.Column(db.Boolean, default=True)
    avatar_color = db.Column(db.String(30), default='#10b981')
    
    def __repr__(self):
        return f'<TestimonioWeb #{self.id} {self.nombre_cliente} ({self.calificacion}★)>'