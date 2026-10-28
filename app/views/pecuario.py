"""
Módulo Pecuario — Animales, Producción, Salud, Alimentación, Razas
"""
import logging
from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, abort
from flask_login import login_required, current_user
from sqlalchemy import or_
from ..models import (
    LoteAnimal, RazaAnimal, ProduccionAnimal, ConsumoAnimal, EventoSanitario,
    Insumo, MovimientoInventario, InventarioSede, Sede, UnidadMedida
)
from ..extensions import db
from .helpers import (
    guardar_imagen, consumir_stock_fifo, safe_float, safe_int, 
    solo_admin, registrar_auditoria, filtrar_por_empresa, asignar_empresa, get_or_404_empresa
)

logger = logging.getLogger(__name__)
pecuario_bp = Blueprint('pecuario', __name__)


@pecuario_bp.before_request
def verificar_acceso_pecuario():
    """Restringe el acceso al módulo pecuario si el plan de la empresa no lo incluye."""
    if not current_user.is_authenticated:
        return
    if getattr(current_user, 'es_superadmin', False):
        return
    emp = current_user.empresa
    if emp and not emp.permite_modulo('pecuario'):
        flash(f"🐄 El Módulo Pecuario y Ganadero es exclusivo del Plan Agro-Hacienda. Tu plan actual es '{emp.plan_nombre}'. Actualiza tu suscripción para desbloquearlo.", "warning")
        return redirect(url_for('dashboard.dashboard'))


# --- CRUD RAZAS ---

@pecuario_bp.route('/pecuario/razas')
@login_required
def lista_razas_animales():
    razas = filtrar_por_empresa(RazaAnimal.query, RazaAnimal).all()
    return render_template('pecuario/lista_razas.html', razas=razas)


