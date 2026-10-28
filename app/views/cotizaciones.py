import logging
from datetime import datetime, timezone, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, Response
from flask_login import login_required, current_user
from ..extensions import db
from ..models import (
    Cotizacion, DetalleCotizacion, Cliente, Venta, DetalleVenta,
    LoteProduccion, Insumo, LoteAnimal
)
from .helpers import (
    filtrar_por_empresa, asignar_empresa, get_or_404_empresa,
    empresa_id_actual, obtener_empresa_activa
)
from ..services.pdf_generator import generar_pdf_cotizacion

logger = logging.getLogger(__name__)

cotizaciones_bp = Blueprint('cotizaciones', __name__, url_prefix='/cotizaciones')


@cotizaciones_bp.route('/')
@login_required
def index():
    """Listado general de cotizaciones y proformas con métricas de conversión."""
    estado_filtro = request.args.get('estado', '').strip()
    cliente_id = request.args.get('cliente_id', type=int)
    q = request.args.get('q', '').strip()

    query = filtrar_por_empresa(Cotizacion.query, Cotizacion)

    if estado_filtro and estado_filtro != 'Todas':
        query = query.filter(Cotizacion.estado == estado_filtro)
    if cliente_id:
        query = query.filter(Cotizacion.cliente_id == cliente_id)
    if q:
        query = query.join(Cliente, Cotizacion.cliente_id == Cliente.id, isouter=True).filter(
            db.or_(
                Cotizacion.numero_cotizacion.ilike(f'%{q}%'),
                Cliente.nombre.ilike(f'%{q}%'),
                Cliente.documento.ilike(f'%{q}%')
            )
        )

    cotizaciones = query.order_by(Cotizacion.fecha_creacion.desc()).all()

    # Métricas y KPIs
    todas_empresa = filtrar_por_empresa(Cotizacion.query, Cotizacion).all()
    total_cotizado = sum(c.total or 0 for c in todas_empresa)
    activas_count = sum(1 for c in todas_empresa if c.estado in ['Borrador', 'Enviada'])
    aprobadas_count = sum(1 for c in todas_empresa if c.estado in ['Aprobada', 'Convertida'])
    convertidas_count = sum(1 for c in todas_empresa if c.estado == 'Convertida')
    tasa_conversion = (convertidas_count / len(todas_empresa) * 100) if todas_empresa else 0.0

    clientes = filtrar_por_empresa(Cliente.query, Cliente).order_by(Cliente.nombre).all()

    return render_template(
        'cotizaciones/index.html',
        cotizaciones=cotizaciones,
        clientes=clientes,
        total_cotizado=total_cotizado,
        activas_count=activas_count,
        aprobadas_count=aprobadas_count,
        convertidas_count=convertidas_count,
        tasa_conversion=tasa_conversion,
        estado_filtro=estado_filtro,
        cliente_id=cliente_id,
        q=q
    )


@cotizaciones_bp.route('/nueva', methods=['GET', 'POST'])
@login_required
def nueva_cotizacion():
    """Crea una nueva cotización comercial."""
    if request.method == 'POST':
        try:
            cliente_id = request.form.get('cliente_id', type=int)
            validez_dias = request.form.get('validez_dias', 15, type=int)
            observaciones = request.form.get('observaciones', '').strip()
            
            eid = empresa_id_actual()
            consecutivo_num = Cotizacion.query.filter_by(empresa_id=eid).count() + 1
            num_cot = f"COT-{consecutivo_num:04d}"

            ahora = datetime.now(timezone.utc)
            fecha_vence = (ahora + timedelta(days=max(1, validez_dias))).date()

            cot = Cotizacion(
                numero_cotizacion=num_cot,
                cliente_id=cliente_id,
                usuario_id=current_user.id,
                fecha_creacion=ahora,
                fecha_vencimiento=fecha_vence,
                estado='Borrador',
                observaciones=observaciones or "Precios válidos por el tiempo estipulado. Sujeto a disponibilidad de inventario."
            )
            asignar_empresa(cot)
            db.session.add(cot)
            db.session.commit()

            flash(f"Cotización #{cot.numero_cotizacion} iniciada con éxito. Agrega los productos a cotizar.", "success")
            return redirect(url_for('cotizaciones.ver_cotizacion', cotizacion_id=cot.id))

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creando cotización: {e}")
            flash(f"Error al crear cotización: {str(e)}", "danger")
            return redirect(url_for('cotizaciones.index'))

    clientes = filtrar_por_empresa(Cliente.query, Cliente).order_by(Cliente.nombre).all()
    return render_template('cotizaciones/nueva.html', clientes=clientes)


