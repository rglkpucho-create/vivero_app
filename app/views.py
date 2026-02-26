import os
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import or_, func
from .models import (
    Usuario, Rol, Proveedor, Insumo, UnidadMedida, 
    PedidoCompra, DetallePedidoCompra, LoteInsumo, MovimientoInventario,
    Especie, LoteProduccion, LaborCampo, ConsumoInsumo,
    Cliente, Venta, DetalleVenta, Sede,
    LoteAnimal, ProduccionAnimal, ConsumoAnimal, EventoSanitario
)
from .extensions import db
from datetime import datetime

main_bp = Blueprint('main', __name__)

# ==================================================
# CONFIGURACIÓN GLOBAL Y HELPERS
# ==================================================

# 1. Inyección de variables globales (para datetime en Jinja)
@main_bp.context_processor
def inject_globals():
    return dict(datetime=datetime)

# 2. Helper: Guardar Imágenes
def guardar_imagen(archivo, carpeta):
    if not archivo:
        return None
    
    filename = secure_filename(archivo.filename)
    # Nombre único: timestamp + nombre original para evitar duplicados
    nombre_unico = f"{int(datetime.now().timestamp())}_{filename}"
    
    # Ruta absoluta en el servidor
    path_folder = os.path.join(current_app.root_path, 'static', 'uploads', carpeta)
    os.makedirs(path_folder, exist_ok=True) # Crea la carpeta si no existe
    
    archivo.save(os.path.join(path_folder, nombre_unico))
    
    # Retorna la ruta relativa para guardar en BD
    return f"uploads/{carpeta}/{nombre_unico}"

# 3. Helper: Recalcular Costo Promedio
def recalcular_costo_promedio(insumo):
    lotes_activos = LoteInsumo.query.filter(
        LoteInsumo.insumo_id == insumo.id, 
        LoteInsumo.cantidad_actual > 0
    ).all()
    
    cantidad_total = sum(l.cantidad_actual for l in lotes_activos)
    valor_total = sum(l.cantidad_actual * l.costo_unitario for l in lotes_activos)
    
    if cantidad_total > 0:
        insumo.costo_promedio = valor_total / cantidad_total
    
    db.session.add(insumo)

# 4. Helper: Lógica FIFO (First In, First Out)
def consumir_stock_fifo(insumo, cantidad_necesaria):
    if insumo.cantidad_actual < cantidad_necesaria:
        raise Exception(f"Stock insuficiente de {insumo.nombre}. Disponible: {insumo.cantidad_actual}")

    lotes = LoteInsumo.query.filter(
        LoteInsumo.insumo_id == insumo.id, 
        LoteInsumo.cantidad_actual > 0
    ).order_by(LoteInsumo.fecha_compra.asc(), LoteInsumo.id.asc()).all()

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


# ==================================================
# 1. AUTENTICACIÓN Y DASHBOARD
# ==================================================

@main_bp.route('/')
def home():
    return render_template('index.html')

@main_bp.route('/registro', methods=['GET', 'POST'])
def registro():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
    
    # Crear roles básicos si no existen
    if not Rol.query.first():
        try:
            db.session.add_all([Rol(nombre='Admin'), Rol(nombre='User')])
            db.session.commit()
        except:
            db.session.rollback()
            
    if request.method == 'POST':
        try:
            u = Usuario(
                nombre_completo=request.form.get('nombre'),
                email=request.form.get('email'),
                rol_id=1
            )
            u.set_password(request.form.get('password'))
            db.session.add(u)
            db.session.commit()
            flash('Registrado correctamente.', 'success')
            return redirect(url_for('main.login'))
        except:
            db.session.rollback()
            flash('Error en el registro.', 'danger')
            
    return render_template('registro.html')

@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
        
    if request.method == 'POST':
        u = Usuario.query.filter_by(email=request.form.get('email')).first()
        if u and u.check_password(request.form.get('password')):
            login_user(u)
            return redirect(url_for('main.dashboard'))
        flash('Credenciales incorrectas.', 'danger')
        
    return render_template('login.html')

@main_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.home'))

@main_bp.route('/dashboard')
@login_required
def dashboard():
    today_date = datetime.utcnow().date()
    
    # 1. KPI: Total de plantas vivas
    total_plantas_crecimiento = db.session.query(
        func.sum(LoteProduccion.cantidad_actual)
    ).filter(LoteProduccion.estado == 'En Crecimiento').scalar() or 0

    lotes_activos_count = LoteProduccion.query.filter_by(estado='En Crecimiento').count()

    # 2. Semáforo de Progreso (Lotes Agrícolas)
    lotes_para_semaforo = LoteProduccion.query.filter_by(
        estado='En Crecimiento'
    ).join(Especie).order_by(LoteProduccion.fecha_siembra.asc()).limit(5).all()

    lotes_progreso_data = []
    for lote in lotes_para_semaforo:
        dias_estimados = lote.especie.dias_ciclo_estimado or 90
        dias_transcurridos = (today_date - lote.fecha_siembra).days
        progreso_pct = min(max((dias_transcurridos / dias_estimados) * 100, 0), 100)
        
        color = 'success'
        if progreso_pct >= 90: color = 'danger'
        elif progreso_pct >= 50: color = 'warning'

        lotes_progreso_data.append({
            'lote_obj': lote,
            'dias_transcurridos': dias_transcurridos,
            'progreso_pct': int(progreso_pct),
            'color_estado': color
        })
        
    # 3. Alertas de Insumos Bajos
    insumos_alerta = Insumo.query.filter(
        Insumo.cantidad_actual <= Insumo.stock_minimo, 
        Insumo.cantidad_actual > 0
    ).order_by(Insumo.cantidad_actual.asc()).limit(5).all()

    return render_template('dashboard.html',
                           total_plantas_crecimiento=int(total_plantas_crecimiento),
                           lotes_activos_count=lotes_activos_count,
                           lotes_progreso=lotes_progreso_data,
                           insumos_alerta=insumos_alerta,
                           total_insumos=Insumo.query.count(),
                           total_proveedores=Proveedor.query.count(),
                           pedidos_pendientes=PedidoCompra.query.filter_by(estado='Solicitado').count(),
                           ventas_mes=Venta.query.count(),
                           species=Especie.query.all(),
                           total_especies=Especie.query.count(),
                           proveedores=Proveedor.query.all(),
                           unidades=UnidadMedida.query.all())

# ==================================================
# 2. GESTIÓN DE TERCEROS Y SEDES
# ==================================================

@main_bp.route('/proveedores')
@login_required
def lista_proveedores():
    q = request.args.get('q', '').strip()
    ajax = request.args.get('ajax') == '1'
    
    query = Proveedor.query
    if q:
        query = query.filter(or_(Proveedor.razon_social.ilike(f'%{q}%'), Proveedor.nit_rut.ilike(f'%{q}%')))
    
    proveedores = query.order_by(Proveedor.razon_social).all()
    
    if ajax:
        return render_template('parciales/items_proveedores.html', proveedores=proveedores)
    return render_template('lista_proveedores.html', proveedores=proveedores, search_query=q)

