"""
Módulo de Inventario — CRUD Insumos, Ajustes, APIs de búsqueda
"""
import logging
from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required
from sqlalchemy import or_
from ..models import Insumo, UnidadMedida, LoteInsumo, MovimientoInventario, InventarioSede, Sede
from ..extensions import db
from .helpers import (
    guardar_imagen, recalcular_costo_promedio, consumir_stock_fifo, safe_float, safe_int, solo_admin, registrar_auditoria, filtrar_por_empresa, asignar_empresa, get_or_404_empresa
)

logger = logging.getLogger(__name__)
inventario_bp = Blueprint('inventario', __name__)


@inventario_bp.route('/insumos')
@login_required
def lista_insumos():
    q = request.args.get('q', '').strip()
    filtro = request.args.get('filtro', 'todos')
    sede_id = request.args.get('sede_id', '')
    vista = request.args.get('vista', 'inventario')
    ajax = request.args.get('ajax') == '1'
    
    query = filtrar_por_empresa(Insumo.query, Insumo)

    if vista == 'inventario' and filtro == 'todos':
        query = query.filter(Insumo.cantidad_actual > 0)

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

    if sede_id:
        query = query.join(InventarioSede).filter(InventarioSede.sede_id == int(sede_id), InventarioSede.cantidad > 0)

    insumos = query.all()
    sedes = filtrar_por_empresa(Sede.query, Sede).all()
    if ajax:
        return render_template('parciales/items_insumos.html', insumos=insumos, sede_filtro=sede_id)
    return render_template('lista_insumos.html', insumos=insumos, vista=vista, sedes=sedes, sede_filtro=sede_id)


