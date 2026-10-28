"""
Módulo de Compras — Pedidos, recepción, ítems
"""
import logging
from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from sqlalchemy import or_
from ..models import (
    Insumo, PedidoCompra, DetallePedidoCompra, LoteInsumo, 
    MovimientoInventario, Proveedor, Sede, UnidadMedida
)
from ..extensions import db
from .helpers import recalcular_costo_promedio, safe_float, safe_int, solo_admin, registrar_auditoria, filtrar_por_empresa, asignar_empresa, get_or_404_empresa

logger = logging.getLogger(__name__)
compras_bp = Blueprint('compras', __name__)


@compras_bp.route('/compras')
@login_required
def lista_pedidos():
    proveedor_id = request.args.get('proveedor_id')
    estado = request.args.get('estado')
    fecha_inicio = request.args.get('fecha_inicio')
    fecha_fin = request.args.get('fecha_fin')
    filtro_dashboard = request.args.get('filtro')
    q = request.args.get('q', '').strip()

    base_pedidos = filtrar_por_empresa(PedidoCompra.query, PedidoCompra)
    
    # KPIs globales
    todos_pedidos = base_pedidos.all()
    kpi_inversion_total = sum(p.total_estimado or 0 for p in todos_pedidos if p.estado == 'Recibido')
    kpi_solicitados = sum(1 for p in todos_pedidos if p.estado == 'Solicitado')
    kpi_recibidos = sum(1 for p in todos_pedidos if p.estado == 'Recibido')
    kpi_borradores = sum(1 for p in todos_pedidos if p.estado == 'Borrador')
    
    query = base_pedidos
    if q:
        query = query.join(Proveedor).filter(or_(
            PedidoCompra.numero_orden.ilike(f'%{q}%'),
            Proveedor.razon_social.ilike(f'%{q}%')
        ))
    if filtro_dashboard == 'pendiente' or estado == 'Solicitado':
        query = query.filter(PedidoCompra.estado == 'Solicitado')
    elif estado:
        query = query.filter(PedidoCompra.estado == estado)
        
    if proveedor_id:
        query = query.filter(PedidoCompra.proveedor_id == int(proveedor_id))
        
    if fecha_inicio:
        query = query.filter(PedidoCompra.fecha_solicitud >= datetime.strptime(fecha_inicio, '%Y-%m-%d').date())
    if fecha_fin:
        query = query.filter(PedidoCompra.fecha_solicitud <= datetime.strptime(fecha_fin, '%Y-%m-%d').date())
        
    pedidos = query.order_by(PedidoCompra.fecha_solicitud.desc()).all()
    ajax = request.args.get('ajax') == '1'
    if ajax:
        return render_template('parciales/items_pedidos.html', pedidos=pedidos)
    return render_template('compras/lista_pedidos.html', 
                         pedidos=pedidos, 
                         proveedores=filtrar_por_empresa(Proveedor.query, Proveedor).all(),
                         kpi_inversion_total=kpi_inversion_total,
                         kpi_solicitados=kpi_solicitados,
                         kpi_recibidos=kpi_recibidos,
                         kpi_borradores=kpi_borradores,
                         search_query=q)


@compras_bp.route('/compra/nueva', methods=['GET', 'POST'])
@login_required
def nuevo_pedido():
    borradores = filtrar_por_empresa(PedidoCompra.query, PedidoCompra).filter_by(estado='Borrador').all()
    for b in borradores:
        if not b.detalles: return redirect(url_for('compras.ver_pedido', pedido_id=b.id))
        
    try:
        prov = filtrar_por_empresa(Proveedor.query, Proveedor).first()
        sede = filtrar_por_empresa(Sede.query, Sede).first()
        
        if not prov: 
            prov = Proveedor(razon_social="Prov Gen", nit_rut="000")
            asignar_empresa(prov)
            db.session.add(prov)
            db.session.commit()
            
        nuevo = PedidoCompra(
            numero_orden=f"OC-{int(datetime.now().timestamp())}", 
            proveedor_id=prov.id, 
            sede_id=sede.id if sede else None, 
            fecha_solicitud=datetime.now(timezone.utc).date(), 
            estado='Borrador'
        )
        asignar_empresa(nuevo)
        db.session.add(nuevo)
        db.session.commit()
        return redirect(url_for('compras.ver_pedido', pedido_id=nuevo.id))
    except Exception as e:
        logger.error(f'Error creando pedido: {e}')
        flash('Error al crear pedido.', 'danger')
        return redirect(url_for('compras.lista_pedidos'))


