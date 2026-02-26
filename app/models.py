from .extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

# ==================================================
# 1. MODELOS DE USUARIOS Y AUTENTICACIÓN
# ==================================================

class Rol(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), unique=True, nullable=False)
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
    fecha_registro = db.Column(db.Date, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<Usuario {self.email}>'

# ==================================================
# 2. GESTIÓN DE TERCEROS Y CONFIGURACIÓN
# ==================================================

class Proveedor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
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
    
    # SKU / Código de Barras para el POS
    codigo = db.Column(db.String(50), nullable=True) 
    
    nombre = db.Column(db.String(100), nullable=False)
    
    # Tipo define el uso: 'Insumo' (Gasto) vs 'Comercial'/'Matera' (Venta)
    tipo = db.Column(db.String(50)) 
    
    unidad_medida_id = db.Column(db.Integer, db.ForeignKey('unidad_medida.id'))
    unidad = db.relationship('UnidadMedida')
    
    stock_minimo = db.Column(db.Float, default=0.0)
    cantidad_actual = db.Column(db.Float, default=0.0) # Inventario Físico Real
    costo_promedio = db.Column(db.Float, default=0.0)  # Costo Ponderado para calcular margen
    imagen_url = db.Column(db.String(255))

    lotes_stock = db.relationship('LoteInsumo', backref='insumo', lazy=True)
    movimientos = db.relationship('MovimientoInventario', backref='insumo', lazy=True)

    def __repr__(self):
        return f'<Insumo {self.nombre}>'

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

class MovimientoInventario(db.Model):
    """
    KARDEX: Historial de todos los movimientos.
    Aquí quedan registrados los 'Ajustes Iniciales' de las materas.
    """
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    tipo_movimiento = db.Column(db.String(50)) # Compra, Venta, Ajuste Inventario
    cantidad = db.Column(db.Float)
    costo_unitario = db.Column(db.Float)
    referencia = db.Column(db.String(100)) # "Ajuste Inicial", "Venta #123"
    insumo_id = db.Column(db.Integer, db.ForeignKey('insumo.id'))

# ==================================================
# 4. GESTIÓN DE COMPRAS (REABASTECIMIENTO)
# ==================================================

class PedidoCompra(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero_orden = db.Column(db.String(50), unique=True)
    proveedor_id = db.Column(db.Integer, db.ForeignKey('proveedor.id'), nullable=False)
    sede_id = db.Column(db.Integer, db.ForeignKey('sede.id'), nullable=True)
    fecha_solicitud = db.Column(db.Date)
    fecha_recepcion = db.Column(db.Date, nullable=True)
    
    # Campo para la planificación de llegadas
    fecha_entrega_estimada = db.Column(db.Date, nullable=True) 

    estado = db.Column(db.String(20), default='Borrador')
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

# ==================================================
# 5. MÓDULO DE PRODUCCIÓN (CULTIVOS PROPIOS)
# ==================================================

class Especie(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre_comun = db.Column(db.String(100), nullable=False)
    nombre_cientifico = db.Column(db.String(100))
    dias_ciclo_estimado = db.Column(db.Integer)
    detalles_cuidado = db.Column(db.Text)
    imagen_url = db.Column(db.String(255))
    lotes = db.relationship('LoteProduccion', backref='especie', lazy=True)

    def __repr__(self):
        return f'<Especie {self.nombre_comun}>'

class LoteProduccion(db.Model):
    """
    Lo que Pepito SIEMBRA y CULTIVA.
    """
    id = db.Column(db.Integer, primary_key=True)
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
    
    estado = db.Column(db.String(30)) # En Crecimiento, Disponible, Finalizado
    
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
    
    consumos = db.relationship('ConsumoInsumo', backref='labor', lazy=True)

class ConsumoInsumo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    labor_id = db.Column(db.Integer, db.ForeignKey('labor_campo.id'))
    insumo_id = db.Column(db.Integer, db.ForeignKey('insumo.id'))
    insumo = db.relationship('Insumo')
    
    cantidad = db.Column(db.Float)
    subtotal = db.Column(db.Float)

# ==================================================
# 6. MÓDULO DE VENTAS (POS)
# ==================================================

class Cliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    documento = db.Column(db.String(20))
    telefono = db.Column(db.String(20))
    email = db.Column(db.String(100))
    direccion = db.Column(db.String(200))
    ventas = db.relationship('Venta', backref='cliente', lazy=True)

class Venta(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero_factura = db.Column(db.String(50), unique=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'))
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    usuario = db.relationship('Usuario')
    
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    estado = db.Column(db.String(20))
    total = db.Column(db.Float, default=0.0)
    
    detalles = db.relationship('DetalleVenta', backref='venta', lazy=True)

class DetalleVenta(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    venta_id = db.Column(db.Integer, db.ForeignKey('venta.id'))
    
    # 1. Venta de Cosecha Propia (Lotes)
    lote_id = db.Column(db.Integer, db.ForeignKey('lote_produccion.id'), nullable=True)
    
    # 2. Venta de Mercancía/Insumos (Materas, Tierra, Herramientas)
    insumo_id = db.Column(db.Integer, db.ForeignKey('insumo.id'), nullable=True)
    insumo = db.relationship('Insumo')

    cantidad = db.Column(db.Float)
    precio_venta_unitario = db.Column(db.Float)
    costo_produccion_unitario = db.Column(db.Float)
    
    subtotal = db.Column(db.Float)
    ganancia = db.Column(db.Float)

# ==================================================
# 7. MÓDULO PECUARIO (ANIMALES) - NIVEL PRO
# ==================================================

class LoteAnimal(db.Model):
    """
    Representa un animal individual (Vaca #01) o un grupo (Galpón Pollos).
    """
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), unique=True) # Arete, Número, ID
    nombre = db.Column(db.String(100))             # "La Lola", "Lote Engorde Dic"
    
    tipo = db.Column(db.String(50))                # Individual / Grupal
    especie = db.Column(db.String(50))             # Bovino, Avícola, Porcino, Caprino
    raza = db.Column(db.String(50))                # Holstein, Angus, Criolla
    
    # --- MODIFICADO: CAMPOS NUEVOS AGREGADOS ---
    genero = db.Column(db.String(20))              # 'Macho' o 'Hembra'
    ubicacion = db.Column(db.String(100))          # 'Corral 1', 'Galpón 2', 'Marranera 1'
    # -------------------------------------------

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
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    lote_animal_id = db.Column(db.Integer, db.ForeignKey('lote_animal.id'))
    
    # Producto generado (Debe existir en Inventario como Mercancía)
    producto_id = db.Column(db.Integer, db.ForeignKey('insumo.id')) 
    producto = db.relationship('Insumo')
    
    cantidad = db.Column(db.Float)
    observaciones = db.Column(db.String(200))

class ConsumoAnimal(db.Model):
    """
    Lo que el animal gasta: Comida, Sal, Suplementos.
    """
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, default=datetime.utcnow)
    lote_animal_id = db.Column(db.Integer, db.ForeignKey('lote_animal.id'))
    
    # Insumo consumido (Debe existir en Inventario como Insumo)
    insumo_id = db.Column(db.Integer, db.ForeignKey('insumo.id'))
    insumo = db.relationship('Insumo')
    
    cantidad = db.Column(db.Float)
    costo_calculado = db.Column(db.Float) # Se calcula con FIFO al momento del registro

class EventoSanitario(db.Model):
    """
    DETALLE PROFESIONAL: Historial médico.
    Vacunas, Purgas, Partos, Enfermedades.
    """
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, default=datetime.utcnow)
    lote_animal_id = db.Column(db.Integer, db.ForeignKey('lote_animal.id'))
    
    tipo = db.Column(db.String(50)) # Vacunación, Enfermedad, Parto, Pesaje, Vet
    descripcion = db.Column(db.Text)
    costo_servicio = db.Column(db.Float, default=0.0) # Si pagaste al veterinario
    
    # Si la vacuna salió del inventario, también genera un ConsumoAnimal, 
    # pero aquí queda el registro clínico.