@cotizaciones_bp.route('/<int:cotizacion_id>')
@login_required
def ver_cotizacion(cotizacion_id):
    """Vista detallada e interactiva de la cotización para agregar productos o convertir."""
    cotizacion = get_or_404_empresa(Cotizacion, cotizacion_id)
    clientes = filtrar_por_empresa(Cliente.query, Cliente).order_by(Cliente.nombre).all()
    
    # Catálogos para el selector rápido de productos
    lotes_disponibles = filtrar_por_empresa(LoteProduccion.query, LoteProduccion).filter(
        LoteProduccion.estado.in_(['En Crecimiento', 'Listo para Venta', 'Cosechado']),
        LoteProduccion.cantidad_actual > 0
    ).all()
    
    insumos_disponibles = filtrar_por_empresa(Insumo.query, Insumo).filter(
        Insumo.cantidad_actual > 0
    ).all()

    animales_disponibles = filtrar_por_empresa(LoteAnimal.query, LoteAnimal).filter(
        LoteAnimal.cantidad_actual > 0
    ).all()

    return render_template(
        'cotizaciones/ver.html',
        cotizacion=cotizacion,
        clientes=clientes,
        lotes_disponibles=lotes_disponibles,
        insumos_disponibles=insumos_disponibles,
        animales_disponibles=animales_disponibles
    )


@cotizaciones_bp.route('/<int:cotizacion_id>/agregar-item', methods=['POST'])
@login_required
def agregar_item(cotizacion_id):
    """Agrega un producto o servicio a la cotización."""
    cotizacion = get_or_404_empresa(Cotizacion, cotizacion_id)
    
    if cotizacion.estado in ['Convertida']:
        flash("No se pueden agregar ítems a una cotización que ya fue convertida a venta.", "warning")
        return redirect(url_for('cotizaciones.ver_cotizacion', cotizacion_id=cotizacion.id))

    try:
        tipo_item = request.form.get('tipo_item')
        item_id = request.form.get('item_id', type=int)
        cantidad = float(request.form.get('cantidad', 1))
        precio_unitario = float(request.form.get('precio_unitario', 0))
        descuento_pct = float(request.form.get('descuento_pct', 0))

        if cantidad <= 0:
            flash("La cantidad debe ser mayor a 0.", "danger")
            return redirect(url_for('cotizaciones.ver_cotizacion', cotizacion_id=cotizacion.id))

        descripcion = ""
        lote_id = None
        insumo_id = None
        animal_id = None

        if tipo_item == 'lote' and item_id:
            lote = get_or_404_empresa(LoteProduccion, item_id)
            lote_id = lote.id
            nom = lote.especie.nombre_comun if lote.especie else lote.codigo_lote
            descripcion = f"{nom} (Lote: {lote.codigo_lote})"
            if precio_unitario <= 0:
                precio_unitario = lote.especie.precio_venta_sugerido if (lote.especie and lote.especie.precio_venta_sugerido) else (lote.costo_unitario * 1.5 if lote.costo_unitario else 5000.0)

        elif tipo_item == 'insumo' and item_id:
            insumo = get_or_404_empresa(Insumo, item_id)
            insumo_id = insumo.id
            descripcion = f"{insumo.nombre}"
            if precio_unitario <= 0:
                precio_unitario = insumo.precio_venta or 0.0

        elif tipo_item == 'animal' and item_id:
            animal = get_or_404_empresa(LoteAnimal, item_id)
            animal_id = animal.id
            descripcion = f"Pecuario: {animal.nombre or animal.codigo} ({animal.especie or 'Ganado'})"
            if precio_unitario <= 0:
                precio_unitario = animal.raza_rel.valor_mercado_estimado if (animal.raza_rel and animal.raza_rel.valor_mercado_estimado) else 150000.0

        else:
            descripcion = request.form.get('descripcion_personalizada', '').strip() or "Servicio / Producto Forestal"

        # Cálculo de subtotal
        factor_desc = 1.0 - (descuento_pct / 100.0)
        subtotal = round(cantidad * precio_unitario * factor_desc, 2)

        detalle = DetalleCotizacion(
            cotizacion=cotizacion,
            cotizacion_id=cotizacion.id,
            lote_id=lote_id,
            insumo_id=insumo_id,
            animal_id=animal_id,
            descripcion=descripcion,
            cantidad=cantidad,
            precio_unitario=precio_unitario,
            descuento_pct=descuento_pct,
            subtotal=subtotal
        )
        db.session.add(detalle)
        db.session.flush()

        # Recalcular totales de la cotización
        _recalcular_cotizacion(cotizacion)
        db.session.commit()

        flash(f"Ítem '{descripcion}' agregado a la cotización.", "success")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error agregando ítem a cotización #{cotizacion_id}: {e}")
        flash(f"Error al agregar ítem: {str(e)}", "danger")

    return redirect(url_for('cotizaciones.ver_cotizacion', cotizacion_id=cotizacion.id))