@compras_bp.route('/compra/<int:pedido_id>', methods=['GET'])
@login_required
def ver_pedido(pedido_id):
    pedido = get_or_404_empresa(PedidoCompra, pedido_id)
    return render_template('compras/ver_pedido.html', 
                           pedido=pedido, 
                           insumos=filtrar_por_empresa(Insumo.query, Insumo).all(), 
                           proveedores=filtrar_por_empresa(Proveedor.query, Proveedor).all(), 
                           sedes=filtrar_por_empresa(Sede.query, Sede).all(),
                           unidades=UnidadMedida.query.all())


@compras_bp.route('/compra/<int:pedido_id>/actualizar_datos', methods=['POST'])
@login_required
def actualizar_datos_pedido(pedido_id):
    p = get_or_404_empresa(PedidoCompra, pedido_id)
    
    if p.estado not in ['Borrador', 'Solicitado']: 
        flash('No se pueden editar datos de un pedido finalizado.', 'warning')
        return redirect(url_for('compras.ver_pedido', pedido_id=p.id))
    
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
        
    return redirect(url_for('compras.ver_pedido', pedido_id=p.id))


@compras_bp.route('/compra/<int:pedido_id>/agregar_item', methods=['POST'])
@login_required
def agregar_item_pedido(pedido_id):
    p = get_or_404_empresa(PedidoCompra, pedido_id)
    if p.estado != 'Borrador': return redirect(url_for('compras.ver_pedido', pedido_id=p.id))
    
    try:
        insumo_id = request.form.get('insumo_id')
        codigo = request.form.get('codigo_barras')
        insumo = None
        
        if insumo_id:
            insumo = get_or_404_empresa(Insumo, int(insumo_id))
        elif codigo:
            insumo = filtrar_por_empresa(Insumo.query, Insumo).filter(or_(Insumo.codigo == codigo, Insumo.nombre.ilike(codigo))).first()
            
        if not insumo:
            flash('No encontrado.', 'warning')
            return redirect(url_for('compras.ver_pedido', pedido_id=p.id))

        cant = safe_float(request.form.get('cantidad'), 1.0)
        if request.form.get('es_caja') == 'on':
            cant *= safe_float(request.form.get('unidades_por_caja'), 1.0)
            
        prec = safe_float(request.form.get('precio_unitario'), float(insumo.costo_promedio or 0))

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
        
    return redirect(url_for('compras.ver_pedido', pedido_id=p.id))


@compras_bp.route('/compra/item/actualizar/<int:detalle_id>', methods=['POST'])
@login_required
def actualizar_item_pedido(detalle_id):
    det = get_or_404_empresa(DetallePedidoCompra, detalle_id)
    if det.pedido.estado != 'Borrador': return redirect(url_for('compras.ver_pedido', pedido_id=det.pedido_id))
    
    try:
        cant = safe_float(request.form.get('cantidad'), 1.0)
        prec = safe_float(request.form.get('precio_unitario'), 0.0)
        
        det.pedido.total_estimado = det.pedido.total_estimado - (det.cantidad_solicitada * det.precio_unitario) + (cant * prec)
        det.cantidad_solicitada = cant
        det.precio_unitario = prec
        
        db.session.commit()
        flash('Actualizado.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error actualizando item pedido: {e}')
        flash('Error al actualizar.', 'danger')
    return redirect(url_for('compras.ver_pedido', pedido_id=det.pedido_id))


