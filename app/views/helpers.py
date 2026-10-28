"""
Funciones auxiliares compartidas entre todos los módulos.
Incluye: guardado de imágenes, FIFO, costo promedio, filtrado multi-empresa.
"""
import os
import logging
from datetime import datetime, timezone
from werkzeug.utils import secure_filename
from flask import current_app, request, abort, flash, redirect, url_for, session
from flask_login import current_user
from functools import wraps
from ..extensions import db
from ..models import LoteInsumo, MovimientoInventario, Insumo, AuditoriaLog

logger = logging.getLogger(__name__)

def empresa_id_actual():
    """Retorna el empresa_id activo (empresa del usuario o la seleccionada por SuperAdmin en sesión)."""
    if current_user and current_user.is_authenticated:
        if getattr(current_user, 'es_superadmin', False):
            selected_empresa_id = session.get('superadmin_empresa_id')
            if selected_empresa_id:
                try:
                    return int(selected_empresa_id)
                except (ValueError, TypeError):
                    pass
        return current_user.empresa_id
    return None


def obtener_empresa_activa():
    """Retorna el modelo Empresa actualmente activo según la sesión del usuario o SuperAdmin."""
    from ..models import Empresa
    eid = empresa_id_actual()
    if eid:
        emp = db.session.get(Empresa, eid)
        if emp:
            return emp
    if current_user and current_user.is_authenticated and current_user.empresa:
        return current_user.empresa
    return Empresa.query.order_by(Empresa.id).first()


def filtrar_por_empresa(query_obj, modelo):
    """Filtra automáticamente por la empresa del usuario actual.
    El SuperAdmin ve TODOS los datos de todas las empresas o filtra por la seleccionada en sesión."""
    if not current_user.is_authenticated:
        return query_obj
    if current_user.es_superadmin:
        selected_empresa_id = session.get('superadmin_empresa_id')
        if selected_empresa_id and hasattr(modelo, 'empresa_id'):
            return query_obj.filter(modelo.empresa_id == int(selected_empresa_id))
        return query_obj  # SuperAdmin ve todo si no hay filtro
    if hasattr(modelo, 'empresa_id') and current_user.empresa_id:
        return query_obj.filter(modelo.empresa_id == current_user.empresa_id)
    return query_obj


def asignar_empresa(obj):
    """Asigna el empresa_id del usuario actual a un objeto nuevo. Si es SuperAdmin, usa la de sesión."""
    if hasattr(obj, 'empresa_id') and current_user.is_authenticated:
        if current_user.es_superadmin:
            selected_empresa_id = session.get('superadmin_empresa_id')
            if selected_empresa_id:
                obj.empresa_id = int(selected_empresa_id)
        else:
            obj.empresa_id = current_user.empresa_id


def registrar_auditoria(accion, modulo, detalle):
    """Registra una acción en la bitácora de auditoría."""
    try:
        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if ip and ',' in ip:
            ip = ip.split(',')[0].strip()
            
        uid = current_user.id if current_user and current_user.is_authenticated else None
        eid = current_user.empresa_id if current_user and current_user.is_authenticated else None
        log = AuditoriaLog(
            usuario_id=uid,
            empresa_id=eid,
            accion=accion,
            modulo=modulo,
            detalle=detalle,
            ip_origen=ip
        )
        db.session.add(log)
        # No hacemos commit aquí, asumimos que se llamará junto con otros cambios en la BD
    except Exception as e:
        logger.error(f"Error registrando auditoría: {e}")