@cotizaciones_bp.route('/<int:cotizacion_id>/eliminar-item/<int:item_id>', methods=['POST'])
@login_required
def eliminar_item(cotizacion_id, item_id):
    """Elimina un ítem de la cotización."""
    cotizacion = get_or_404_empresa(Cotizacion, cotizacion_id)
    detalle = DetalleCotizacion.query.filter_by(id=item_id, cotizacion_id=cotizacion.id).first_or_404()
    
    try:
        db.session.delete(detalle)
        db.session.flush()
        _recalcular_cotizacion(cotizacion)
        db.session.commit()
        flash("Ítem removido de la cotización.", "info")
    except Exception as e:
        db.session.rollback()
        flash(f"Error eliminando ítem: {str(e)}", "danger")

    return redirect(url_for('cotizaciones.ver_cotizacion', cotizacion_id=cotizacion.id))


@cotizaciones_bp.route('/<int:cotizacion_id>/cambiar-estado', methods=['POST'])
@login_required
def cambiar_estado(cotizacion_id):
    """Actualiza el estado comercial de la cotización."""
    cotizacion = get_or_404_empresa(Cotizacion, cotizacion_id)
    nuevo_estado = request.form.get('estado')
    if nuevo_estado in ['Borrador', 'Enviada', 'Aprobada', 'Rechazada']:
        cotizacion.estado = nuevo_estado
        db.session.commit()
        flash(f"Estado de cotización #{cotizacion.numero_cotizacion} actualizado a '{nuevo_estado}'.", "success")
    return redirect(url_for('cotizaciones.ver_cotizacion', cotizacion_id=cotizacion.id))


@cotizaciones_bp.route('/<int:cotizacion_id>/convertir-venta', methods=['POST'])
@login_required
def convertir_en_venta(cotizacion_id):
    """
    Convierte la cotización en una Venta POS en 1 clic:
    Copia todos los productos, crea la venta en borrador/finalizable,
    actualiza la cotización a 'Convertida' y redirige a la vista de venta.
    """
    cotizacion = get_or_404_empresa(Cotizacion, cotizacion_id)

    if not cotizacion.detalles:
        flash("No puedes convertir una cotización vacía sin productos.", "warning")
        return redirect(url_for('cotizaciones.ver_cotizacion', cotizacion_id=cotizacion.id))

    if cotizacion.estado == 'Convertida' and cotizacion.venta_id:
        flash(f"Esta cotización ya fue convertida previamente a la Venta #{cotizacion.venta_asociada.numero_factura if cotizacion.venta_asociada else cotizacion.venta_id}.", "info")
        return redirect(url_for('ventas.ver_venta', venta_id=cotizacion.venta_id))

    try:
        # 1. Asegurar cliente
        cliente_id = cotizacion.cliente_id
        if not cliente_id:
            cli = filtrar_por_empresa(Cliente.query, Cliente).first()
            cliente_id = cli.id if cli else None

        # 2. Generar nueva Venta
        consecutivo_factura = f"FAC-{int(datetime.now().timestamp())}"
        nueva_venta = Venta(
            numero_factura=consecutivo_factura,
            cliente_id=cliente_id,
            usuario_id=current_user.id,
            estado='Borrador',
            subtotal=cotizacion.subtotal,
            descuento=cotizacion.descuento,
            impuestos=cotizacion.impuestos,
            total=cotizacion.total,
            observaciones=f"Generada a partir de Cotización #{cotizacion.numero_cotizacion}"
        )
        asignar_empresa(nueva_venta)
        db.session.add(nueva_venta)
        db.session.flush()

        # 3. Copiar detalles
        for item in cotizacion.detalles:
            costo_unit = 0.0
            if item.lote_id and item.lote:
                costo_unit = item.lote.costo_unitario or 0.0
            elif item.insumo_id and item.insumo:
                costo_unit = item.insumo.costo_promedio or 0.0
            elif item.animal_id and item.animal:
                costo_unit = (item.animal.costo_acumulado / item.animal.cantidad_actual) if item.animal.cantidad_actual else 0.0

            det_v = DetalleVenta(
                venta_id=nueva_venta.id,
                lote_id=item.lote_id,
                insumo_id=item.insumo_id,
                animal_id=item.animal_id,
                cantidad=item.cantidad,
                precio_venta_unitario=item.precio_unitario,
                costo_produccion_unitario=costo_unit,
                descuento_pct=item.descuento_pct or 0.0,
                iva_pct=item.iva_pct or 0.0,
                subtotal=item.subtotal,
                ganancia=item.subtotal - (item.cantidad * costo_unit)
            )
            db.session.add(det_v)

        # 4. Vincular cotización a la venta
        cotizacion.estado = 'Convertida'
        cotizacion.venta_id = nueva_venta.id
        db.session.commit()

        flash(f"¡Excelente! Cotización #{cotizacion.numero_cotizacion} convertida con éxito en la Venta #{nueva_venta.numero_factura}. Puedes finalizar el cobro ahora.", "success")
        return redirect(url_for('ventas.ver_venta', venta_id=nueva_venta.id))

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error convirtiendo cotización #{cotizacion_id} a venta: {e}")
        flash(f"Error convirtiendo cotización a venta: {str(e)}", "danger")
        return redirect(url_for('cotizaciones.ver_cotizacion', cotizacion_id=cotizacion.id))