@compras_bp.route('/compra/item/eliminar/<int:detalle_id>', methods=['POST'])
@login_required
def eliminar_item_pedido(detalle_id):
    det = get_or_404_empresa(DetallePedidoCompra, detalle_id)
    pid = det.pedido_id
    if det.pedido.estado != 'Borrador': return redirect(url_for('compras.ver_pedido', pedido_id=pid))
    
    try:
        det.pedido.total_estimado -= (det.cantidad_solicitada * det.precio_unitario)
        db.session.delete(det)
        db.session.commit()
        flash('Eliminado.', 'info')
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error eliminando item pedido: {e}')
        
    return redirect(url_for('compras.ver_pedido', pedido_id=pid))


@compras_bp.route('/compra/<int:pedido_id>/confirmar', methods=['POST'])
@login_required
def confirmar_pedido(pedido_id):
    pedido = get_or_404_empresa(PedidoCompra, pedido_id)
    if not pedido.detalles: 
        flash('No se puede confirmar un pedido sin ítems.', 'warning')
        return redirect(url_for('compras.ver_pedido', pedido_id=pedido.id))
    
    try:
        pedido.estado = 'Solicitado'
        db.session.commit()
        flash(f'✅ Pedido #{pedido.numero_orden} confirmado exitosamente. Estado: Solicitado.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error confirmando pedido: {e}')
        flash('Error al confirmar el pedido.', 'danger')
        return redirect(url_for('compras.ver_pedido', pedido_id=pedido.id))
        
    return redirect(url_for('compras.lista_pedidos'))


@compras_bp.route('/compra/<int:pedido_id>/cancelar', methods=['POST'])
@login_required
def cancelar_pedido(pedido_id):
    try:
        p = get_or_404_empresa(PedidoCompra, pedido_id)
        p.estado = 'Cancelado'
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error cancelando pedido: {e}')
    return redirect(url_for('compras.lista_pedidos'))


@compras_bp.route('/compra/<int:pedido_id>/procesar_recepcion', methods=['POST'])
@login_required
def procesar_recepcion(pedido_id):
    pedido = get_or_404_empresa(PedidoCompra, pedido_id)
    if pedido.estado != 'Solicitado': return redirect(url_for('compras.ver_pedido', pedido_id=pedido.id))
    
    try:
        pedido.estado = 'Recibido'
        pedido.fecha_recepcion = datetime.now(timezone.utc).date()
        
        for d in pedido.detalles:
            cant = safe_float(request.form.get(f"recibido_{d.id}"), 0.0)
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
        
    return redirect(url_for('compras.ver_pedido', pedido_id=pedido.id))


# --- Gestión de Proveedores y Sedes ---

@compras_bp.route('/proveedores')
@login_required
def lista_proveedores():
    q = request.args.get('q', '').strip()
    ajax = request.args.get('ajax') == '1'
    
    todos_proveedores = filtrar_por_empresa(Proveedor.query, Proveedor).all()
    pedidos_empresa = filtrar_por_empresa(PedidoCompra.query, PedidoCompra).all()
    
    kpi_total_proveedores = len(todos_proveedores)
    kpi_pedidos_activos = sum(1 for p in pedidos_empresa if p.estado == 'Solicitado')
    kpi_inversion_compras = sum(p.total_estimado or 0 for p in pedidos_empresa if p.estado == 'Recibido')
    kpi_con_pedidos = len(set(p.proveedor_id for p in pedidos_empresa if p.proveedor_id))
    
    query = filtrar_por_empresa(Proveedor.query, Proveedor)
    if q:
        query = query.filter(or_(Proveedor.razon_social.ilike(f'%{q}%'), Proveedor.nit_rut.ilike(f'%{q}%'), Proveedor.contacto_nombre.ilike(f'%{q}%')))
    
    proveedores = query.order_by(Proveedor.razon_social).all()
    
    if ajax:
        return render_template('parciales/items_proveedores.html', proveedores=proveedores)
    return render_template('compras/lista_proveedores.html', 
                          proveedores=proveedores, 
                          search_query=q,
                          kpi_total_proveedores=kpi_total_proveedores,
                          kpi_pedidos_activos=kpi_pedidos_activos,
                          kpi_inversion_compras=kpi_inversion_compras,
                          kpi_con_pedidos=kpi_con_pedidos)