@main_bp.route('/proveedor/nuevo', methods=['GET', 'POST'])
@main_bp.route('/proveedor/editar/<int:proveedor_id>', methods=['GET', 'POST'])
@login_required
def nuevo_proveedor(proveedor_id=None):
    proveedor = Proveedor.query.get_or_404(proveedor_id) if proveedor_id else None
    
    if request.method == 'POST':
        try:
            if proveedor:
                proveedor.razon_social = request.form.get('razon_social')
                proveedor.nit_rut = request.form.get('nit_rut')
                proveedor.contacto_nombre = request.form.get('contacto_nombre')
                proveedor.telefono = request.form.get('telefono')
                proveedor.email = request.form.get('email')
                proveedor.direccion = request.form.get('direccion')
            else:
                db.session.add(Proveedor(
                    razon_social=request.form.get('razon_social'), 
                    nit_rut=request.form.get('nit_rut'), 
                    contacto_nombre=request.form.get('contacto_nombre'), 
                    telefono=request.form.get('telefono'), 
                    email=request.form.get('email'), 
                    direccion=request.form.get('direccion')
                ))
            db.session.commit()
            return redirect(url_for('main.lista_proveedores'))
        except:
            db.session.rollback()
            
    return render_template('nuevo_proveedor.html', proveedor=proveedor)

@main_bp.route('/proveedor/eliminar/<int:proveedor_id>', methods=['POST'])
@login_required
def eliminar_proveedor(proveedor_id):
    try:
        db.session.delete(Proveedor.query.get_or_404(proveedor_id))
        db.session.commit()
    except:
        db.session.rollback()
    return redirect(url_for('main.lista_proveedores'))

@main_bp.route('/configuracion/sedes')
@login_required
def lista_sedes():
    return render_template('lista_sedes.html', sedes=Sede.query.order_by(Sede.nombre).all())

@main_bp.route('/configuracion/sede/nueva', methods=['GET', 'POST'])
@login_required
def nueva_sede(sede_id=None):
    if request.method == 'POST':
        try:
            db.session.add(Sede(
                nombre=request.form.get('nombre'), 
                tipo=request.form.get('tipo'), 
                ubicacion_geo=request.form.get('ubicacion_geo')
            ))
            db.session.commit()
            return redirect(url_for('main.lista_sedes'))
        except:
            db.session.rollback()
    return render_template('nueva_sede.html', sede=None)

@main_bp.route('/configuracion/sede/editar/<int:sede_id>', methods=['GET', 'POST'])
@login_required
def editar_sede(sede_id):
    sede = Sede.query.get_or_404(sede_id)
    if request.method == 'POST':
        try:
            sede.nombre = request.form.get('nombre')
            sede.tipo = request.form.get('tipo')
            sede.ubicacion_geo = request.form.get('ubicacion_geo')
            db.session.commit()
            return redirect(url_for('main.lista_sedes'))
        except:
            db.session.rollback()
    return render_template('nueva_sede.html', sede=sede)

@main_bp.route('/configuracion/sede/eliminar/<int:sede_id>', methods=['POST'])
@login_required
def eliminar_sede(sede_id):
    try:
        db.session.delete(Sede.query.get_or_404(sede_id))
        db.session.commit()
    except:
        pass
    return redirect(url_for('main.lista_sedes'))

# ==================================================
# 3. GESTIÓN DE INVENTARIOS
# ==================================================

@main_bp.route('/insumos')
@login_required
def lista_insumos():
    q = request.args.get('q', '').strip()
    filtro = request.args.get('filtro', 'todos')
    ajax = request.args.get('ajax') == '1'
    
    query = Insumo.query
    if q:
        query = query.filter(or_(Insumo.nombre.ilike(f'%{q}%'), Insumo.codigo.ilike(f'%{q}%')))
    
    if filtro == 'bajo':
        query = query.filter(Insumo.cantidad_actual <= Insumo.stock_minimo, Insumo.cantidad_actual > 0)
    elif filtro == 'sin_stock':
        query = query.filter(Insumo.cantidad_actual <= 0)
    elif filtro == 'con_stock':
        query = query.filter(Insumo.cantidad_actual > 0)
    elif filtro == 'alerta_total':
        query = query.filter(Insumo.cantidad_actual <= Insumo.stock_minimo)

    insumos = query.all()
    if ajax:
        return render_template('parciales/items_insumos.html', insumos=insumos)
    return render_template('lista_insumos.html', insumos=insumos)