@cotizaciones_bp.route('/<int:cotizacion_id>/pdf')
@login_required
def descargar_pdf(cotizacion_id):
    """Genera y descarga en streaming el PDF oficial de la cotización."""
    cotizacion = get_or_404_empresa(Cotizacion, cotizacion_id)
    try:
        pdf_bytes = generar_pdf_cotizacion(cotizacion)
        filename = f"Cotizacion_{cotizacion.numero_cotizacion}.pdf"
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={'Content-Disposition': f'inline; filename="{filename}"'}
        )
    except Exception as e:
        logger.error(f"Error generando PDF de cotización #{cotizacion_id}: {e}")
        flash(f"Error al generar documento PDF: {str(e)}", "danger")
        return redirect(url_for('cotizaciones.ver_cotizacion', cotizacion_id=cotizacion.id))


@cotizaciones_bp.route('/<int:cotizacion_id>/whatsapp-url')
@login_required
def whatsapp_url(cotizacion_id):
    """Genera un deep link enriquecido de WhatsApp para enviar la propuesta al cliente."""
    cotizacion = get_or_404_empresa(Cotizacion, cotizacion_id)
    empresa = obtener_empresa_activa()
    cliente = cotizacion.cliente
    
    telefono = ""
    nombre_cli = "Estimado cliente"
    if cliente:
        telefono = (cliente.telefono or "").replace(" ", "").replace("+", "").replace("-", "")
        nombre_cli = cliente.nombre or "Estimado cliente"
    
    if telefono.startswith("3") and len(telefono) == 10:
        telefono = f"57{telefono}"

    nombre_empresa = empresa.nombre if empresa else "EcoSistem"
    vence_str = cotizacion.fecha_vencimiento.strftime('%d/%m/%Y') if cotizacion.fecha_vencimiento else "15 días"
    
    lineas = [
        f"🌿 *¡Hola {nombre_cli}!*",
        f"Te saludamos de *{nombre_empresa}*. Te compartimos la propuesta económica solicitada:",
        f"📄 *Cotización:* #{cotizacion.numero_cotizacion}",
        f"💰 *Total Propuesta:* ${cotizacion.total:,.0f} COP",
        f"⏳ *Validez de la oferta:* Hasta {vence_str}",
        "",
        "Quedamos a tu entera disposición para resolver cualquier duda o proceder con tu pedido. ¡Gracias por confiar en nosotros!"
    ]
    mensaje = "%0A".join(lineas)
    wa_link = f"https://api.whatsapp.com/send?phone={telefono}&text={mensaje}" if telefono else f"https://api.whatsapp.com/send?text={mensaje}"

    return jsonify({'success': True, 'whatsapp_url': wa_link})


def _recalcular_cotizacion(cotizacion):
    """Recalcula subtotal, descuentos, impuestos y total de la cotización."""
    subtotal_base = sum(d.cantidad * d.precio_unitario for d in cotizacion.detalles)
    descuentos = sum((d.cantidad * d.precio_unitario * (d.descuento_pct / 100.0)) for d in cotizacion.detalles if d.descuento_pct)
    cotizacion.subtotal = round(subtotal_base, 2)
    cotizacion.descuento = round(descuentos, 2)
    cotizacion.total = round(max(0.0, subtotal_base - descuentos + (cotizacion.impuestos or 0.0)), 2)