def rol_requerido(nivel_minimo):
    """
    Decorador para restringir acceso por nivel de rol.
    Nivel 0: SuperAdmin, 1: Admin, 2: Gerente, 3: Operario, 4: Visor
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return current_app.login_manager.unauthorized()
            
            if not current_user.activo:
                flash('Su cuenta está desactivada.', 'danger')
                return redirect(url_for('auth.logout'))
                
            if not current_user.tiene_permiso(nivel_minimo):
                flash('No tienes permisos suficientes para acceder a esta área.', 'danger')
                return redirect(url_for('dashboard.dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def solo_admin(f):
    """Atajo para rutas solo de administrador."""
    return rol_requerido(1)(f)

def solo_superadmin(f):
    """Decorador para rutas exclusivas del proveedor del software (SuperAdmin)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return current_app.login_manager.unauthorized()
        if not current_user.es_superadmin:
            flash('Acceso exclusivo para el administrador del sistema.', 'danger')
            return redirect(url_for('dashboard.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def get_or_404_empresa(modelo, id):
    """
    Obtiene un objeto por id (abortando con 404 si no existe) 
    y verifica que pertenezca a la empresa del usuario (o si es superadmin).
    Si no pertenece, aborta con 403.
    """
    obj = modelo.query.get_or_404(id)
    if hasattr(obj, 'empresa_id') and current_user.is_authenticated and not getattr(current_user, 'es_superadmin', False):
        if obj.empresa_id != current_user.empresa_id:
            abort(403)
    return obj


import uuid

def validar_cabecera_imagen(stream):
    """Verifica si el stream contiene una firma binaria de imagen permitida."""
    try:
        pos = stream.tell()
        header = stream.read(16)
        stream.seek(pos)
        if not header:
            return False
        # PNG: \x89PNG\r\n\x1a\n
        if header.startswith(b'\x89PNG\r\n\x1a\n'):
            return True
        # JPEG: \xff\xd8\xff
        if header.startswith(b'\xff\xd8\xff'):
            return True
        # GIF: GIF87a o GIF89a
        if header.startswith(b'GIF87a') or header.startswith(b'GIF89a'):
            return True
        # WebP: RIFF....WEBP
        if len(header) >= 12 and header.startswith(b'RIFF') and header[8:12] == b'WEBP':
            return True
    except Exception as e:
        logger.error(f"Error validando firma de imagen: {e}")
    return False


def guardar_imagen(archivo, carpeta):
    """Guarda un archivo de imagen validando firma real y retorna su ruta relativa."""
    if not archivo or not getattr(archivo, 'filename', None):
        return None
    
    filename = secure_filename(archivo.filename)
    if not filename:
        return None
    
    # Validar extensión
    ext = os.path.splitext(filename)[1].lower()
    allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    if ext not in allowed_extensions:
        abort(400, "Extensión de archivo no permitida")

    # Validar mimetype
    mimetype = getattr(archivo, 'mimetype', '')
    allowed_mimetypes = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
    if mimetype not in allowed_mimetypes:
        abort(400, "Tipo MIME no permitido")

    # Validar firma binaria real de la imagen
    if hasattr(archivo, 'stream') and not validar_cabecera_imagen(archivo.stream):
        abort(400, "El archivo no contiene una estructura de imagen válida")

    nombre_unico = f"{uuid.uuid4().hex}_{filename}"
    
    path_folder = os.path.join(current_app.root_path, 'static', 'uploads', carpeta)
    os.makedirs(path_folder, exist_ok=True)
    
    archivo.save(os.path.join(path_folder, nombre_unico))
    return f"uploads/{carpeta}/{nombre_unico}"


def recalcular_costo_promedio(insumo):
    """Recalcula el costo promedio ponderado de un insumo desde sus lotes activos."""
    lotes_activos = LoteInsumo.query.filter(
        LoteInsumo.insumo_id == insumo.id, 
        LoteInsumo.cantidad_actual > 0
    ).all()
    
    cantidad_total = sum(l.cantidad_actual for l in lotes_activos)
    valor_total = sum(l.cantidad_actual * l.costo_unitario for l in lotes_activos)
    
    if cantidad_total > 0:
        insumo.costo_promedio = valor_total / cantidad_total
    
    db.session.add(insumo)


def consumir_stock_fifo(insumo, cantidad_necesaria):
    """
    Consume stock usando método FIFO (First In, First Out).
    Retorna (costo_total, costo_unitario_promedio_salida).
    Lanza Exception si no hay stock suficiente.
    """
    if insumo.cantidad_actual < cantidad_necesaria:
        raise Exception(f"Stock insuficiente de {insumo.nombre}. Disponible: {insumo.cantidad_actual}")

    lotes = LoteInsumo.query.filter(
        LoteInsumo.insumo_id == insumo.id, 
        LoteInsumo.cantidad_actual > 0
    ).order_by(LoteInsumo.fecha_compra.asc(), LoteInsumo.id.asc()).with_for_update().all()

    cantidad_pendiente = cantidad_necesaria
    costo_total_salida = 0.0

    for lote in lotes:
        if cantidad_pendiente <= 0:
            break
        
        tomar = min(lote.cantidad_actual, cantidad_pendiente)
        lote.cantidad_actual -= tomar
        costo_total_salida += (tomar * lote.costo_unitario)
        cantidad_pendiente -= tomar

    insumo.cantidad_actual -= cantidad_necesaria
    recalcular_costo_promedio(insumo)
    
    costo_unitario_salida = costo_total_salida / cantidad_necesaria if cantidad_necesaria > 0 else 0
    return costo_total_salida, costo_unitario_salida


def safe_float(value, default=0.0):
    """Convierte un valor a float de manera segura. Retorna default si es nulo o inválido."""
    if value is None or str(value).strip() == '':
        return default
    try:
        return float(value)
    except ValueError:
        return default


def safe_int(value, default=0):
    """Convierte un valor a int de manera segura. Retorna default si es nulo o inválido."""
    if value is None or str(value).strip() == '':
        return default
    try:
        return int(float(value)) # float cast first prevents ValueError on something like '1.0'
    except ValueError:
        return default