@compras_bp.route('/proveedor/nuevo', methods=['GET', 'POST'])
@compras_bp.route('/proveedor/editar/<int:proveedor_id>', methods=['GET', 'POST'])
@login_required
def nuevo_proveedor(proveedor_id=None):
    proveedor = get_or_404_empresa(Proveedor, proveedor_id) if proveedor_id else None
    
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
                p = Proveedor(
                    razon_social=request.form.get('razon_social'), 
                    nit_rut=request.form.get('nit_rut'), 
                    contacto_nombre=request.form.get('contacto_nombre'), 
                    telefono=request.form.get('telefono'), 
                    email=request.form.get('email'), 
                    direccion=request.form.get('direccion')
                )
                asignar_empresa(p)
                db.session.add(p)
            db.session.commit()
            return redirect(url_for('compras.lista_proveedores'))
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error guardando proveedor: {e}')
            flash('Error al guardar proveedor.', 'danger')
            
    return render_template('compras/nuevo_proveedor.html', proveedor=proveedor)


@compras_bp.route('/proveedor/eliminar/<int:proveedor_id>', methods=['POST'])
@solo_admin
def eliminar_proveedor(proveedor_id):
    try:
        prov = get_or_404_empresa(Proveedor, proveedor_id)
        db.session.delete(prov)
        db.session.commit()
        registrar_auditoria('ELIMINAR', 'Compras', f"Proveedor {prov.razon_social} eliminado")
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error eliminando proveedor: {e}')
        flash('No se puede eliminar. Puede tener pedidos asociados.', 'warning')
    return redirect(url_for('compras.lista_proveedores'))


@compras_bp.route('/configuracion/sedes')
@login_required
def lista_sedes():
    return render_template('compras/lista_sedes.html', sedes=filtrar_por_empresa(Sede.query, Sede).order_by(Sede.nombre).all())


@compras_bp.route('/configuracion/sede/nueva', methods=['GET', 'POST'])
@login_required
def nueva_sede(sede_id=None):
    # Validación de límite de sedes según el plan SaaS contratado
    if not current_user.es_superadmin and current_user.empresa:
        permite, mensaje, actual, limite = current_user.empresa.verificar_limite_sedes()
        if not permite:
            flash(f"⚠️ {mensaje}", 'warning')
            return redirect(url_for('compras.lista_sedes'))

    if request.method == 'POST':
        try:
            s = Sede(
                nombre=request.form.get('nombre'), 
                tipo=request.form.get('tipo'), 
                ubicacion_geo=request.form.get('ubicacion_geo')
            )
            asignar_empresa(s)
            db.session.add(s)
            db.session.commit()
            return redirect(url_for('compras.lista_sedes'))
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error guardando sede: {e}')
            flash('Error al guardar sede.', 'danger')
    return render_template('compras/nueva_sede.html', sede=None)


@compras_bp.route('/configuracion/sede/editar/<int:sede_id>', methods=['GET', 'POST'])
@login_required
def editar_sede(sede_id):
    sede = get_or_404_empresa(Sede, sede_id)
    if request.method == 'POST':
        try:
            sede.nombre = request.form.get('nombre')
            sede.tipo = request.form.get('tipo')
            sede.ubicacion_geo = request.form.get('ubicacion_geo')
            db.session.commit()
            return redirect(url_for('compras.lista_sedes'))
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error editando sede: {e}')
            flash('Error al editar sede.', 'danger')
    return render_template('compras/nueva_sede.html', sede=sede)


@compras_bp.route('/configuracion/sede/eliminar/<int:sede_id>', methods=['POST'])
@solo_admin
def eliminar_sede(sede_id):
    try:
        sede = get_or_404_empresa(Sede, sede_id)
        db.session.delete(sede)
        db.session.commit()
        registrar_auditoria('ELIMINAR', 'Compras', f"Sede {sede.nombre} eliminada")
    except Exception as e:
        logger.error(f'Error eliminando sede: {e}')
        flash('No se puede eliminar. Puede tener lotes asociados.', 'warning')
    return redirect(url_for('compras.lista_sedes'))