@main_bp.route('/insumo/nuevo', methods=['GET', 'POST'])
@main_bp.route('/insumo/editar/<int:insumo_id>', methods=['GET', 'POST'])
@login_required
def nuevo_insumo(insumo_id=None):
    # Asegurar que existan unidades
    if not UnidadMedida.query.first():
        try:
            db.session.add(UnidadMedida(nombre='Unidad', abreviatura='Und'))
            db.session.commit()
        except: pass
        
    insumo = Insumo.query.get_or_404(insumo_id) if insumo_id else None
    unidades = UnidadMedida.query.all()
    
    if request.method == 'POST':
        try:
            if insumo: 
                # EDICIÓN
                insumo.nombre = request.form.get('nombre')
                insumo.codigo = request.form.get('codigo')
                insumo.tipo = request.form.get('tipo')
                insumo.unidad_medida_id = int(request.form.get('unidad_id'))
                insumo.stock_minimo = float(request.form.get('stock_minimo', 0))
                
                if 'imagen' in request.files and request.files['imagen'].filename != '':
                    insumo.imagen_url = guardar_imagen(request.files['imagen'], 'insumos')
                
                # Ajuste de stock directo en edición (Opcional)
                try:
                    nuevo_stock = float(request.form.get('stock_inicial', insumo.cantidad_actual))
                    diff = nuevo_stock - insumo.cantidad_actual
                    if abs(diff) > 0.001:
                        if diff > 0:
                            db.session.add(LoteInsumo(insumo_id=insumo.id, fecha_compra=datetime.utcnow().date(), cantidad_inicial=diff, cantidad_actual=diff, costo_unitario=insumo.costo_promedio))
                        else:
                            consumir_stock_fifo(insumo, abs(diff))
                        
                        if diff > 0:
                            insumo.cantidad_actual = nuevo_stock
                            recalcular_costo_promedio(insumo)
                            
                        db.session.add(MovimientoInventario(tipo_movimiento='Ajuste Edición', cantidad=abs(diff), costo_unitario=insumo.costo_promedio, referencia=request.form.get('motivo_ajuste', 'Ajuste'), insumo_id=insumo.id))
                except: pass
            else:
                # CREACIÓN
                stock = float(request.form.get('stock_inicial', 0))
                costo = float(request.form.get('costo_inicial', 0))
                img = None
                if 'imagen' in request.files and request.files['imagen'].filename != '':
                    img = guardar_imagen(request.files['imagen'], 'insumos')
                
                nuevo = Insumo(
                    nombre=request.form.get('nombre'), 
                    codigo=request.form.get('codigo'), 
                    tipo=request.form.get('tipo'), 
                    unidad_medida_id=int(request.form.get('unidad_id')), 
                    stock_minimo=float(request.form.get('stock_minimo', 0)), 
                    cantidad_actual=stock, 
                    costo_promedio=costo, 
                    imagen_url=img
                )
                db.session.add(nuevo)
                db.session.flush() # Para obtener ID
                
                if stock > 0:
                    db.session.add(LoteInsumo(insumo_id=nuevo.id, fecha_compra=datetime.utcnow().date(), cantidad_inicial=stock, cantidad_actual=stock, costo_unitario=costo))
                    db.session.add(MovimientoInventario(tipo_movimiento='Inventario Inicial', cantidad=stock, costo_unitario=costo, referencia='Carga inicial', insumo_id=nuevo.id))
            
            db.session.commit()
            return redirect(url_for('main.lista_insumos'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {e}', 'danger')
            return render_template('nuevo_insumo.html', unidades=unidades, insumo=insumo)
            
    return render_template('nuevo_insumo.html', unidades=unidades, insumo=insumo)

@main_bp.route('/insumo/eliminar/<int:insumo_id>', methods=['POST'])
@login_required
def eliminar_insumo(insumo_id):
    try:
        db.session.delete(Insumo.query.get_or_404(insumo_id))
        db.session.commit()
        flash('Eliminado.', 'success')
    except:
        db.session.rollback()
    return redirect(url_for('main.lista_insumos'))

@main_bp.route('/insumo/ajustar/<int:insumo_id>', methods=['POST'])
@login_required
def ajustar_stock_insumo(insumo_id):
    insumo = Insumo.query.get_or_404(insumo_id)
    try:
        nueva = float(request.form.get('nueva_cantidad'))
        diff = nueva - insumo.cantidad_actual
        
        if nueva < 0 or diff == 0:
            return redirect(url_for('main.lista_insumos'))
            
        if diff > 0:
            db.session.add(LoteInsumo(insumo_id=insumo.id, fecha_compra=datetime.utcnow().date(), cantidad_inicial=diff, cantidad_actual=diff, costo_unitario=insumo.costo_promedio))
        else:
            consumir_stock_fifo(insumo, abs(diff))
            
        if diff > 0:
            insumo.cantidad_actual = nueva
            recalcular_costo_promedio(insumo)
            
        db.session.add(MovimientoInventario(tipo_movimiento='Ajuste', cantidad=abs(diff), costo_unitario=insumo.costo_promedio, referencia=request.form.get('motivo'), insumo_id=insumo.id, fecha=datetime.utcnow()))
        db.session.commit()
        flash('Ajustado.', 'success')
    except:
        db.session.rollback()
    return redirect(url_for('main.lista_insumos'))

# --- API: CREACIÓN RÁPIDA (CON COSTO) ---
@main_bp.route('/api/insumo/crear_rapido', methods=['POST'])
@login_required
def crear_insumo_rapido_api():
    try:
        data = request.json
        if data.get('codigo'):
            existe = Insumo.query.filter_by(codigo=data.get('codigo')).first()
            if existe: return jsonify({'success': False, 'error': 'El código ya existe'})

        costo_inicial = float(data.get('costo') or 0)

        nuevo = Insumo(
            nombre=data.get('nombre'),
            codigo=data.get('codigo'),
            tipo=data.get('tipo', 'Insumo'),
            unidad_medida_id=int(data.get('unidad_id')),
            stock_minimo=0,
            cantidad_actual=0,
            costo_promedio=costo_inicial
        )
        db.session.add(nuevo)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'item': {
                'id': nuevo.id,
                'nombre': nuevo.nombre,
                'codigo': nuevo.codigo,
                'unidad': nuevo.unidad.abreviatura,
                'costo': costo_inicial
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@main_bp.route('/api/insumos/buscar', methods=['GET'])
@login_required
def buscar_insumos_api():
    q = request.args.get('q', '').strip()
    if not q: return jsonify([])
    
    insumos = Insumo.query.filter(or_(Insumo.nombre.ilike(f'%{q}%'), Insumo.codigo.ilike(f'%{q}%'))).limit(10).all()
    
    res = [{
        'id': i.id, 
        'nombre': i.nombre, 
        'codigo': i.codigo, 
        'unidad': i.unidad.abreviatura if i.unidad else '', 
        'costo': i.costo_promedio
    } for i in insumos]
    return jsonify(res)

# ==================================================
# 4. GESTIÓN DE COMPRAS
# ==================================================

@main_bp.route('/compras')
@login_required
def lista_pedidos():
    query = PedidoCompra.query
    return render_template('lista_pedidos.html', pedidos=query.order_by(PedidoCompra.fecha_solicitud.desc()).all(), proveedores=Proveedor.query.all())

@main_bp.route('/compra/nueva', methods=['GET', 'POST'])
@login_required
def nuevo_pedido():
    borradores = PedidoCompra.query.filter_by(estado='Borrador').all()
    for b in borradores:
        if not b.detalles: return redirect(url_for('main.ver_pedido', pedido_id=b.id))
        
    try:
        prov = Proveedor.query.first()
        sede = Sede.query.first()
        
        # Crear datos por defecto si no existen
        if not prov: 
            prov = Proveedor(razon_social="Prov Gen", nit_rut="000")
            db.session.add(prov)
            db.session.commit()
            
        nuevo = PedidoCompra(
            numero_orden=f"OC-{int(datetime.now().timestamp())}", 
            proveedor_id=prov.id, 
            sede_id=sede.id if sede else None, 
            fecha_solicitud=datetime.utcnow().date(), 
            estado='Borrador'
        )
        db.session.add(nuevo)
        db.session.commit()
        return redirect(url_for('main.ver_pedido', pedido_id=nuevo.id))
    except:
        return redirect(url_for('main.lista_pedidos'))

@main_bp.route('/compra/<int:pedido_id>', methods=['GET'])
@login_required
def ver_pedido(pedido_id):
    pedido = PedidoCompra.query.get_or_404(pedido_id)
    return render_template('ver_pedido.html', 
                           pedido=pedido, 
                           insumos=Insumo.query.all(), 
                           proveedores=Proveedor.query.all(), 
                           sedes=Sede.query.all(),
                           unidades=UnidadMedida.query.all())

@main_bp.route('/compra/<int:pedido_id>/actualizar_datos', methods=['POST'])
@login_required
def actualizar_datos_pedido(pedido_id):
    p = PedidoCompra.query.get_or_404(pedido_id)
    
    if p.estado not in ['Borrador', 'Solicitado']: 
        flash('No se pueden editar datos de un pedido finalizado.', 'warning')
        return redirect(url_for('main.ver_pedido', pedido_id=p.id))
    
    try:
        if request.form.get('proveedor_id'): p.proveedor_id = int(request.form.get('proveedor_id'))
        if request.form.get('sede_id'): p.sede_id = int(request.form.get('sede_id'))
        if request.form.get('fecha_solicitud'): p.fecha_solicitud = datetime.strptime(request.form.get('fecha_solicitud'), '%Y-%m-%d').date()
        
        fecha_entrega = request.form.get('fecha_entrega_estimada')
        if fecha_entrega:
            p.fecha_entrega_estimada = datetime.strptime(fecha_entrega, '%Y-%m-%d').date()
        else:
            p.fecha_entrega_estimada = None
        
        db.session.commit()
        flash('Datos actualizados.', 'success')
        
    except Exception as e: 
        db.session.rollback()
        flash('Error al actualizar.', 'danger')
        
    return redirect(url_for('main.ver_pedido', pedido_id=p.id))

@main_bp.route('/compra/<int:pedido_id>/agregar_item', methods=['POST'])
@login_required
def agregar_item_pedido(pedido_id):
    p = PedidoCompra.query.get_or_404(pedido_id)
    if p.estado != 'Borrador': return redirect(url_for('main.ver_pedido', pedido_id=p.id))
    
    try:
        insumo_id = request.form.get('insumo_id')
        codigo = request.form.get('codigo_barras')
        insumo = None
        
        if insumo_id:
            insumo = Insumo.query.get(int(insumo_id))
        elif codigo:
            insumo = Insumo.query.filter(or_(Insumo.codigo == codigo, Insumo.nombre.ilike(codigo))).first()
            
        if not insumo:
            flash('No encontrado.', 'warning')
            return redirect(url_for('main.ver_pedido', pedido_id=p.id))

        cant = float(request.form.get('cantidad', 1))
        if request.form.get('es_caja') == 'on':
            cant *= float(request.form.get('unidades_por_caja') or 1)
            
        prec = float(request.form.get('precio_unitario') or insumo.costo_promedio or 0)

        existe = DetallePedidoCompra.query.filter_by(pedido_id=p.id, insumo_id=insumo.id).first()
        if existe:
            p.total_estimado -= (existe.cantidad_solicitada * existe.precio_unitario)
            existe.cantidad_solicitada += cant
            existe.precio_unitario = prec
            p.total_estimado += (existe.cantidad_solicitada * existe.precio_unitario)
        else:
            db.session.add(DetallePedidoCompra(pedido_id=p.id, insumo_id=insumo.id, cantidad_solicitada=cant, precio_unitario=prec))
            p.total_estimado += (cant * prec)
            
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {e}', 'danger')
        
    return redirect(url_for('main.ver_pedido', pedido_id=p.id))

@main_bp.route('/compra/item/actualizar/<int:detalle_id>', methods=['POST'])
@login_required
def actualizar_item_pedido(detalle_id):
    det = DetallePedidoCompra.query.get_or_404(detalle_id)
    if det.pedido.estado != 'Borrador': return redirect(url_for('main.ver_pedido', pedido_id=det.pedido_id))
    
    try:
        cant = float(request.form.get('cantidad'))
        prec = float(request.form.get('precio_unitario'))
        
        det.pedido.total_estimado = det.pedido.total_estimado - (det.cantidad_solicitada * det.precio_unitario) + (cant * prec)
        det.cantidad_solicitada = cant
        det.precio_unitario = prec
        
        db.session.commit()
        flash('Actualizado.', 'success')
    except:
        db.session.rollback()
        
    return redirect(url_for('main.ver_pedido', pedido_id=det.pedido_id))

@main_bp.route('/compra/item/eliminar/<int:detalle_id>', methods=['POST'])
@login_required
def eliminar_item_pedido(detalle_id):
    det = DetallePedidoCompra.query.get_or_404(detalle_id)
    pid = det.pedido_id
    if det.pedido.estado != 'Borrador': return redirect(url_for('main.ver_pedido', pedido_id=pid))
    
    try:
        det.pedido.total_estimado -= (det.cantidad_solicitada * det.precio_unitario)
        db.session.delete(det)
        db.session.commit()
        flash('Eliminado.', 'info')
    except:
        db.session.rollback()
        
    return redirect(url_for('main.ver_pedido', pedido_id=pid))

@main_bp.route('/compra/<int:pedido_id>/confirmar', methods=['POST'])
@login_required
def confirmar_pedido(pedido_id):
    pedido = PedidoCompra.query.get_or_404(pedido_id)
    if not pedido.detalles: return redirect(url_for('main.ver_pedido', pedido_id=pedido.id))
    
    try:
        pedido.estado = 'Solicitado'
        db.session.commit()
        flash('Confirmado.', 'success')
    except:
        db.session.rollback()
        
    return redirect(url_for('main.ver_pedido', pedido_id=pedido.id))

@main_bp.route('/compra/<int:pedido_id>/cancelar', methods=['POST'])
@login_required
def cancelar_pedido(pedido_id):
    try:
        p = PedidoCompra.query.get_or_404(pedido_id)
        p.estado = 'Cancelado'
        db.session.commit()
    except:
        db.session.rollback()
    return redirect(url_for('main.lista_pedidos'))

@main_bp.route('/compra/<int:pedido_id>/procesar_recepcion', methods=['POST'])
@login_required
def procesar_recepcion(pedido_id):
    pedido = PedidoCompra.query.get_or_404(pedido_id)
    if pedido.estado != 'Solicitado': return redirect(url_for('main.ver_pedido', pedido_id=pedido.id))
    
    try:
        pedido.estado = 'Recibido'
        pedido.fecha_recepcion = datetime.utcnow().date()
        
        for d in pedido.detalles:
            cant = float(request.form.get(f"recibido_{d.id}", 0))
            d.cantidad_recibida = cant
            
            if cant > 0:
                d.insumo.cantidad_actual += cant
                lote = LoteInsumo(
                    insumo_id=d.insumo_id, 
                    pedido_id=pedido.id, 
                    fecha_compra=pedido.fecha_recepcion, 
                    cantidad_inicial=cant, 
                    cantidad_actual=cant, 
                    costo_unitario=d.precio_unitario
                )
                kardex = MovimientoInventario(
                    tipo_movimiento='Compra', 
                    cantidad=cant, 
                    costo_unitario=d.precio_unitario, 
                    referencia=f"Pedido #{pedido.numero_orden}", 
                    insumo_id=d.insumo_id
                )
                db.session.add(lote)
                db.session.add(kardex)
                recalcular_costo_promedio(d.insumo)
                
        db.session.commit()
        flash('Recepción exitosa.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {e}', 'danger')
        
    return redirect(url_for('main.ver_pedido', pedido_id=pedido.id))

# ==================================================
# 5. MÓDULO DE PRODUCCIÓN (CULTIVOS)
# ==================================================

@main_bp.route('/produccion/lote/cambiar_estado/<int:lote_id>', methods=['POST'])
@login_required
def cambiar_estado_lote(lote_id):
    lote = LoteProduccion.query.get_or_404(lote_id)
    nuevo_estado = request.form.get('nuevo_estado')
    
    try:
        if nuevo_estado in ['En Crecimiento', 'Disponible', 'Finalizado']:
            lote.estado = nuevo_estado
            db.session.commit()
            
            if nuevo_estado == 'Disponible':
                flash(f'¡Lote {lote.codigo_lote} habilitado para venta!', 'success')
            elif nuevo_estado == 'Finalizado':
                flash('Lote cerrado y archivado.', 'secondary')
            else:
                flash('Estado actualizado.', 'info')
        else:
            flash('Estado no válido.', 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
        
    return redirect(url_for('main.ver_lote', lote_id=lote.id))

@main_bp.route('/produccion/lote/cosechar', methods=['POST'])
@login_required
def registrar_cosecha():
    lote_id = request.form.get('lote_id')
    producto_id = request.form.get('producto_id')
    
    try:
        cantidad = float(request.form.get('cantidad'))
        fecha = request.form.get('fecha')
        notas = request.form.get('notas')
        
        lote = LoteProduccion.query.get_or_404(lote_id)
        producto = Insumo.query.get_or_404(producto_id)
        
        producto.cantidad_actual += cantidad
        
        db.session.add(MovimientoInventario(
            tipo_movimiento='Producción Interna', 
            cantidad=cantidad, 
            costo_unitario=0, 
            referencia=f"Cosecha Lote {lote.codigo_lote}", 
            insumo_id=producto.id, 
            fecha=datetime.strptime(fecha, '%Y-%m-%d')
        ))
        
        db.session.add(LaborCampo(
            lote_id=lote.id, 
            usuario_id=current_user.id, 
            fecha=datetime.strptime(fecha, '%Y-%m-%d'), 
            tipo_labor='Cosecha', 
            descripcion=f"Recolección de {cantidad} {producto.unidad.abreviatura} de {producto.nombre}. {notas}"
        ))
        
        db.session.add(LoteInsumo(
            insumo_id=producto.id, 
            fecha_compra=datetime.strptime(fecha, '%Y-%m-%d'), 
            cantidad_inicial=cantidad, 
            cantidad_actual=cantidad, 
            costo_unitario=0
        ))
        
        db.session.commit()
        flash(f'¡Cosecha registrada!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
        
    return redirect(url_for('main.ver_lote', lote_id=lote_id))

@main_bp.route('/produccion/lotes')
@login_required
def lista_lotes():
    query_str = request.args.get('q', '').strip()
    sede_id = request.args.get('sede_id')
    proposito = request.args.get('proposito')
    
    # --- DETECTAR SI ES UNA PETICIÓN AJAX (JAVASCRIPT) ---
    ajax = request.args.get('ajax') == '1'
    # -----------------------------------------------------

    sedes = Sede.query.order_by(Sede.nombre).all()
    query = LoteProduccion.query.join(Especie).outerjoin(Sede)
    
    if query_str:
        query = query.filter(or_(
            LoteProduccion.codigo_lote.ilike(f'%{query_str}%'), 
            Especie.nombre_comun.ilike(f'%{query_str}%'), 
            LoteProduccion.ubicacion.ilike(f'%{query_str}%')
        ))
        
    if sede_id and sede_id.isdigit():
        query = query.filter(LoteProduccion.sede_id == int(sede_id))
        
    if proposito and proposito in ['Venta Plantula', 'Produccion Fruto']:
        query = query.filter(LoteProduccion.proposito == proposito)
    
    lotes = query.order_by(LoteProduccion.fecha_siembra.desc()).all()

    # --- CAMBIO IMPORTANTE AQUÍ ---
    if ajax:
        # Si es AJAX, devolvemos SOLO el pedacito de HTML de las tarjetas
        return render_template('parciales/items_lotes.html', lotes=lotes, today=datetime.utcnow().date())
    
    # Si es carga normal, devolvemos la página completa con menú
    return render_template('produccion/lista_lotes.html', 
                           lotes=lotes, 
                           sedes=sedes, 
                           today=datetime.utcnow().date())

@main_bp.route('/siembra/nueva', methods=['GET', 'POST'])
@login_required
def nuevo_lote():
    if request.method == 'POST':
        try:
            nuevo = LoteProduccion(
                codigo_lote=f"SMB-{int(datetime.now().timestamp())}",
                especie_id=int(request.form.get('especie_id')),
                sede_id=int(request.form.get('sede_id')),
                cantidad_sembrada=int(request.form.get('cantidad')),
                cantidad_actual=int(request.form.get('cantidad')),
                fecha_siembra=datetime.strptime(request.form.get('fecha_siembra'), '%Y-%m-%d').date(),
                ubicacion=request.form.get('ubicacion'),
                proposito=request.form.get('proposito'),
                estado='En Crecimiento'
            )
            db.session.add(nuevo)
            db.session.commit()
            return redirect(url_for('main.lista_lotes'))
        except:
            db.session.rollback()
            
    return render_template('produccion/nuevo_lote.html', 
                           sedes=Sede.query.all(), 
                           especies=Especie.query.all(), 
                           today_str=datetime.utcnow().strftime('%Y-%m-%d'))

@main_bp.route('/produccion/lote/<int:lote_id>')
@login_required
def ver_lote(lote_id):
    return render_template('produccion/ver_lote.html', 
                           lote=LoteProduccion.query.get_or_404(lote_id), 
                           insumos=Insumo.query.order_by(Insumo.nombre).all(), 
                           datetime=datetime)

@main_bp.route('/produccion/lote/eliminar/<int:lote_id>', methods=['POST'])
@login_required
def eliminar_lote(lote_id):
    try: 
        lote = LoteProduccion.query.get_or_404(lote_id)
        for l in LaborCampo.query.filter_by(lote_id=lote.id).all():
            for c in l.consumos:
                db.session.delete(c)
            db.session.delete(l)
        db.session.delete(lote)
        db.session.commit()
        flash('Eliminado.', 'success')
    except:
        db.session.rollback()
        
    return redirect(url_for('main.lista_lotes'))

@main_bp.route('/produccion/lote/ajustar/<int:lote_id>', methods=['POST'])
@login_required
def ajustar_stock_lote(lote_id):
    try: 
        lote = LoteProduccion.query.get_or_404(lote_id)
        lote.cantidad_actual = int(request.form.get('nueva_cantidad'))
        if lote.cantidad_actual == 0:
            lote.estado = 'Finalizado'
        db.session.commit()
    except:
        db.session.rollback()
        
    return redirect(url_for('main.ver_lote', lote_id=lote_id))

@main_bp.route('/produccion/labor/guardar', methods=['POST'])
@login_required
def registrar_labor():
    try:
        lote = LoteProduccion.query.get_or_404(request.form.get('lote_id'))
        
        labor = LaborCampo(
            lote_id=lote.id,
            tipo_labor=request.form.get('tipo_labor'),
            descripcion=request.form.get('descripcion'),
            usuario_id=current_user.id,
            fecha=datetime.utcnow().date()
        )
        db.session.add(labor)
        db.session.flush()
        
        if request.form.get('insumo_id') and float(request.form.get('cantidad_insumo') or 0) > 0:
            insumo = Insumo.query.get(request.form.get('insumo_id'))
            costo, _ = consumir_stock_fifo(insumo, float(request.form.get('cantidad_insumo')))
            
            db.session.add(ConsumoInsumo(
                labor_id=labor.id,
                insumo_id=insumo.id,
                cantidad=float(request.form.get('cantidad_insumo')),
                subtotal=costo
            ))
            lote.costo_total += costo
            
        db.session.commit()
        flash('Labor registrada.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {e}', 'danger')
        
    return redirect(url_for('main.ver_lote', lote_id=request.form.get('lote_id')))

@main_bp.route('/produccion/labor/editar/<int:labor_id>', methods=['POST'])
@login_required
def editar_labor(labor_id):
    labor = LaborCampo.query.get_or_404(labor_id)
    try:
        labor.tipo_labor = request.form.get('tipo_labor')
        labor.descripcion = request.form.get('descripcion')
        db.session.commit()
        flash('Actualizado.', 'success')
    except:
        db.session.rollback()
        
    return redirect(url_for('main.ver_lote', lote_id=labor.lote_id))

@main_bp.route('/produccion/labor/eliminar/<int:labor_id>', methods=['POST'])
@login_required
def eliminar_labor(labor_id):
    labor = LaborCampo.query.get_or_404(labor_id)
    lid = labor.lote_id
    try:
        for c in labor.consumos:
            c.insumo.cantidad_actual += c.cantidad
            labor.lote.costo_total -= c.subtotal
            db.session.delete(c)
        db.session.delete(labor)
        db.session.commit()
        flash('Eliminado.', 'success')
    except:
        db.session.rollback()
        
    return redirect(url_for('main.ver_lote', lote_id=lid))

@main_bp.route('/produccion/especies')
@login_required
def lista_especies():
    return render_template('produccion/lista_especies.html', especies=Especie.query.all())

@main_bp.route('/produccion/especie/nueva', methods=['GET', 'POST'])
@login_required
def nueva_especie():
    if request.method == 'POST':
        try:
            imagen_path = None
            if 'imagen' in request.files:
                file = request.files['imagen']
                if file and file.filename != '':
                    imagen_path = guardar_imagen(file, 'especies')
                    
            db.session.add(Especie(
                nombre_comun=request.form.get('nombre_comun'),
                nombre_cientifico=request.form.get('nombre_cientifico'),
                dias_ciclo_estimado=int(request.form.get('dias_ciclo') or 0),
                detalles_cuidado=request.form.get('detalles_cuidado'),
                imagen_url=imagen_path
            ))
            db.session.commit()
            return redirect(url_for('main.lista_especies'))
        except:
            db.session.rollback()
            
    return render_template('produccion/nueva_especie.html')

@main_bp.route('/produccion/especie/editar_ficha/<int:especie_id>', methods=['POST'])
@login_required
def editar_ficha_especie(especie_id):
    e = Especie.query.get_or_404(especie_id)
    lote_id = request.args.get('lote_id')
    try: 
        e.dias_ciclo_estimado = int(request.form.get('dias_ciclo'))
        e.detalles_cuidado = request.form.get('detalles_cuidado')
        
        if 'imagen_editar' in request.files:
            file = request.files['imagen_editar']
            if file and file.filename != '':
                e.imagen_url = guardar_imagen(file, 'especies')
        db.session.commit()
    except:
        db.session.rollback()
        
    return redirect(url_for('main.ver_lote', lote_id=lote_id)) if lote_id else redirect(url_for('main.lista_especies'))

@main_bp.route('/produccion/especie/eliminar/<int:especie_id>', methods=['POST'])
@login_required
def eliminar_especie(especie_id):
    try:
        db.session.delete(Especie.query.get_or_404(especie_id))
        db.session.commit()
    except:
        db.session.rollback()
        
    return redirect(url_for('main.lista_especies'))

# ==================================================
# 6. MÓDULO DE VENTAS (POS)
# ==================================================

@main_bp.route('/clientes')
@login_required
def lista_clientes():
    q = request.args.get('q', '').strip()
    query = Cliente.query
    if q:
        query = query.filter(or_(Cliente.nombre.ilike(f'%{q}%'), Cliente.documento.ilike(f'%{q}%')))
    return render_template('ventas/lista_clientes.html', clientes=query.all(), search_query=q)

@main_bp.route('/cliente/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo_cliente():
    if request.method == 'POST':
        try:
            db.session.add(Cliente(
                nombre=request.form.get('nombre'),
                documento=request.form.get('documento'),
                telefono=request.form.get('telefono'),
                email=request.form.get('email'),
                direccion=request.form.get('direccion')
            ))
            db.session.commit()
            flash('Cliente creado.', 'success')
            return redirect(url_for('main.lista_clientes'))
        except:
            db.session.rollback()
            
    return render_template('ventas/nuevo_cliente.html')

@main_bp.route('/ventas')
@login_required
def lista_ventas():
    return render_template('ventas/lista_ventas.html', ventas=Venta.query.order_by(Venta.fecha.desc()).all())

@main_bp.route('/venta/nueva', methods=['GET', 'POST'])
@login_required
def nueva_venta():
    borradores = Venta.query.filter_by(estado='Borrador').all()
    for b in borradores:
        if not b.detalles: return redirect(url_for('main.ver_venta', venta_id=b.id))
        
    try:
        cli = Cliente.query.first()
        if not cli:
            cli = Cliente(nombre='Mostrador')
            db.session.add(cli)
            db.session.commit()
            
        v = Venta(
            numero_factura=f"FAC-{int(datetime.now().timestamp())}", 
            cliente_id=cli.id, 
            usuario_id=current_user.id, 
            estado='Borrador'
        )
        db.session.add(v)
        db.session.commit()
        return redirect(url_for('main.ver_venta', venta_id=v.id))
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {e}', 'danger')
        return redirect(url_for('main.lista_ventas'))

@main_bp.route('/venta/<int:venta_id>')
@login_required
def ver_venta(venta_id):
    venta = Venta.query.get_or_404(venta_id)
    clientes = Cliente.query.all()
    return render_template('ventas/ver_venta.html', venta=venta, clientes=clientes)

@main_bp.route('/venta/<int:venta_id>/cambiar_cliente', methods=['POST'])
@login_required
def cambiar_cliente_venta(venta_id):
    venta = Venta.query.get_or_404(venta_id)
    try:
        venta.cliente_id = int(request.form.get('cliente_id'))
        db.session.commit()
    except:
        db.session.rollback()
    return redirect(url_for('main.ver_venta', venta_id=venta_id))

@main_bp.route('/venta/<int:venta_id>/agregar', methods=['POST'])
@login_required
def agregar_item_venta(venta_id):
    venta = Venta.query.get_or_404(venta_id)
    try:
        lote_id = request.form.get('lote_id')
        insumo_id = request.form.get('insumo_id')
        
        lote_id = int(lote_id) if lote_id else None
        insumo_id = int(insumo_id) if insumo_id else None
        
        cantidad = float(request.form.get('cantidad', 1))
        precio_venta = float(request.form.get('precio_unitario', 0))
        
        if request.form.get('es_caja') == 'on':
            cantidad *= float(request.form.get('unidades_por_caja') or 1)
            
        existe = None
        if lote_id:
            existe = DetalleVenta.query.filter_by(venta_id=venta.id, lote_id=lote_id).first()
        elif insumo_id:
            existe = DetalleVenta.query.filter_by(venta_id=venta.id, insumo_id=insumo_id).first()
            
        costo_unit = 0
        if lote_id: 
            obj = LoteProduccion.query.get(lote_id)
            if obj.cantidad_actual < cantidad:
                flash('Stock insuficiente.', 'warning')
                return redirect(url_for('main.ver_venta', venta_id=venta_id))
            costo_unit = obj.costo_total / obj.cantidad_actual if obj.cantidad_actual else 0
        elif insumo_id:
            obj = Insumo.query.get(insumo_id)
            if obj.cantidad_actual < cantidad:
                flash(f'Stock insuficiente de {obj.nombre}.', 'warning')
                return redirect(url_for('main.ver_venta', venta_id=venta_id))
            costo_unit = obj.costo_promedio
            
        if existe:
            existe.cantidad += cantidad
            existe.precio_venta_unitario = precio_venta
            existe.subtotal = existe.cantidad * precio_venta
            existe.ganancia = existe.subtotal - (existe.cantidad * existe.costo_produccion_unitario)
            venta.total = sum(d.subtotal for d in venta.detalles)
        else:
            det = DetalleVenta(
                venta_id=venta.id,
                lote_id=lote_id,
                insumo_id=insumo_id,
                cantidad=cantidad,
                precio_venta_unitario=precio_venta,
                costo_produccion_unitario=costo_unit,
                subtotal=cantidad*precio_venta,
                ganancia=(cantidad*precio_venta)-(cantidad*costo_unit)
            )
            db.session.add(det)
            venta.total += cantidad*precio_venta
            
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(str(e), 'danger')
        
    return redirect(url_for('main.ver_venta', venta_id=venta.id))

@main_bp.route('/venta/<int:venta_id>/finalizar', methods=['POST'])
@login_required
def finalizar_venta(venta_id):
    venta = Venta.query.get_or_404(venta_id)
    try:
        for d in venta.detalles:
            if d.lote_id:
                lote = d.lote_origen
                if lote.cantidad_actual < d.cantidad:
                    raise Exception(f"Sin stock lote.")
                lote.cantidad_actual -= d.cantidad
                lote.costo_total -= (d.cantidad * d.costo_produccion_unitario)
                
                if lote.cantidad_actual <= 0:
                    lote.estado = 'Finalizado'
                    
            elif d.insumo_id:
                costo_tot, costo_unit = consumir_stock_fifo(d.insumo, d.cantidad)
                d.costo_produccion_unitario = costo_unit
                d.ganancia = d.subtotal - costo_tot
                
                db.session.add(MovimientoInventario(
                    tipo_movimiento='Venta', 
                    cantidad=d.cantidad, 
                    costo_unitario=costo_unit, 
                    referencia=f"Factura #{venta.numero_factura}", 
                    insumo_id=d.insumo_id
                ))
                
        venta.estado = 'Finalizada'
        db.session.commit()
        flash('Venta lista.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(str(e), 'danger')
        
    return redirect(url_for('main.ver_venta', venta_id=venta.id))

@main_bp.route('/venta/item/actualizar/<int:detalle_id>', methods=['POST'])
@login_required
def actualizar_item_venta(detalle_id):
    det = DetalleVenta.query.get_or_404(detalle_id)
    try:
        cant = float(request.form.get('cantidad'))
        stock_disp = det.insumo.cantidad_actual if det.insumo else det.lote_origen.cantidad_actual
        
        if cant > stock_disp:
            flash('Stock insuficiente.', 'warning')
            return redirect(url_for('main.ver_venta', venta_id=det.venta_id))
            
        det.venta.total -= det.subtotal
        det.cantidad = cant
        det.subtotal = det.cantidad * det.precio_venta_unitario
        det.ganancia = det.subtotal - (det.cantidad * det.costo_produccion_unitario)
        det.venta.total += det.subtotal
        
        db.session.commit()
        flash('Actualizado.', 'success')
    except:
        db.session.rollback()
        
    return redirect(url_for('main.ver_venta', venta_id=det.venta_id))

@main_bp.route('/venta/item/eliminar/<int:detalle_id>', methods=['POST'])
@login_required
def eliminar_item_venta(detalle_id):
    det = DetalleVenta.query.get_or_404(detalle_id)
    vid = det.venta_id
    try:
        det.venta.total -= det.subtotal
        db.session.delete(det)
        db.session.commit()
        flash('Eliminado.', 'info')
    except:
        db.session.rollback()
        
    return redirect(url_for('main.ver_venta', venta_id=vid))

@main_bp.route('/venta/<int:pedido_id>/cancelar', methods=['POST'])
@login_required
def cancelar_venta_ruta(pedido_id):
    try:
        venta = Venta.query.get_or_404(pedido_id)
        venta.estado = 'Anulada'
        db.session.commit()
        flash('Anulada.', 'secondary')
    except:
        db.session.rollback()
        
    return redirect(url_for('main.lista_ventas'))

@main_bp.route('/api/ventas/buscar', methods=['GET'])
@login_required
def buscar_items_venta_api():
    q = request.args.get('q', '').strip()
    res = []
    
    if not q: return jsonify([])
    
    # 1. Buscar Insumos (Mercancía)
    for i in Insumo.query.filter(or_(Insumo.nombre.ilike(f'%{q}%'), Insumo.codigo.ilike(f'%{q}%')), Insumo.cantidad_actual > 0).limit(5).all():
        res.append({
            'type': 'insumo', 
            'id': i.id, 
            'nombre': i.nombre, 
            'codigo': i.codigo, 
            'unidad': i.unidad.abreviatura if i.unidad else '', 
            'stock': i.cantidad_actual, 
            'costo': i.costo_promedio,
            'origen': 'Bodega'
        })
    
    # 2. Buscar Lotes (Plantas)
    lotes = LoteProduccion.query.join(Especie).filter(
        or_(Especie.nombre_comun.ilike(f'%{q}%'), LoteProduccion.codigo_lote.ilike(f'%{q}%')), 
        LoteProduccion.cantidad_actual > 0, 
        LoteProduccion.estado == 'Disponible', 
        LoteProduccion.proposito == 'Venta Plantula'
    ).limit(5).all()

    for l in lotes:
        res.append({
            'type': 'lote', 
            'id': l.id, 
            'nombre': f"{l.especie.nombre_comun} - {l.codigo_lote}", 
            'codigo': l.codigo_lote, 
            'unidad': 'Und', 
            'stock': l.cantidad_actual, 
            'costo': l.costo_total/l.cantidad_actual if l.cantidad_actual else 0, 
            'origen': 'Cultivo'
        })
        
    return jsonify(res)

@main_bp.route('/debug/escenario_completo')
@login_required
def escenario_completo():
    try:
        meta = db.metadata
        for table in reversed(meta.sorted_tables):
            db.session.execute(table.delete())
        db.session.flush()
        
        kg = UnidadMedida(nombre='Kilogramo', abreviatura='Kg')
        und = UnidadMedida(nombre='Unidad', abreviatura='Und')
        db.session.add_all([kg, und])
        
        sede = Sede(nombre='Vivero Central', tipo='Bodega')
        db.session.add(sede)
        
        prov = Proveedor(razon_social='Prov Gral', nit_rut='123')
        db.session.add(prov)
        
        cli = Cliente(nombre='Mostrador', documento='222')
        db.session.add(cli)
        db.session.flush()
        
        ins = Insumo(nombre='Triple 15', codigo='T15', tipo='Insumo', unidad_medida_id=kg.id, cantidad_actual=100, costo_promedio=4500)
        db.session.add(ins)
        db.session.flush()
        
        db.session.add(LoteInsumo(insumo_id=ins.id, fecha_compra=datetime(2023,1,1).date(), cantidad_inicial=50, cantidad_actual=50, costo_unitario=4000))
        db.session.add(LoteInsumo(insumo_id=ins.id, fecha_compra=datetime(2023,2,1).date(), cantidad_inicial=50, cantidad_actual=50, costo_unitario=5000))
        
        db.session.commit()
        flash('Escenario generado.', 'success')
        return redirect(url_for('main.dashboard'))
    except Exception as e:
        db.session.rollback()
        return str(e)

# ==================================================
# 7. MÓDULO PECUARIO (ANIMALES)
# ==================================================

@main_bp.route('/animales')
@login_required
def lista_animales():
    sedes = Sede.query.all()
    q = request.args.get('q', '').strip()
    
    query = LoteAnimal.query
    if q:
        query = query.filter(or_(LoteAnimal.nombre.ilike(f'%{q}%'), LoteAnimal.codigo.ilike(f'%{q}%')))
        
    return render_template('pecuario/lista_animales.html', animales=query.all(), sedes=sedes)

@main_bp.route('/animal/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo_animal():
    sedes = Sede.query.all()
    
    if request.method == 'POST':
        try:
            # 1. Procesar Imagen (Nombre 'foto' en HTML)
            ruta_imagen = None
            if 'foto' in request.files:
                file = request.files['foto']
                if file and file.filename != '':
                    ruta_imagen = guardar_imagen(file, 'animales')

            # 2. Fechas (Evitar error con cadena vacía)
            f_nac_str = request.form.get('fecha_nacimiento')
            f_nac = datetime.strptime(f_nac_str, '%Y-%m-%d').date() if f_nac_str else None
            
            f_ing_str = datetime.utcnow().date() # Por defecto hoy si no se envía

            # 3. Crear Objeto
            nuevo = LoteAnimal(
                codigo=request.form.get('codigo'),
                nombre=request.form.get('nombre'),
                tipo=request.form.get('tipo', 'Individual'), 
                especie=request.form.get('especie'),
                raza=request.form.get('raza'),
                
                # --- CAMPOS NUEVOS ---
                genero=request.form.get('genero'),        # 'Macho' o 'Hembra'
                ubicacion=request.form.get('ubicacion'),  # 'Corral 1', 'Galpón 2', etc.
                # ---------------------

                fecha_nacimiento=f_nac,
                fecha_ingreso=f_ing_str,
                
                cantidad_inicial=int(request.form.get('cantidad', 1)),
                cantidad_actual=int(request.form.get('cantidad', 1)),
                
                peso_actual=float(request.form.get('peso') or 0),
                sede_id=int(request.form.get('sede_id')),
                proposito=request.form.get('proposito'),
                estado='Activo',
                costo_acumulado=float(request.form.get('costo_inicial') or 0),
                imagen_url=ruta_imagen 
            )
            
            db.session.add(nuevo)
            db.session.commit()
            
            flash('Animal/Lote registrado con éxito.', 'success')
            return redirect(url_for('main.lista_animales'))
            
        except Exception as e:
            db.session.rollback()
            print(f"Error registrando animal: {e}") 
            flash(f'Error: {str(e)}', 'danger')
            
    return render_template('pecuario/nuevo_animal.html', sedes=sedes, today=datetime.utcnow().date())

@main_bp.route('/animal/<int:id>')
@login_required
def ver_animal(id):
    animal = LoteAnimal.query.get_or_404(id)
    productos_venta = Insumo.query.filter_by(tipo='Comercial').all()
    alimentos = Insumo.query.filter_by(tipo='Insumo').all()
    return render_template('pecuario/ver_animal.html', animal=animal, productos=productos_venta, alimentos=alimentos, today=datetime.utcnow().date())

@main_bp.route('/animal/producir', methods=['POST'])
@login_required
def registrar_produccion_animal():
    animal_id = request.form.get('animal_id')
    try:
        animal = LoteAnimal.query.get_or_404(animal_id)
        producto = Insumo.query.get_or_404(request.form.get('producto_id'))
        cantidad = float(request.form.get('cantidad'))
        
        prod = ProduccionAnimal(
            lote_animal_id=animal.id,
            producto_id=producto.id,
            cantidad=cantidad,
            observaciones=request.form.get('observaciones'),
            fecha=datetime.strptime(request.form.get('fecha'), '%Y-%m-%d')
        )
        db.session.add(prod)
        
        producto.cantidad_actual += cantidad
        
        kardex = MovimientoInventario(
            tipo_movimiento='Producción Pecuaria', 
            cantidad=cantidad, 
            costo_unitario=0, 
            referencia=f"Prod. {animal.nombre}", 
            insumo_id=producto.id
        )
        db.session.add(kardex)
        
        db.session.commit()
        flash('Producción registrada.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {e}', 'danger')
        
    return redirect(url_for('main.ver_animal', id=animal_id))

@main_bp.route('/animal/alimentar', methods=['POST'])
@login_required
def registrar_consumo_animal():
    animal_id = request.form.get('animal_id')
    try:
        animal = LoteAnimal.query.get_or_404(animal_id)
        insumo = Insumo.query.get_or_404(request.form.get('insumo_id'))
        cantidad = float(request.form.get('cantidad'))
        
        costo_total, _ = consumir_stock_fifo(insumo, cantidad)
        
        consumo = ConsumoAnimal(
            lote_animal_id=animal.id,
            insumo_id=insumo.id,
            cantidad=cantidad,
            costo_calculado=costo_total,
            fecha=datetime.strptime(request.form.get('fecha'), '%Y-%m-%d')
        )
        db.session.add(consumo)
        
        animal.costo_acumulado += costo_total
        
        kardex = MovimientoInventario(
            tipo_movimiento='Consumo Animal', 
            cantidad=cantidad, 
            costo_unitario=insumo.costo_promedio, 
            referencia=f"Alim. {animal.nombre}", 
            insumo_id=insumo.id
        )
        db.session.add(kardex)
        
        db.session.commit()
        flash('Alimentación registrada.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {e}', 'danger')
        
    return redirect(url_for('main.ver_animal', id=animal_id))

@main_bp.route('/animal/evento_salud', methods=['POST'])
@login_required
def registrar_evento_salud():
    animal_id = request.form.get('animal_id')
    try:
        animal = LoteAnimal.query.get_or_404(animal_id)
        
        evento = EventoSanitario(
            lote_animal_id=animal.id,
            fecha=datetime.strptime(request.form.get('fecha'), '%Y-%m-%d'),
            tipo=request.form.get('tipo'),
            descripcion=request.form.get('descripcion'),
            costo_servicio=float(request.form.get('costo') or 0)
        )
        
        if evento.costo_servicio > 0:
            animal.costo_acumulado += evento.costo_servicio
            
        db.session.add(evento)
        db.session.commit()
        flash('Evento registrado.', 'info')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {e}', 'danger')
        
    return redirect(url_for('main.ver_animal', id=animal_id))