@inventario_bp.route('/insumo/nuevo', methods=['GET', 'POST'])
@inventario_bp.route('/insumo/editar/<int:insumo_id>', methods=['GET', 'POST'])
@login_required
def nuevo_insumo(insumo_id=None):
    if not UnidadMedida.query.first():
        try:
            db.session.add(UnidadMedida(nombre='Unidad', abreviatura='Und'))
            db.session.commit()
        except Exception as e:
            logger.error(f'Error creando unidad de medida: {e}')
        
    insumo = get_or_404_empresa(Insumo, insumo_id) if insumo_id else None
    unidades = UnidadMedida.query.all()
    
    if request.method == 'POST':
        try:
            if insumo: 
                insumo.nombre = request.form.get('nombre')
                insumo.codigo = request.form.get('codigo')
                insumo.tipo = request.form.get('tipo')
                insumo.unidad_medida_id = int(request.form.get('unidad_id'))
                insumo.stock_minimo = safe_float(request.form.get('stock_minimo'), 0.0)
                insumo.precio_venta = safe_float(request.form.get('precio_venta'), 0.0)
                
                if 'imagen' in request.files and request.files['imagen'].filename != '':
                    insumo.imagen_url = guardar_imagen(request.files['imagen'], 'insumos')
                
                try:
                    nuevo_stock = safe_float(request.form.get('stock_inicial'), float(insumo.cantidad_actual))
                    diff = nuevo_stock - insumo.cantidad_actual
                    if abs(diff) > 0.001:
                        if diff > 0:
                            db.session.add(LoteInsumo(insumo_id=insumo.id, fecha_compra=datetime.now(timezone.utc).date(), cantidad_inicial=diff, cantidad_actual=diff, costo_unitario=insumo.costo_promedio))
                        else:
                            consumir_stock_fifo(insumo, abs(diff))
                        
                        if diff > 0:
                            insumo.cantidad_actual = nuevo_stock
                            recalcular_costo_promedio(insumo)
                            
                        db.session.add(MovimientoInventario(tipo_movimiento='Ajuste Edición', cantidad=abs(diff), costo_unitario=insumo.costo_promedio, referencia=request.form.get('motivo_ajuste', 'Ajuste'), insumo_id=insumo.id))
                except Exception as e:
                    logger.error(f'Error en ajuste de stock: {e}')
            else:
                stock = safe_float(request.form.get('stock_inicial'), 0.0)
                costo = safe_float(request.form.get('costo_inicial'), 0.0)
                img = None
                if 'imagen' in request.files and request.files['imagen'].filename != '':
                    img = guardar_imagen(request.files['imagen'], 'insumos')
                
                nuevo = Insumo(
                    nombre=request.form.get('nombre'), 
                    codigo=request.form.get('codigo'), 
                    tipo=request.form.get('tipo'), 
                    unidad_medida_id=int(request.form.get('unidad_id')), 
                    stock_minimo=safe_float(request.form.get('stock_minimo'), 0.0), 
                    cantidad_actual=stock, 
                    costo_promedio=costo, 
                    precio_venta=safe_float(request.form.get('precio_venta'), 0.0),
                    imagen_url=img
                )
                asignar_empresa(nuevo)
                db.session.add(nuevo)
                db.session.commit()
                
                if stock > 0:
                    db.session.add(LoteInsumo(insumo_id=nuevo.id, fecha_compra=datetime.now(timezone.utc).date(), cantidad_inicial=stock, cantidad_actual=stock, costo_unitario=costo))
                    db.session.add(MovimientoInventario(tipo_movimiento='Inventario Inicial', cantidad=stock, costo_unitario=costo, referencia='Carga inicial', insumo_id=nuevo.id))
            
            db.session.commit()
            return redirect(url_for('inventario.lista_insumos'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {e}', 'danger')
            return render_template('nuevo_insumo.html', unidades=unidades, insumo=insumo)
            
    return render_template('nuevo_insumo.html', unidades=unidades, insumo=insumo)


@inventario_bp.route('/insumo/eliminar/<int:insumo_id>', methods=['POST'])
@solo_admin
def eliminar_insumo(insumo_id):
    try:
        ins = get_or_404_empresa(Insumo, insumo_id)
        db.session.delete(ins)
        db.session.commit()
        registrar_auditoria('ELIMINAR', 'Inventario', f"Insumo {ins.nombre} eliminado")
        flash('Eliminado.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error eliminando insumo: {e}')
        flash('No se puede eliminar. Puede tener movimientos asociados.', 'warning')
    return redirect(url_for('inventario.lista_insumos'))


@inventario_bp.route('/insumo/ajustar/<int:insumo_id>', methods=['POST'])
@login_required
def ajustar_stock_insumo(insumo_id):
    insumo = get_or_404_empresa(Insumo, insumo_id)
    try:
        nueva = safe_float(request.form.get('nueva_cantidad'), float(insumo.cantidad_actual))
        diff = nueva - insumo.cantidad_actual
        
        if nueva < 0 or diff == 0:
            return redirect(url_for('inventario.lista_insumos'))
            
        if diff > 0:
            db.session.add(LoteInsumo(insumo_id=insumo.id, fecha_compra=datetime.now(timezone.utc).date(), cantidad_inicial=diff, cantidad_actual=diff, costo_unitario=insumo.costo_promedio))
        else:
            consumir_stock_fifo(insumo, abs(diff))
            
        if diff > 0:
            insumo.cantidad_actual = nueva
            recalcular_costo_promedio(insumo)
            
        db.session.add(MovimientoInventario(tipo_movimiento='Ajuste', cantidad=abs(diff), costo_unitario=insumo.costo_promedio, referencia=request.form.get('motivo'), insumo_id=insumo.id, fecha=datetime.now(timezone.utc)))
        db.session.commit()
        flash('Ajustado.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error ajustando stock: {e}')
        flash(f'Error al ajustar: {e}', 'danger')
    return redirect(url_for('inventario.lista_insumos'))


# --- API: CREACIÓN RÁPIDA ---
@inventario_bp.route('/api/insumo/crear_rapido', methods=['POST'])
@login_required
def crear_insumo_rapido_api():
    try:
        data = request.json or {}
        codigo = data.get('codigo')
        if codigo:
            existe = filtrar_por_empresa(Insumo.query, Insumo).filter_by(codigo=codigo).first()
            if existe: return jsonify({'success': False, 'error': 'El código ya existe'})

        costo_inicial = safe_float(data.get('costo'), 0.0)

        nuevo = Insumo(
            nombre=data.get('nombre'),
            codigo=codigo,
            tipo=data.get('tipo', 'Insumo'),
            unidad_medida_id=int(data.get('unidad_id')),
            stock_minimo=0,
            cantidad_actual=0,
            costo_promedio=costo_inicial
        )
        asignar_empresa(nuevo)
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


@inventario_bp.route('/api/insumos/buscar', methods=['GET'])
@login_required
def buscar_insumos_api():
    q = request.args.get('q', '').strip()
    if not q: return jsonify([])
    
    insumos_query = filtrar_por_empresa(Insumo.query, Insumo)
    insumos = insumos_query.filter(or_(Insumo.nombre.ilike(f'%{q}%'), Insumo.codigo.ilike(f'%{q}%'))).limit(10).all()
    
    res = [{
        'id': i.id, 
        'nombre': i.nombre, 
        'codigo': i.codigo, 
        'unidad': i.unidad.abreviatura if i.unidad else '', 
        'costo': i.costo_promedio
    } for i in insumos]
    return jsonify(res)
