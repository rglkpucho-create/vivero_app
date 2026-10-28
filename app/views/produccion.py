"""
Módulo de Producción — Lotes, Labores, Especies, Cosechas
"""
import logging
from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from sqlalchemy import or_
from ..models import (
    Especie, LoteProduccion, LaborCampo, ConsumoInsumo, Insumo,
    Sede, MovimientoInventario, LoteInsumo, InventarioSede, UnidadMedida
)
from ..extensions import db
from .helpers import guardar_imagen, consumir_stock_fifo, safe_float, safe_int, solo_admin, registrar_auditoria, filtrar_por_empresa, asignar_empresa, get_or_404_empresa

logger = logging.getLogger(__name__)
produccion_bp = Blueprint('produccion', __name__)


@produccion_bp.route('/produccion/lote/cambiar_estado/<int:lote_id>', methods=['POST'])
@login_required
def cambiar_estado_lote(lote_id):
    lote = get_or_404_empresa(LoteProduccion, lote_id)
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
        
    return redirect(url_for('produccion.ver_lote', lote_id=lote.id))


@produccion_bp.route('/produccion/lote/cosechar', methods=['POST'])
@login_required
def registrar_cosecha():
    lote_id = request.form.get('lote_id')
    
    try:
        lote = get_or_404_empresa(LoteProduccion, lote_id)
        fecha_str = request.form.get('fecha') or datetime.now(timezone.utc).strftime('%Y-%m-%d')
        fecha_dt = datetime.strptime(fecha_str, '%Y-%m-%d')
        notas = request.form.get('notas', '').strip()
        modo_destino = request.form.get('modo_destino', 'auto')
        tipo_cosecha = request.form.get('tipo_cosecha', 'parcial')
        cantidad = safe_float(request.form.get('cantidad'), 0.0)
        unidad_id = safe_int(request.form.get('unidad_id'), None)
        precio_venta = safe_float(request.form.get('precio_venta'), 0.0)

        if cantidad <= 0:
            flash('La cantidad cosechada debe ser mayor a 0.', 'warning')
            return redirect(url_for('produccion.ver_lote', lote_id=lote.id))

        # 1. Determinar el producto destino en catálogo
        if modo_destino == 'auto':
            nombre_producto = request.form.get('nombre_producto', '').strip()
            if not nombre_producto:
                nombre_producto = f"{lote.especie.nombre_comun} Fresco"
            
            # Buscar si ya existe
            producto = Insumo.query.filter_by(empresa_id=lote.empresa_id, nombre=nombre_producto).first()
            if not producto:
                codigo_sugerido = f"COS-{lote.especie_id}-{int(datetime.now().timestamp()) % 100000}"
                if not unidad_id:
                    u_kg = UnidadMedida.query.filter_by(abreviatura='Kg').first()
                    unidad_id = u_kg.id if u_kg else 1

                producto = Insumo(
                    empresa_id=lote.empresa_id,
                    nombre=nombre_producto,
                    codigo=codigo_sugerido,
                    tipo='Producto Comercial',
                    unidad_medida_id=unidad_id,
                    stock_minimo=5.0,
                    cantidad_actual=0.0,
                    costo_promedio=0.0,
                    precio_venta=precio_venta if precio_venta > 0 else (lote.especie.precio_venta_sugerido if lote.especie else 0.0),
                    imagen_url=lote.especie.imagen_url if lote.especie else None
                )
                db.session.add(producto)
                db.session.flush()

            if lote.especie:
                lote.especie.producto_cosecha_id = producto.id
            if precio_venta > 0:
                producto.precio_venta = precio_venta
        else:
            producto_id = request.form.get('producto_id')
            producto = get_or_404_empresa(Insumo, producto_id)
            if precio_venta > 0:
                producto.precio_venta = precio_venta

        # 2. Asignación y ponderación de costos de producción
        costo_unitario = 0.0
        if lote.costo_total and lote.costo_total > 0 and cantidad > 0:
            if tipo_cosecha == 'total':
                costo_unitario = round(lote.costo_total / cantidad, 2)
            else:
                costo_unitario = round((lote.costo_total * 0.25) / cantidad, 2)

        stock_prev = producto.cantidad_actual or 0.0
        costo_prev = producto.costo_promedio or 0.0
        if (stock_prev + cantidad) > 0 and costo_unitario > 0:
            producto.costo_promedio = round(((stock_prev * costo_prev) + (cantidad * costo_unitario)) / (stock_prev + cantidad), 2)
        elif costo_unitario > 0 and stock_prev == 0:
            producto.costo_promedio = costo_unitario

        # 3. Sumar existencia al inventario general y por sede
        producto.cantidad_actual += cantidad

        if lote.sede_id:
            inv_sede = InventarioSede.query.filter_by(insumo_id=producto.id, sede_id=lote.sede_id).first()
            if not inv_sede:
                inv_sede = InventarioSede(insumo_id=producto.id, sede_id=lote.sede_id, cantidad=0.0)
                db.session.add(inv_sede)
            inv_sede.cantidad += cantidad

        # 4. Movimientos y Kardex
        db.session.add(MovimientoInventario(
            tipo_movimiento='Producción Interna',
            cantidad=cantidad,
            costo_unitario=costo_unitario,
            referencia=f"Cosecha Lote {lote.codigo_lote} ({tipo_cosecha.capitalize()})",
            insumo_id=producto.id,
            fecha=fecha_dt
        ))

        db.session.add(LoteInsumo(
            insumo_id=producto.id,
            fecha_compra=fecha_dt.date() if hasattr(fecha_dt, 'date') else fecha_dt,
            cantidad_inicial=cantidad,
            cantidad_actual=cantidad,
            costo_unitario=costo_unitario
        ))

        # 5. Registro de Labor de Cosecha
        abrev = producto.unidad.abreviatura if producto.unidad else 'Und'
        desc_labor = f"Cosecha {tipo_cosecha.capitalize()}: {cantidad:g} {abrev} de '{producto.nombre}'."
        if notas:
            desc_labor += f" | {notas}"

        db.session.add(LaborCampo(
            lote_id=lote.id,
            usuario_id=current_user.id,
            fecha=fecha_dt.date() if hasattr(fecha_dt, 'date') else fecha_dt,
            tipo_labor='Cosecha',
            descripcion=desc_labor
        ))

        # 6. Gestión de plantas del lote según modalidad
        if tipo_cosecha == 'total':
            plantas_extraidas = safe_int(request.form.get('plantas_extraidas'), lote.cantidad_actual)
            lote.cantidad_actual = max(0, lote.cantidad_actual - plantas_extraidas)
            if lote.cantidad_actual == 0:
                lote.estado = 'Finalizado'
                flash(f'🌾 ¡Cosecha Final Registrada! Se ingresaron {cantidad:g} {abrev} de "{producto.nombre}" al inventario. El lote quedó completado.', 'success')
            else:
                flash(f'🌾 ¡Cosecha Registrada! Se ingresaron {cantidad:g} {abrev} de "{producto.nombre}". Quedan {lote.cantidad_actual} plantas activas.', 'success')
        else:
            flash(f'🌿 ¡Cosecha Parcial Registrada! Se ingresaron {cantidad:g} {abrev} de "{producto.nombre}" listos para venta en POS. Las {lote.cantidad_actual} plantas continúan activas para próximos cortes.', 'success')

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error en cosecha: {e}")
        flash(f'Error al registrar cosecha: {str(e)}', 'danger')

    return redirect(url_for('produccion.ver_lote', lote_id=lote_id))