@pecuario_bp.route('/pecuario/raza/nueva', methods=['GET', 'POST'])
@login_required
def nueva_raza_animal():
    if request.method == 'POST':
        try:
            ruta_imagen = guardar_imagen(request.files.get('foto'), 'especies')

            nueva_raza = RazaAnimal(
                nombre=request.form.get('nombre'),
                especie=request.form.get('especie'),
                proposito_ideal=request.form.get('proposito_ideal'),
                rendimiento_est=request.form.get('rendimiento_est'),
                ciclo_tecnico=request.form.get('ciclo_tecnico'),
                cuidados_tecnicos=request.form.get('cuidados_tecnicos'),
                imagen_url=ruta_imagen
            )
            db.session.add(nueva_raza)
            asignar_empresa(nueva_raza)
            db.session.commit()
            flash('Ficha Técnica de Raza añadida exitosamente.', 'success')
            return redirect(url_for('pecuario.lista_razas_animales'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al guardar: {str(e)}', 'danger')
            
    return render_template('pecuario/nueva_raza.html')


@pecuario_bp.route('/pecuario/raza/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_raza_animal(id):
    raza = get_or_404_empresa(RazaAnimal, id)
    if request.method == 'POST':
        try:
            ruta_imagen = guardar_imagen(request.files.get('foto'), 'especies')
            if ruta_imagen:
                raza.imagen_url = ruta_imagen
                
            raza.nombre = request.form.get('nombre')
            raza.especie = request.form.get('especie')
            raza.proposito_ideal = request.form.get('proposito_ideal')
            raza.rendimiento_est = request.form.get('rendimiento_est')
            raza.ciclo_tecnico = request.form.get('ciclo_tecnico')
            raza.cuidados_tecnicos = request.form.get('cuidados_tecnicos')
            
            db.session.commit()
            flash('Ficha Técnica actualizada.', 'success')
            return redirect(url_for('pecuario.lista_razas_animales'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')
            
    return render_template('pecuario/nueva_raza.html', raza=raza, edit_mode=True)


@pecuario_bp.route('/pecuario/raza/eliminar/<int:id>', methods=['POST'])
@solo_admin
def eliminar_raza_animal(id):
    raza = get_or_404_empresa(RazaAnimal, id)
    try:
        if len(raza.animales) > 0:
            flash('No se puede eliminar la raza porque hay animales asociados a ella.', 'warning')
            return redirect(url_for('pecuario.lista_razas_animales'))
            
        db.session.delete(raza)
        db.session.commit()
        registrar_auditoria('ELIMINAR', 'Pecuario', f"Raza {raza.nombre} eliminada.")
        flash('Raza eliminada correctamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar: {str(e)}', 'danger')
        
    return redirect(url_for('pecuario.lista_razas_animales'))


# --- ANIMALES ---

@pecuario_bp.route('/animales')
@login_required
def lista_animales():
    sedes = filtrar_por_empresa(Sede.query, Sede).all()
    q = request.args.get('q', '').strip()
    sede_id = request.args.get('sede_id', '').strip()
    especie_filtro = request.args.get('especie', '').strip()
    vista = request.args.get('vista', 'tarjetas')
    ajax = request.args.get('ajax') == '1'
    
    query = filtrar_por_empresa(LoteAnimal.query, LoteAnimal)
    if q:
        query = query.filter(or_(
            LoteAnimal.nombre.ilike(f'%{q}%'),
            LoteAnimal.codigo.ilike(f'%{q}%'),
            LoteAnimal.raza.ilike(f'%{q}%')
        ))
    if sede_id and sede_id.isdigit():
        query = query.filter(LoteAnimal.sede_id == int(sede_id))
    if especie_filtro:
        query = query.filter(LoteAnimal.especie == especie_filtro)
        
    animales = query.order_by(LoteAnimal.fecha_ingreso.desc()).all()
    
    resumen_sedes = {}
    if vista == 'informativa':
        lotes_activos = filtrar_por_empresa(LoteAnimal.query, LoteAnimal).filter(LoteAnimal.cantidad_actual > 0, LoteAnimal.estado == 'Activo').all()
        for lote in lotes_activos:
            sede_nom = lote.sede.nombre if lote.sede else "Sin Sede"
            tipo_base = lote.raza_rel.nombre if lote.raza_rel else (lote.raza or lote.especie)
            tipo_nom = f"{tipo_base} - {lote.proposito}" if lote.proposito else tipo_base
            
            if sede_nom not in resumen_sedes:
                resumen_sedes[sede_nom] = {}
            
            resumen_sedes[sede_nom][tipo_nom] = resumen_sedes[sede_nom].get(tipo_nom, 0) + lote.cantidad_actual

    if ajax:
        return render_template('parciales/items_animales.html', animales=animales)

    return render_template('pecuario/lista_animales.html', 
                           animales=animales, 
                           sedes=sedes, 
                           vista=vista, 
                           resumen_sedes=resumen_sedes)


@pecuario_bp.route('/animal/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo_animal():
    sedes = filtrar_por_empresa(Sede.query, Sede).all()
    razas = filtrar_por_empresa(RazaAnimal.query, RazaAnimal).all()
    
    if request.method == 'POST':
        try:
            ruta_imagen = None
            if 'foto' in request.files:
                file = request.files['foto']
                if file and file.filename != '':
                    ruta_imagen = guardar_imagen(file, 'animales')

            f_nac_str = request.form.get('fecha_nacimiento')
            f_nac = datetime.strptime(f_nac_str, '%Y-%m-%d').date() if f_nac_str else None
            
            f_ing_str = datetime.now(timezone.utc).date()

            nuevo = LoteAnimal(
                codigo=request.form.get('codigo'),
                nombre=request.form.get('nombre'),
                tipo=request.form.get('tipo', 'Individual'), 
                especie=request.form.get('especie'),
                raza=request.form.get('raza'),
                genero=request.form.get('genero'),
                ubicacion=request.form.get('ubicacion'),
                raza_id=request.form.get('raza_id') if request.form.get('raza_id') else None,
                fecha_nacimiento=f_nac,
                fecha_ingreso=f_ing_str,
                cantidad_inicial=safe_int(request.form.get('cantidad'), 1),
                cantidad_actual=safe_int(request.form.get('cantidad'), 1),
                peso_actual=safe_float(request.form.get('peso'), 0.0),
                sede_id=int(request.form.get('sede_id')),
                proposito=request.form.get('proposito'),
                estado='Activo',
                costo_acumulado=safe_float(request.form.get('costo_inicial'), 0.0),
                imagen_url=ruta_imagen 
            )
            
            db.session.add(nuevo)
            asignar_empresa(nuevo)
            db.session.commit()
            
            flash('Animal/Lote registrado con éxito.', 'success')
            return redirect(url_for('pecuario.lista_animales'))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error registrando animal: {e}") 
            flash(f'Error: {str(e)}', 'danger')
            
    return render_template('pecuario/nuevo_animal.html', sedes=sedes, razas=razas, today=datetime.now(timezone.utc).date())


@pecuario_bp.route('/animal/<int:id>')
@login_required
def ver_animal(id):
    animal = get_or_404_empresa(LoteAnimal, id)
    productos_venta = filtrar_por_empresa(Insumo.query, Insumo).filter_by(tipo='Comercial').all()
    alimentos = filtrar_por_empresa(Insumo.query, Insumo).filter_by(tipo='Insumo').all()
    unidades = UnidadMedida.query.all()
    return render_template('pecuario/ver_animal.html', 
                           animal=animal, 
                           productos=productos_venta, 
                           alimentos=alimentos, 
                           unidades=unidades,
                           today=datetime.now(timezone.utc).date())


@pecuario_bp.route('/trazabilidad/animal/<int:id>')
def trazabilidad_animal(id):
    animal = get_or_404_empresa(LoteAnimal, id)
    return render_template('trazabilidad_publica.html', 
                           tipo='animal',
                           data=animal,
                           datetime=datetime)


@pecuario_bp.route('/animal/producir', methods=['POST'])
@login_required
def registrar_produccion_animal():
    animal_id = request.form.get('animal_id')
    try:
        animal = get_or_404_empresa(LoteAnimal, animal_id)
        
        prod_id = request.form.get('producto_id')
        nuevo_prod = request.form.get('nuevo_producto_produccion')
        unidad_id = request.form.get('unidad_medida_id') or 1
        precio_venta = safe_float(request.form.get('precio_venta'), 0.0)

        if nuevo_prod and nuevo_prod.strip():
            producto = Insumo(
                nombre=nuevo_prod.strip(),
                tipo='Comercial',
                unidad_medida_id=unidad_id, 
                cantidad_actual=0,
                costo_promedio=0,
                precio_venta=precio_venta
            )
            asignar_empresa(producto)
            db.session.add(producto)
            db.session.flush()
        else:
            producto = get_or_404_empresa(Insumo, prod_id)
            if precio_venta > 0 and (not producto.precio_venta or producto.precio_venta == 0):
                producto.precio_venta = precio_venta
                
        cantidad = safe_float(request.form.get('cantidad'), 0.0)
        
        fecha_str = request.form.get('fecha')
        fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d') if fecha_str else datetime.now(timezone.utc)

        prod = ProduccionAnimal(
            lote_animal_id=animal.id,
            producto_id=producto.id,
            cantidad=cantidad,
            observaciones=request.form.get('observaciones', f'Producción extraída de {animal.nombre}'),
            fecha=fecha_obj
        )
        db.session.add(prod)
        
        producto.cantidad_actual += cantidad
        
        if animal.sede_id:
            inv_sede = InventarioSede.query.filter_by(insumo_id=producto.id, sede_id=animal.sede_id).first()
            if not inv_sede:
                inv_sede = InventarioSede(insumo_id=producto.id, sede_id=animal.sede_id, cantidad=0)
                db.session.add(inv_sede)
            inv_sede.cantidad += cantidad
        
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
        
    return redirect(url_for('pecuario.ver_animal', id=animal_id))


@pecuario_bp.route('/animal/evento_salud', methods=['POST'])
@login_required
def registrar_evento_salud_animal():
    animal_id = request.form.get('animal_id')
    try:
        animal = get_or_404_empresa(LoteAnimal, animal_id)
        costo_float = safe_float(request.form.get('costo_servicio'), 0.0)

        foto = request.files.get('foto_evento')
        imagen_url = guardar_imagen(foto, 'salud_animal') if foto and foto.filename != '' else None

        fecha_raw = request.form.get('fecha')
        try:
            fecha_evento = datetime.strptime(fecha_raw, '%Y-%m-%d').date() if fecha_raw else datetime.now(timezone.utc).date()
        except Exception:
            fecha_evento = datetime.now(timezone.utc).date()

        vet = request.form.get('veterinario', '').strip()
        desc = request.form.get('descripcion', '').strip()
        if vet:
            desc = f"👨‍⚕️ {vet} — {desc}"

        nuevo_peso = safe_float(request.form.get('nuevo_peso'), 0.0)
        if nuevo_peso > 0:
            animal.peso_actual = nuevo_peso

        evt = EventoSanitario(
            lote_animal_id=animal.id,
            tipo=request.form.get('tipo'),
            descripcion=desc,
            costo_servicio=costo_float,
            fecha=fecha_evento,
            imagen_url=imagen_url
        )
        db.session.add(evt)
        animal.costo_acumulado += costo_float
        db.session.commit()
        flash('Evento clínico/sanitario registrado con éxito.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error registrando evento de salud: {e}', 'danger')
        
    return redirect(url_for('pecuario.ver_animal', id=animal_id))


@pecuario_bp.route('/animal/alimentar', methods=['POST'])
@login_required
def registrar_consumo_animal():
    animal_id = request.form.get('animal_id')
    try:
        animal = get_or_404_empresa(LoteAnimal, animal_id)
        insumo = get_or_404_empresa(Insumo, request.form.get('insumo_id'))
        cantidad = safe_float(request.form.get('cantidad'), 0.0)
        
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
        
    return redirect(url_for('pecuario.ver_animal', id=animal_id))


@pecuario_bp.route('/animal/registrar_baja', methods=['POST'])
@login_required
def registrar_baja_animal():
    animal_id = request.form.get('animal_id')
    try:
        animal = get_or_404_empresa(LoteAnimal, animal_id)
        cantidad_baja = safe_int(request.form.get('cantidad_baja'), 1)
        motivo = request.form.get('motivo', 'Enfermedad')
        observaciones = request.form.get('observaciones', '').strip()
        fecha_str = request.form.get('fecha')
        fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d').date() if fecha_str else datetime.now(timezone.utc).date()
        
        if cantidad_baja <= 0:
            flash('La cantidad debe ser al menos 1.', 'warning')
            return redirect(url_for('pecuario.ver_animal', id=animal.id))
            
        if cantidad_baja > animal.cantidad_actual:
            flash(f'No puedes dar de baja {cantidad_baja}. Animales activos: {animal.cantidad_actual}', 'danger')
            return redirect(url_for('pecuario.ver_animal', id=animal.id))
            
        animal.cantidad_actual -= cantidad_baja
        if animal.cantidad_actual <= 0:
            animal.estado = 'Muerto'
            
        evento = EventoSanitario(
            lote_animal_id=animal.id,
            tipo='Mortalidad / Baja',
            descripcion=f"Baja de {cantidad_baja} animal(es) por {motivo}. {observaciones}".strip(),
            costo_servicio=0.0,
            fecha=fecha_obj
        )
        db.session.add(evento)
        db.session.commit()
        
        registrar_auditoria('ELIMINAR', 'Pecuario', f"Baja de {cantidad_baja} animales en lote {animal.codigo} ({motivo})")
        flash(f'Baja registrada: {cantidad_baja} animal(es) por {motivo}.', 'warning')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error registrando baja animal: {e}")
        flash(f'Error al registrar baja: {e}', 'danger')
        
    return redirect(url_for('pecuario.ver_animal', id=animal_id))