@produccion_bp.route('/produccion/lote/registrar_baja', methods=['POST'])
@login_required
def registrar_baja_lote():
    lote_id = request.form.get('lote_id')
    try:
        lote = get_or_404_empresa(LoteProduccion, lote_id)
        cantidad_baja = safe_int(request.form.get('cantidad_baja'), 0)
        motivo = request.form.get('motivo', 'Plaga / Enfermedad')
        fecha_str = request.form.get('fecha')
        observaciones = request.form.get('observaciones', '').strip()
        fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d').date() if fecha_str else datetime.now(timezone.utc).date()
        
        if cantidad_baja <= 0:
            flash('La cantidad de baja debe ser mayor a 0.', 'warning')
            return redirect(url_for('produccion.ver_lote', lote_id=lote.id))
            
        if cantidad_baja > lote.cantidad_actual:
            flash(f'No puedes dar de baja {cantidad_baja} plantas. Solo hay {lote.cantidad_actual} activas.', 'danger')
            return redirect(url_for('produccion.ver_lote', lote_id=lote.id))
            
        lote.cantidad_actual -= cantidad_baja
        if lote.cantidad_actual <= 0:
            lote.estado = 'Finalizado'
            
        desc = f"Baja de {cantidad_baja} plantas por {motivo}. {observaciones}".strip()
        labor = LaborCampo(
            lote_id=lote.id,
            usuario_id=current_user.id,
            fecha=fecha_obj,
            tipo_labor='Merma / Descarte',
            descripcion=desc
        )
        db.session.add(labor)
        db.session.commit()
        
        registrar_auditoria('EDITAR', 'Producción', f"Merma de {cantidad_baja} plantas en lote {lote.codigo_lote} ({motivo})")
        flash(f'Merma registrada: {cantidad_baja} plantas dadas de baja ({motivo}).', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error registrando merma: {e}")
        flash(f'Error al registrar merma: {str(e)}', 'danger')
        
    return redirect(url_for('produccion.ver_lote', lote_id=lote_id))


@produccion_bp.route('/produccion/lotes')
@login_required
def lista_lotes():
    query_str = request.args.get('q', '').strip()
    sede_id = request.args.get('sede_id')
    proposito = request.args.get('proposito')
    ajax = request.args.get('ajax') == '1'

    sedes = filtrar_por_empresa(Sede.query, Sede).order_by(Sede.nombre).all()
    query = filtrar_por_empresa(LoteProduccion.query, LoteProduccion).join(Especie).outerjoin(Sede)
    
    if query_str:
        query = query.filter(or_(
            LoteProduccion.codigo_lote.ilike(f'%{query_str}%'), 
            Especie.nombre_comun.ilike(f'%{query_str}%'), 
            LoteProduccion.ubicacion.ilike(f'%{query_str}%')
        ))
        
    if sede_id and sede_id.isdigit():
        query = query.filter(LoteProduccion.sede_id == int(sede_id))
        
    filtro = request.args.get('filtro')
    if filtro == 'crecimiento':
        query = query.filter(LoteProduccion.estado == 'En Crecimiento')
    elif proposito and proposito in ['Venta Plantula', 'Produccion Fruto']:
        query = query.filter(LoteProduccion.proposito == proposito)
    
    lotes = query.order_by(LoteProduccion.fecha_siembra.desc()).all()

    vista = request.args.get('vista')
    resumen_sedes = {}
    
    if vista == 'informativa':
        sedes_ids = {l.sede_id for l in lotes if l.sede_id}
        sedes_obj = Sede.query.filter(Sede.id.in_(sedes_ids)).all()
        for s in sedes_obj:
            resumen_sedes[s.nombre] = {}
            lotes_sede = [l for l in lotes if l.sede_id == s.id]
            for l in lotes_sede:
                proposito_str = "Cultivo Permanente" if l.proposito == 'Produccion Fruto' else "Comercializar Planta"
                esp_nombre = f"{l.especie.nombre_comun} - {proposito_str}"
                resumen_sedes[s.nombre][esp_nombre] = resumen_sedes[s.nombre].get(esp_nombre, 0) + (l.cantidad_actual or 0)

    if ajax:
        return render_template('parciales/items_lotes.html', lotes=lotes, today=datetime.now(timezone.utc).date())
    
    return render_template('produccion/lista_lotes.html', 
                           lotes=lotes, 
                           sedes=sedes, 
                           vista=vista,
                           resumen_sedes=resumen_sedes,
                           today=datetime.now(timezone.utc).date())


@produccion_bp.route('/siembra/nueva', methods=['GET', 'POST'])
@login_required
def nuevo_lote():
    # Validación de límite de lotes según el plan SaaS contratado
    if not current_user.es_superadmin and current_user.empresa:
        permite, mensaje, actual, limite = current_user.empresa.verificar_limite_lotes()
        if not permite:
            flash(f"⚠️ {mensaje}", 'warning')
            return redirect(url_for('produccion.lista_lotes'))

    if request.method == 'POST':
        try:
            nuevo = LoteProduccion(
                codigo_lote=f"SMB-{int(datetime.now().timestamp())}",
                especie_id=int(request.form.get('especie_id')),
                sede_id=int(request.form.get('sede_id')),
                cantidad_sembrada=safe_int(request.form.get('cantidad'), 1),
                cantidad_actual=safe_int(request.form.get('cantidad'), 1),
                fecha_siembra=datetime.strptime(request.form.get('fecha_siembra'), '%Y-%m-%d').date(),
                ubicacion=request.form.get('ubicacion'),
                proposito=request.form.get('proposito'),
                estado='En Crecimiento'
            )
            db.session.add(nuevo)
            asignar_empresa(nuevo)
            db.session.commit()
            return redirect(url_for('produccion.lista_lotes'))
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error creando lote: {e}')
            flash(f'Error al crear lote: {e}', 'danger')
            
    return render_template('produccion/nuevo_lote.html', 
                           sedes=filtrar_por_empresa(Sede.query, Sede).all(), 
                           especies=filtrar_por_empresa(Especie.query, Especie).all(), 
                           today_str=datetime.now(timezone.utc).strftime('%Y-%m-%d'))


@produccion_bp.route('/produccion/lote/<int:lote_id>')
@login_required
def ver_lote(lote_id):
    lote = get_or_404_empresa(LoteProduccion, lote_id)
    insumos = filtrar_por_empresa(Insumo.query, Insumo).order_by(Insumo.nombre).all()
    unidades = UnidadMedida.query.order_by(UnidadMedida.id).all()
    
    # Producto sugerido de cosecha
    producto_sugerido = None
    if lote.especie:
        producto_sugerido = Insumo.query.filter(
            Insumo.empresa_id == lote.empresa_id,
            Insumo.nombre.ilike(f"%{lote.especie.nombre_comun}%")
        ).first()

    return render_template('produccion/ver_lote.html', 
                           lote=lote, 
                           insumos=insumos,
                           unidades=unidades,
                           producto_sugerido=producto_sugerido,
                           today_str=datetime.now(timezone.utc).strftime('%Y-%m-%d'),
                           datetime=datetime)



@produccion_bp.route('/trazabilidad/lote/<int:id>')
def trazabilidad_lote(id):
    lote = get_or_404_empresa(LoteProduccion, id)
    return render_template('trazabilidad_publica.html', 
                           tipo='lote',
                           data=lote,
                           datetime=datetime)


@produccion_bp.route('/produccion/lote/eliminar/<int:lote_id>', methods=['POST'])
@solo_admin
def eliminar_lote(lote_id):
    try: 
        lote = get_or_404_empresa(LoteProduccion, lote_id)
        for l in LaborCampo.query.filter_by(lote_id=lote.id).all():
            for c in l.consumos:
                db.session.delete(c)
            db.session.delete(l)
        db.session.delete(lote)
        db.session.commit()
        registrar_auditoria('ELIMINAR', 'Producción', f"Lote {lote.codigo_lote} eliminado")
        flash('Eliminado.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error eliminando lote: {e}')
        flash('Error al eliminar lote.', 'danger')
        
    return redirect(url_for('produccion.lista_lotes'))


@produccion_bp.route('/produccion/lote/ajustar/<int:lote_id>', methods=['POST'])
@login_required
def ajustar_stock_lote(lote_id):
    try: 
        lote = get_or_404_empresa(LoteProduccion, lote_id)
        lote.cantidad_actual = safe_int(request.form.get('nueva_cantidad'), lote.cantidad_actual)
        if lote.cantidad_actual == 0:
            lote.estado = 'Finalizado'
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error ajustando stock lote: {e}')
        
    return redirect(url_for('produccion.ver_lote', lote_id=lote_id))


@produccion_bp.route('/produccion/labor/guardar', methods=['POST'])
@login_required
def registrar_labor():
    try:
        lote = get_or_404_empresa(LoteProduccion, request.form.get('lote_id'))
        
        labor = LaborCampo(
            lote_id=lote.id,
            tipo_labor=request.form.get('tipo_labor'),
            descripcion=request.form.get('descripcion'),
            usuario_id=current_user.id,
            fecha=datetime.strptime(request.form.get('fecha'), '%Y-%m-%d').date() if request.form.get('fecha') else datetime.now(timezone.utc).date()
        )
        
        foto = request.files.get('foto_labor')
        if foto:
            labor.imagen_url = guardar_imagen(foto, 'labores')

        db.session.add(labor)
        db.session.flush()
        
        insumo_ids = request.form.getlist('insumo_id[]')
        cantidades = request.form.getlist('cantidad_usada[]')
        
        if request.form.get('insumo_id'):
            insumo_ids.append(request.form.get('insumo_id'))
            cantidades.append(request.form.get('cantidad_insumo') or 0)

        for i_id, cant in zip(insumo_ids, cantidades):
            cant_f = safe_float(cant, 0.0)
            if i_id and cant_f > 0:
                insumo = get_or_404_empresa(Insumo, int(i_id))
                costo, _ = consumir_stock_fifo(insumo, cant_f)
                
                db.session.add(ConsumoInsumo(
                    labor_id=labor.id,
                    insumo_id=insumo.id,
                    cantidad=cant_f,
                    subtotal=costo
                ))
                lote.costo_total += (costo or 0)
            
        db.session.commit()
        flash('Labor y multimedia registrados correctamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {e}', 'danger')
        
    return redirect(url_for('produccion.ver_lote', lote_id=request.form.get('lote_id')))


@produccion_bp.route('/produccion/labor/editar/<int:labor_id>', methods=['POST'])
@login_required
def editar_labor(labor_id):
    labor = get_or_404_empresa(LaborCampo, labor_id)
    try:
        labor.tipo_labor = request.form.get('tipo_labor')
        labor.descripcion = request.form.get('descripcion')
        db.session.commit()
        flash('Actualizado.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error editando labor: {e}')
        flash('Error al editar labor.', 'danger')
        
    return redirect(url_for('produccion.ver_lote', lote_id=labor.lote_id))


@produccion_bp.route('/produccion/labor/eliminar/<int:labor_id>', methods=['POST'])
@solo_admin
def eliminar_labor(labor_id):
    labor = get_or_404_empresa(LaborCampo, labor_id)
    lid = labor.lote_id
    try:
        for c in labor.consumos:
            c.insumo.cantidad_actual += c.cantidad
            labor.lote.costo_total -= c.subtotal
            db.session.delete(c)
        db.session.delete(labor)
        db.session.commit()
        registrar_auditoria('ELIMINAR', 'Producción', f"Labor {labor.tipo_labor} eliminada del lote {lid}")
        flash('Eliminado.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error eliminando labor: {e}')
        
    return redirect(url_for('produccion.ver_lote', lote_id=lid))


@produccion_bp.route('/produccion/especies')
@login_required
def lista_especies():
    return render_template('produccion/lista_especies.html', especies=filtrar_por_empresa(Especie.query, Especie).all())


@produccion_bp.route('/produccion/especie/nueva', methods=['GET', 'POST'])
@login_required
def nueva_especie():
    if request.method == 'POST':
        try:
            imagen_path = None
            if 'imagen' in request.files:
                file = request.files['imagen']
                if file and file.filename != '':
                    imagen_path = guardar_imagen(file, 'especies')
            
            prod_id = request.form.get('producto_cosecha_id')
            nuevo_prod = request.form.get('nuevo_producto_cosecha')

            if nuevo_prod and nuevo_prod.strip():
                insumo = Insumo(
                    nombre=nuevo_prod.strip(),
                    tipo='Comercial',
                    unidad_medida_id=1,
                    cantidad_actual=0,
                    costo_promedio=0
                )
                db.session.add(insumo)
                asignar_empresa(insumo)
                db.session.flush()
                prod_id = insumo.id

            esp = Especie(
                nombre_comun=request.form.get('nombre_comun'),
                nombre_cientifico=request.form.get('nombre_cientifico'),
                dias_ciclo_estimado=safe_int(request.form.get('dias_ciclo'), 0),
                detalles_cuidado=request.form.get('detalles_cuidado'),
                imagen_url=imagen_path,
                precio_venta_sugerido=safe_float(request.form.get('precio_venta_sugerido'), 0.0),
                producto_cosecha_id=int(prod_id) if prod_id else None
            )
            asignar_empresa(esp)
            db.session.add(esp)
            db.session.commit()
            return redirect(url_for('produccion.lista_especies'))
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error creando especie: {e}')
            flash(f'Error: {e}', 'danger')
            
    return render_template('produccion/nueva_especie.html', insumos=filtrar_por_empresa(Insumo.query, Insumo).all())


@produccion_bp.route('/produccion/especie/editar_ficha/<int:especie_id>', methods=['POST'])
@login_required
def editar_ficha_especie(especie_id):
    e = get_or_404_empresa(Especie, especie_id)
    lote_id = request.args.get('lote_id')
    try: 
        e.dias_ciclo_estimado = safe_int(request.form.get('dias_ciclo'), e.dias_ciclo_estimado or 0)
        e.detalles_cuidado = request.form.get('detalles_cuidado')
        if request.form.get('precio_venta_sugerido') is not None:
            e.precio_venta_sugerido = safe_float(request.form.get('precio_venta_sugerido'), 0.0)

        nuevo_prod = request.form.get('nuevo_producto_cosecha')
        if nuevo_prod and nuevo_prod.strip():
            insumo = Insumo(
                nombre=nuevo_prod.strip(),
                tipo='Comercial',
                unidad_medida_id=1,
                cantidad_actual=0,
                costo_promedio=0
            )
            asignar_empresa(insumo)
            db.session.add(insumo)
            db.session.flush()
            e.producto_cosecha_id = insumo.id
        elif request.form.get('producto_cosecha_id'):
            e.producto_cosecha_id = int(request.form.get('producto_cosecha_id'))
        
        if 'imagen_editar' in request.files:
            file = request.files['imagen_editar']
            if file and file.filename != '':
                e.imagen_url = guardar_imagen(file, 'especies')
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error editando ficha especie: {e}')
        flash(f'Error: {e}', 'danger')
        
    return redirect(url_for('produccion.ver_lote', lote_id=lote_id)) if lote_id else redirect(url_for('produccion.lista_especies'))


@produccion_bp.route('/produccion/especie/eliminar/<int:especie_id>', methods=['POST'])
@solo_admin
def eliminar_especie(especie_id):
    try:
        esp = get_or_404_empresa(Especie, especie_id)
        db.session.delete(esp)
        db.session.commit()
        registrar_auditoria('ELIMINAR', 'Producción', f"Especie {esp.nombre_comun} eliminada")
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error eliminando especie: {e}')
        
    return redirect(url_for('produccion.lista_especies'))
