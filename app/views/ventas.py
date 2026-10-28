"""
Módulo de Ventas (POS) — Facturas, ítems, clientes, búsqueda
"""
import logging
from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, Response
from flask_login import login_required, current_user
from sqlalchemy import or_
from ..models import (
    Cliente, Venta, DetalleVenta, LoteProduccion, Especie,
    Insumo, MovimientoInventario, LoteAnimal, RazaAnimal,
    CajaTurno, MovimientoCaja, AbonoVenta
)
from ..extensions import db
from .helpers import consumir_stock_fifo, safe_float, safe_int, solo_admin, registrar_auditoria, filtrar_por_empresa, asignar_empresa, get_or_404_empresa
from ..services.pdf_generator import generar_pdf_factura
from ..services.facturacion_electronica import FacturacionElectronicaService
from ..services.pasarela_pagos import PasarelaPagosService
from ..services.notificaciones import NotificacionesService

logger = logging.getLogger(__name__)
ventas_bp = Blueprint('ventas', __name__)


@ventas_bp.route('/clientes')
@login_required
def lista_clientes():
    q = request.args.get('q', '').strip()
    ajax = request.args.get('ajax') == '1'
    query = filtrar_por_empresa(Cliente.query, Cliente)
    if q:
        query = query.filter(or_(
            Cliente.nombre.ilike(f'%{q}%'),
            Cliente.documento.ilike(f'%{q}%'),
            Cliente.email.ilike(f'%{q}%')
        ))
    clientes = query.order_by(Cliente.nombre).all()
    if ajax:
        return render_template('parciales/items_clientes.html', clientes=clientes)
    return render_template('ventas/lista_clientes.html', clientes=clientes, search_query=q)


@ventas_bp.route('/cliente/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo_cliente():
    if request.method == 'POST':
        try:
            c = Cliente(
                nombre=request.form.get('nombre'),
                documento=request.form.get('documento'),
                telefono=request.form.get('telefono'),
                email=request.form.get('email'),
                direccion=request.form.get('direccion')
            )
            asignar_empresa(c)
            db.session.add(c)
            db.session.commit()
            flash('Cliente creado.', 'success')
            return redirect(url_for('ventas.lista_clientes'))
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error creando cliente: {e}')
            flash(f'Error: {e}', 'danger')
            
    return render_template('ventas/nuevo_cliente.html')


@ventas_bp.route('/cliente/rapido', methods=['POST'])
@login_required
def cliente_rapido():
    """Creación instantánea de cliente desde el POS sin salir de la venta (Estilo OPTICAL)."""
    data = request.get_json(silent=True) or request.form
    nombre = (data.get('nombre') or '').strip()
    if not nombre:
        return jsonify({'success': False, 'message': 'El nombre del cliente es obligatorio.'}), 400
        
    documento = (data.get('documento') or '').strip()
    telefono = (data.get('telefono') or '').strip()
    email = (data.get('email') or '').strip()
    direccion = (data.get('direccion') or '').strip()
    
    if documento:
        existente = filtrar_por_empresa(Cliente.query, Cliente).filter_by(documento=documento).first()
        if existente:
            return jsonify({
                'success': True,
                'cliente': {
                    'id': existente.id,
                    'nombre': existente.nombre,
                    'documento': existente.documento or '',
                    'telefono': existente.telefono or ''
                },
                'mensaje': 'Cliente existente encontrado y asociado.'
            })
            
    try:
        nuevo = Cliente(
            nombre=nombre,
            documento=documento,
            telefono=telefono,
            email=email,
            direccion=direccion
        )
        asignar_empresa(nuevo)
        db.session.add(nuevo)
        db.session.commit()
        return jsonify({
            'success': True,
            'cliente': {
                'id': nuevo.id,
                'nombre': nuevo.nombre,
                'documento': nuevo.documento or '',
                'telefono': nuevo.telefono or ''
            },
            'mensaje': 'Cliente registrado con éxito.'
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error en cliente_rapido: {e}')
        return jsonify({'success': False, 'message': str(e)}), 500



@ventas_bp.route('/ventas')
@login_required
def lista_ventas():
    q = request.args.get('q', '').strip()
    estado = request.args.get('estado')
    filtro = request.args.get('filtro')
    
    base_query = filtrar_por_empresa(Venta.query, Venta)
    
    # KPIs globales sobre todas las ventas de la empresa
    todas_ventas = base_query.all()
    kpi_facturacion_total = sum(v.total or 0 for v in todas_ventas if v.estado == 'Finalizada')
    kpi_total_transacciones = len(todas_ventas)
    kpi_finalizadas = sum(1 for v in todas_ventas if v.estado == 'Finalizada')
    kpi_borradores = sum(1 for v in todas_ventas if v.estado == 'Borrador')
    kpi_ticket_promedio = (kpi_facturacion_total / kpi_finalizadas) if kpi_finalizadas > 0 else 0
    
    query = base_query
    if q:
        query = query.join(Cliente).filter(or_(
            Venta.numero_factura.ilike(f'%{q}%'),
            Cliente.nombre.ilike(f'%{q}%'),
            Cliente.documento.ilike(f'%{q}%')
        ))
    if estado:
        query = query.filter(Venta.estado == estado)
    if filtro == 'mes':
        today = datetime.now(timezone.utc)
        query = query.filter(
            db.extract('month', Venta.fecha) == today.month,
            db.extract('year', Venta.fecha) == today.year
        )
    elif filtro == 'hoy':
        today = datetime.now(timezone.utc).date()
        query = query.filter(db.func.date(Venta.fecha) == today)
        
    ventas = query.order_by(Venta.fecha.desc()).all()
    
    return render_template('ventas/lista_ventas.html', 
                           ventas=ventas,
                           search_query=q,
                           filtro_estado=estado,
                           filtro_tiempo=filtro,
                           kpi_facturacion_total=kpi_facturacion_total,
                           kpi_total_transacciones=kpi_total_transacciones,
                           kpi_finalizadas=kpi_finalizadas,
                           kpi_borradores=kpi_borradores,
                           kpi_ticket_promedio=kpi_ticket_promedio)


@ventas_bp.route('/venta/nueva', methods=['GET', 'POST'])
@login_required
def nueva_venta():
    borradores = filtrar_por_empresa(Venta.query, Venta).filter_by(estado='Borrador').all()
    for b in borradores:
        if not b.detalles: return redirect(url_for('ventas.ver_venta', venta_id=b.id))
        
    try:
        cli = filtrar_por_empresa(Cliente.query, Cliente).first()
        if not cli:
            cli = Cliente(nombre='Mostrador')
            asignar_empresa(cli)
            db.session.add(cli)
            db.session.commit()
            
        v = Venta(
            numero_factura=f"FAC-{int(datetime.now().timestamp())}", 
            cliente_id=cli.id, 
            usuario_id=current_user.id, 
            estado='Borrador'
        )
        asignar_empresa(v)
        db.session.add(v)
        db.session.commit()
        return redirect(url_for('ventas.ver_venta', venta_id=v.id))
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {e}', 'danger')
        return redirect(url_for('ventas.lista_ventas'))


@ventas_bp.route('/venta/<int:venta_id>')
@login_required
def ver_venta(venta_id):
    venta = get_or_404_empresa(Venta, venta_id)
    clientes = filtrar_por_empresa(Cliente.query, Cliente).order_by(Cliente.nombre).all()
    caja_activa = CajaTurno.query.filter_by(
        empresa_id=venta.empresa_id,
        estado='Abierta'
    ).order_by(CajaTurno.id.desc()).first()
    
    return render_template('ventas/ver_venta.html', 
                           venta=venta, 
                           clientes=clientes,
                           caja_activa=caja_activa)


@ventas_bp.route('/venta/<int:venta_id>/cambiar_cliente', methods=['POST'])
@login_required
def cambiar_cliente_venta(venta_id):
    venta = get_or_404_empresa(Venta, venta_id)
    try:
        data = request.get_json(silent=True) or request.form
        nuevo_cli_id = int(data.get('cliente_id'))
        cli = get_or_404_empresa(Cliente, nuevo_cli_id)
        venta.cliente_id = cli.id
        db.session.commit()
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'cliente': {'id': cli.id, 'nombre': cli.nombre, 'documento': cli.documento or ''}})
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error cambiando cliente de venta: {e}')
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': str(e)}), 400
    return redirect(url_for('ventas.ver_venta', venta_id=venta_id))


@ventas_bp.route('/cliente/<int:cliente_id>/completar_fe', methods=['POST'])
@login_required
def completar_datos_fe(cliente_id):
    cli = get_or_404_empresa(Cliente, cliente_id)
    data = request.get_json(silent=True) or request.form
    try:
        cli.tipo_documento = (data.get('tipo_documento') or cli.tipo_documento or 'CC').strip()
        cli.documento = (data.get('documento') or cli.documento or '').strip()
        cli.email = (data.get('email') or cli.email or '').strip()
        cli.telefono = (data.get('telefono') or cli.telefono or '').strip()
        cli.direccion = (data.get('direccion') or cli.direccion or '').strip()
        cli.ciudad = (data.get('ciudad') or cli.ciudad or '').strip()
        db.session.commit()
        return jsonify({'success': True, 'message': 'Datos de Facturación Electrónica guardados.'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400


@ventas_bp.route('/venta/<int:venta_id>/agregar', methods=['POST'])
@login_required
def agregar_item_venta(venta_id):
    venta = get_or_404_empresa(Venta, venta_id)
    is_ajax = request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    try:
        data = request.get_json(silent=True) or request.form
        lote_id = data.get('lote_id')
        insumo_id = data.get('insumo_id')
        animal_id = data.get('animal_id')
        
        lote_id = int(lote_id) if lote_id else None
        insumo_id = int(insumo_id) if insumo_id else None
        animal_id = int(animal_id) if animal_id else None
        
        cantidad = safe_float(data.get('cantidad'), 1.0)
        precio_venta = safe_float(data.get('precio_unitario'), 0.0)
        
        if data.get('es_caja') in ['on', True, 'true', '1']:
            cantidad *= safe_float(data.get('unidades_por_caja'), 1.0)
            
        existe = None
        if lote_id:
            existe = DetalleVenta.query.filter_by(venta_id=venta.id, lote_id=lote_id).first()
        elif insumo_id:
            existe = DetalleVenta.query.filter_by(venta_id=venta.id, insumo_id=insumo_id).first()
        elif animal_id:
            existe = DetalleVenta.query.filter_by(venta_id=venta.id, animal_id=animal_id).first()
            
        costo_unit = 0
        if lote_id: 
            obj = get_or_404_empresa(LoteProduccion, lote_id)
            if obj.cantidad_actual < cantidad:
                if is_ajax: return jsonify({'success': False, 'message': 'Stock insuficiente en el lote.'}), 400
                flash('Stock insuficiente.', 'warning')
                return redirect(url_for('ventas.ver_venta', venta_id=venta_id))
            costo_unit = obj.costo_total / obj.cantidad_actual if obj.cantidad_actual else 0
            if precio_venta <= 0:
                precio_venta = obj.especie.precio_venta_sugerido if obj.especie else 0
        elif insumo_id:
            obj = get_or_404_empresa(Insumo, insumo_id)
            if obj.cantidad_actual < cantidad:
                if is_ajax: return jsonify({'success': False, 'message': f'Stock insuficiente de {obj.nombre}.'}), 400
                flash(f'Stock insuficiente de {obj.nombre}.', 'warning')
                return redirect(url_for('ventas.ver_venta', venta_id=venta_id))
            costo_unit = obj.costo_promedio
            if precio_venta <= 0:
                precio_venta = obj.precio_venta or 0
        elif animal_id:
            obj = get_or_404_empresa(LoteAnimal, animal_id)
            if obj.cantidad_actual < cantidad:
                if is_ajax: return jsonify({'success': False, 'message': f'Disponibilidad insuficiente del animal ({obj.codigo}).'}), 400
                flash(f'Disponibilidad insuficiente del animal ({obj.codigo}).', 'warning')
                return redirect(url_for('ventas.ver_venta', venta_id=venta_id))
            costo_unit = obj.costo_acumulado / obj.cantidad_actual if obj.cantidad_actual else 0
            if precio_venta <= 0:
                precio_venta = obj.raza_rel.valor_mercado_estimado if obj.raza_rel and obj.raza_rel.valor_mercado_estimado else (costo_unit * 1.3 or 100000.0)
            
        if existe:
            existe.cantidad += cantidad
            if precio_venta > 0:
                existe.precio_venta_unitario = precio_venta
            desc_factor = 1.0 - ((existe.descuento_pct or 0.0) / 100.0)
            base = existe.cantidad * existe.precio_venta_unitario * desc_factor
            iva_val = base * ((existe.iva_pct or 0.0) / 100.0)
            existe.subtotal = base + iva_val
            existe.ganancia = base - (existe.cantidad * (existe.costo_produccion_unitario or 0))
            det = existe
        else:
            base = cantidad * precio_venta
            det = DetalleVenta(
                venta_id=venta.id,
                lote_id=lote_id,
                insumo_id=insumo_id,
                animal_id=animal_id,
                cantidad=cantidad,
                precio_venta_unitario=precio_venta,
                costo_produccion_unitario=costo_unit,
                descuento_pct=0.0,
                iva_pct=0.0,
                subtotal=base,
                ganancia=base - (cantidad * costo_unit)
            )
            db.session.add(det)
            
        db.session.flush()
        venta.subtotal = sum((d.cantidad * d.precio_venta_unitario) for d in venta.detalles)
        venta.total = sum(d.subtotal for d in venta.detalles)
        db.session.commit()
        
        if is_ajax:
            item_nombre = "Item"
            if det.lote_origen:
                item_nombre = det.lote_origen.especie.nombre_comun if det.lote_origen.especie else det.lote_origen.codigo_lote
            elif det.animal:
                item_nombre = f"Animal: {det.animal.nombre or det.animal.codigo}"
            elif det.insumo:
                item_nombre = det.insumo.nombre

            return jsonify({
                'success': True,
                'item_id': det.id,
                'nombre': item_nombre,
                'cantidad': det.cantidad,
                'precio': det.precio_venta_unitario,
                'subtotal': det.subtotal,
                'total_venta': venta.total,
                'total_items': len(venta.detalles)
            })
    except Exception as e:
        db.session.rollback()
        if is_ajax:
            return jsonify({'success': False, 'message': str(e)}), 400
        flash(str(e), 'danger')
        
    return redirect(url_for('ventas.ver_venta', venta_id=venta.id))


@ventas_bp.route('/venta/<int:venta_id>/finalizar', methods=['POST'])
@login_required
def finalizar_venta(venta_id):
    venta = get_or_404_empresa(Venta, venta_id)
    is_ajax = request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    data = request.get_json(silent=True) or request.form
    
    if venta.estado not in ['Borrador', 'Pedido Web']:
        if is_ajax:
            return jsonify({'success': False, 'message': 'La venta ya no es un borrador o pedido editable.'}), 400
        flash('La venta ya no es un borrador o pedido editable.', 'warning')
        return redirect(url_for('ventas.ver_venta', venta_id=venta.id))

    if not venta.detalles:
        if is_ajax:
            return jsonify({'success': False, 'message': 'El carrito está vacío.'}), 400
        flash('El carrito está vacío.', 'warning')
        return redirect(url_for('ventas.ver_venta', venta_id=venta.id))

    # Actualizar cliente si se envió
    cliente_id = data.get('cliente_id')
    if cliente_id:
        try:
            cli_sel = get_or_404_empresa(Cliente, int(cliente_id))
            venta.cliente_id = cli_sel.id
        except Exception:
            pass

    # Validación de Facturación Electrónica (DIAN / Agro)
    requiere_fe = data.get('requiere_fe') in ['on', True, 'true', '1']
    if requiere_fe:
        cliente = venta.cliente
        if not cliente or cliente.nombre in ['Mostrador', 'Consumidor Final', '']:
            return jsonify({'success': False, 'message': 'Debe seleccionar un cliente registrado para emitir Factura Electrónica.'}), 400
            
        faltantes = []
        if not cliente.documento or not cliente.documento.strip():
            faltantes.append('Documento / NIT')
        if not cliente.email or not cliente.email.strip():
            faltantes.append('Correo Electrónico')
        if not cliente.direccion or not cliente.direccion.strip():
            faltantes.append('Dirección')
        if not cliente.ciudad or not cliente.ciudad.strip():
            faltantes.append('Ciudad')
            
        if faltantes:
            return jsonify({
                'success': False,
                'requiere_completar_fe': True,
                'cliente': {
                    'id': cliente.id,
                    'nombre': cliente.nombre,
                    'tipo_documento': cliente.tipo_documento or 'CC',
                    'documento': cliente.documento or '',
                    'email': cliente.email or '',
                    'telefono': cliente.telefono or '',
                    'direccion': cliente.direccion or '',
                    'ciudad': cliente.ciudad or ''
                },
                'faltantes': faltantes,
                'message': f'Faltan datos requeridos para Factura Electrónica: {", ".join(faltantes)}'
            })

    try:
        # Descontar stock
        for d in venta.detalles:
            if d.lote_id:
                lote = LoteProduccion.query.with_for_update().get(d.lote_id)
                if lote.cantidad_actual < d.cantidad:
                    raise Exception(f"Sin stock en el lote productivo ({lote.codigo_lote}).")
                lote.cantidad_actual -= d.cantidad
                lote.costo_total -= (d.cantidad * d.costo_produccion_unitario)
                if lote.cantidad_actual <= 0:
                    lote.estado = 'Finalizado'
            elif d.animal_id:
                animal = LoteAnimal.query.with_for_update().get(d.animal_id)
                if animal.cantidad_actual < d.cantidad:
                    raise Exception(f"Sin stock en lote/animal pecuario ({animal.codigo}).")
                animal.cantidad_actual -= int(d.cantidad)
                if animal.cantidad_actual <= 0:
                    animal.estado = 'Vendido'
            elif d.insumo_id:
                insumo = Insumo.query.with_for_update().get(d.insumo_id)
                costo_tot, costo_unit = consumir_stock_fifo(insumo, d.cantidad)
                d.costo_produccion_unitario = costo_unit
                d.ganancia = d.subtotal - costo_tot
                db.session.add(MovimientoInventario(
                    tipo_movimiento='Venta', 
                    cantidad=d.cantidad, 
                    costo_unitario=costo_unit, 
                    referencia=f"Factura #{venta.numero_factura}", 
                    insumo_id=d.insumo_id
                ))

        # Descuentos globales e Impuestos
        desc_global = safe_float(data.get('descuento_global'), 0.0)
        tipo_desc = data.get('tipo_descuento', 'monto') # 'monto' o 'pct'
        
        subtotal_base = sum((d.cantidad * d.precio_venta_unitario) for d in venta.detalles)
        if tipo_desc == 'pct':
            desc_val = (subtotal_base * min(100.0, desc_global)) / 100.0
        else:
            desc_val = min(subtotal_base, desc_global)
            
        iva_total = sum((d.subtotal - (d.cantidad * d.precio_venta_unitario * (1.0 - (d.descuento_pct or 0.0)/100.0))) for d in venta.detalles)
        
        venta.subtotal = subtotal_base
        venta.descuento = desc_val
        venta.impuestos = max(0.0, iva_total)
        venta.total = max(0.0, (subtotal_base - desc_val) + venta.impuestos)
        venta.es_electronica = bool(requiere_fe)

        # Tipo de venta: Contado vs Crédito
        tipo_venta = data.get('tipo_venta', 'Contado')
        venta.tipo_venta = tipo_venta
        
        if tipo_venta == 'Credito':
            abono = safe_float(data.get('abono_inicial'), 0.0)
            vence_str = data.get('fecha_vencimiento')
            fv = None
            if vence_str:
                try: fv = datetime.strptime(vence_str, '%Y-%m-%d').date()
                except Exception: pass
            venta.abono = abono
            venta.saldo = max(0.0, venta.total - abono)
            venta.fecha_vencimiento = fv
            metodo_abono = data.get('metodo_pago_abono', 'Efectivo')
            venta.metodo_pago = f"Crédito (Abono {metodo_abono}: ${abono:,.0f} - Saldo: ${venta.saldo:,.0f})"
        else:
            metodo = (data.get('metodo_pago') or 'Efectivo').strip()
            if metodo == 'Mixto':
                m1 = data.get('metodo_mixto_1') or 'Efectivo'
                val1 = safe_float(data.get('monto_mixto_1'), 0)
                m2 = data.get('metodo_mixto_2') or 'Transferencia'
                val2 = safe_float(data.get('monto_mixto_2'), 0)
                venta.metodo_pago = f"Mixto ({m1}: ${val1:,.0f} + {m2}: ${val2:,.0f})"
            else:
                venta.metodo_pago = metodo

        # Vincular venta al turno de caja activo de la empresa (si existe)
        caja_activa = CajaTurno.query.filter_by(
            empresa_id=venta.empresa_id,
            estado='Abierta'
        ).order_by(CajaTurno.id.desc()).first()
        if caja_activa:
            venta.caja_turno_id = caja_activa.id

        venta.estado = 'Finalizada'

        # Registrar abono inicial en el historial de cartera si aplica
        if tipo_venta == 'Credito' and (venta.abono or 0) > 0:
            eid = venta.empresa_id
            consecutivo = AbonoVenta.query.filter_by(empresa_id=eid).count() + 1
            recibo_inicial = AbonoVenta(
                numero_recibo=f"RC-{consecutivo:04d}",
                venta_id=venta.id,
                cliente_id=venta.cliente_id,
                usuario_id=current_user.id,
                caja_turno_id=caja_activa.id if (caja_activa and data.get('metodo_pago_abono', 'Efectivo').lower() == 'efectivo') else None,
                monto=venta.abono,
                metodo_pago=data.get('metodo_pago_abono', 'Efectivo'),
                saldo_anterior=venta.total,
                saldo_nuevo=venta.saldo,
                notas="Abono inicial al momento de la venta a crédito"
            )
            asignar_empresa(recibo_inicial)
            db.session.add(recibo_inicial)

        db.session.commit()
        
        if is_ajax:
            return jsonify({
                'success': True,
                'numero_factura': venta.numero_factura,
                'total': venta.total,
                'metodo_pago': venta.metodo_pago,
                'ticket_url': url_for('ventas.imprimir_ticket_venta', venta_id=venta.id)
            })
            
        flash(f'Venta #{venta.numero_factura} finalizada con éxito.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error finalizando venta: {e}')
        if is_ajax:
            return jsonify({'success': False, 'message': str(e)}), 400
        flash(str(e), 'danger')
        
    return redirect(url_for('ventas.ver_venta', venta_id=venta.id))


@ventas_bp.route('/venta/<int:venta_id>/ticket')
@login_required
def imprimir_ticket_venta(venta_id):
    venta = get_or_404_empresa(Venta, venta_id)
    return render_template('ventas/ticket_pos.html', venta=venta, now=datetime.now(timezone.utc))


@ventas_bp.route('/venta/<int:venta_id>/factura-pdf')
@login_required
def descargar_factura_pdf(venta_id):
    venta = get_or_404_empresa(Venta, venta_id)
    try:
        pdf_bytes = generar_pdf_factura(venta)
        filename = f"Factura_{venta.numero_factura or venta.id}.pdf"
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'inline; filename="{filename}"'
            }
        )
    except Exception as e:
        logger.error(f"Error generando factura PDF para venta #{venta_id}: {e}")
        flash(f"Error generando factura comercial PDF: {str(e)}", "danger")
        return redirect(url_for('ventas.ver_venta', venta_id=venta.id))


@ventas_bp.route('/venta/<int:venta_id>/enviar-email', methods=['POST'])
@login_required
def enviar_factura_email_route(venta_id):
    """Envía la factura en PDF como archivo adjunto al correo del cliente."""
    venta = get_or_404_empresa(Venta, venta_id)
    is_ajax = request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    data = request.get_json(silent=True) or request.form
    email_dest = data.get('email') or (venta.cliente.email if venta.cliente else None)
    mensaje_extra = data.get('mensaje') or None

    resultado = NotificacionesService.enviar_factura_email(
        venta=venta,
        email_destino=email_dest,
        mensaje_extra=mensaje_extra
    )

    if resultado['success']:
        if is_ajax:
            return jsonify({'success': True, 'message': resultado['message'], 'modo': resultado.get('modo')})
        flash(resultado['message'], 'success')
    else:
        if is_ajax:
            return jsonify({'success': False, 'message': resultado['message']}), 400
        flash(resultado['message'], 'danger')

    return redirect(url_for('ventas.ver_venta', venta_id=venta.id))


@ventas_bp.route('/venta/<int:venta_id>/whatsapp-url')
@login_required
def obtener_whatsapp_factura(venta_id):
    """Retorna la URL enriquecida de WhatsApp para la factura."""
    venta = get_or_404_empresa(Venta, venta_id)
    url_wa = NotificacionesService.generar_url_whatsapp_factura(venta)
    return jsonify({'success': True, 'whatsapp_url': url_wa})


@ventas_bp.route('/pedidos-web/<int:pedido_id>/notificar-whatsapp')
@login_required
def notificar_pedido_whatsapp(pedido_id):
    """Retorna la URL de WhatsApp para notificar el estado actual del pedido web."""
    pedido = get_or_404_empresa(Venta, pedido_id)
    nuevo_estado = request.args.get('estado') or pedido.estado
    url_wa = NotificacionesService.generar_url_whatsapp_pedido(pedido, nuevo_estado=nuevo_estado)
    return jsonify({'success': True, 'whatsapp_url': url_wa})


@ventas_bp.route('/venta/item/actualizar/<int:detalle_id>', methods=['POST'])
@login_required
def actualizar_item_venta(detalle_id):
    det = get_or_404_empresa(DetalleVenta, detalle_id)
    is_ajax = request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    try:
        data = request.get_json(silent=True) or request.form
        delta = safe_float(data.get('delta'), 0.0)
        
        if delta != 0.0:
            nueva_cant = det.cantidad + delta
        elif 'cantidad' in data:
            nueva_cant = safe_float(data.get('cantidad'), 1.0)
        else:
            nueva_cant = det.cantidad
            
        if nueva_cant <= 0:
            vid = det.venta_id
            db.session.delete(det)
            db.session.flush()
            det.venta.subtotal = sum((d.cantidad * d.precio_venta_unitario) for d in det.venta.detalles)
            det.venta.total = sum(d.subtotal for d in det.venta.detalles)
            db.session.commit()
            if is_ajax:
                return jsonify({
                    'success': True, 
                    'action': 'deleted', 
                    'subtotal_venta': det.venta.subtotal,
                    'total_venta': det.venta.total,
                    'total_items': len(det.venta.detalles)
                })
            flash('Artículo removido del ticket.', 'info')
            return redirect(url_for('ventas.ver_venta', venta_id=vid))
            
        stock_disp = det.insumo.cantidad_actual if det.insumo else (det.lote_origen.cantidad_actual if det.lote_origen else (det.animal.cantidad_actual if det.animal else 9999))
        if nueva_cant > stock_disp:
            if is_ajax:
                return jsonify({'success': False, 'message': f'Stock insuficiente. Máximo disponible: {stock_disp}'}), 400
            flash('Stock insuficiente.', 'warning')
            return redirect(url_for('ventas.ver_venta', venta_id=det.venta_id))
            
        det.cantidad = nueva_cant
        
        # Descuento e IVA por línea
        if 'descuento_pct' in data:
            det.descuento_pct = max(0.0, min(100.0, safe_float(data.get('descuento_pct'), 0.0)))
        if 'iva_pct' in data:
            det.iva_pct = max(0.0, min(100.0, safe_float(data.get('iva_pct'), 0.0)))
            
        desc_factor = 1.0 - ((det.descuento_pct or 0.0) / 100.0)
        base = det.cantidad * det.precio_venta_unitario * desc_factor
        iva_val = base * ((det.iva_pct or 0.0) / 100.0)
        det.subtotal = base + iva_val
        det.ganancia = base - (det.cantidad * (det.costo_produccion_unitario or 0))
        
        db.session.flush()
        det.venta.subtotal = sum((d.cantidad * d.precio_venta_unitario) for d in det.venta.detalles)
        det.venta.total = sum(d.subtotal for d in det.venta.detalles)
        
        db.session.commit()
        if is_ajax:
            return jsonify({
                'success': True, 
                'action': 'updated',
                'cantidad': det.cantidad,
                'descuento_pct': det.descuento_pct,
                'iva_pct': det.iva_pct,
                'subtotal': det.subtotal,
                'subtotal_venta': det.venta.subtotal,
                'total_venta': det.venta.total,
                'total_items': len(det.venta.detalles)
            })
        flash('Actualizado.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error actualizando item venta: {e}')
        if is_ajax:
            return jsonify({'success': False, 'message': str(e)}), 400
        flash(f'Error: {e}', 'danger')
        
    return redirect(url_for('ventas.ver_venta', venta_id=det.venta_id))


@ventas_bp.route('/venta/item/eliminar/<int:detalle_id>', methods=['POST'])
@login_required
def eliminar_item_venta(detalle_id):
    det = get_or_404_empresa(DetalleVenta, detalle_id)
    vid = det.venta_id
    is_ajax = request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    try:
        if det.venta.estado != 'Borrador':
            raise Exception("No se pueden eliminar ítems de una venta finalizada o anulada.")
        venta = det.venta
        db.session.delete(det)
        db.session.flush()
        venta.subtotal = sum((d.cantidad * d.precio_venta_unitario) for d in venta.detalles)
        venta.total = sum(d.subtotal for d in venta.detalles)
        db.session.commit()
        registrar_auditoria('ELIMINAR', 'Ventas', f"Item eliminado de la venta {vid}")
        if is_ajax:
            return jsonify({
                'success': True,
                'action': 'deleted',
                'subtotal_venta': venta.subtotal,
                'total_venta': venta.total,
                'total_items': len(venta.detalles)
            })
        flash('Eliminado.', 'info')
    except Exception as e:
        db.session.rollback()
        if is_ajax:
            return jsonify({'success': False, 'message': str(e)}), 400
        flash(f'Error al eliminar: {str(e)}', 'danger')
        
    return redirect(url_for('ventas.ver_venta', venta_id=vid))


@ventas_bp.route('/venta/<int:venta_id>/descartar', methods=['POST'])
@login_required
def descartar_venta_borrador(venta_id):
    venta = get_or_404_empresa(Venta, venta_id)
    is_ajax = request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    try:
        if venta.estado != 'Borrador':
            raise Exception("Solo se pueden descartar ventas en estado Borrador.")
        for d in list(venta.detalles):
            db.session.delete(d)
        venta.estado = 'Anulada'
        db.session.commit()
        if is_ajax:
            return jsonify({'success': True, 'redirect_url': url_for('ventas.nueva_venta')})
        flash('Venta descartada.', 'secondary')
        return redirect(url_for('ventas.nueva_venta'))
    except Exception as e:
        db.session.rollback()
        if is_ajax:
            return jsonify({'success': False, 'message': str(e)}), 400
        flash(str(e), 'danger')
        return redirect(url_for('ventas.ver_venta', venta_id=venta_id))



@ventas_bp.route('/venta/<int:pedido_id>/cancelar', methods=['POST'])
@solo_admin
def cancelar_venta_ruta(pedido_id):
    try:
        venta = get_or_404_empresa(Venta, pedido_id)
        if venta.estado == 'Finalizada':
            flash('No puede anular una venta finalizada directamente. Se requiere reverso de inventario.', 'warning')
            return redirect(url_for('ventas.ver_venta', venta_id=pedido_id))
        venta.estado = 'Anulada'
        db.session.commit()
        registrar_auditoria('ELIMINAR', 'Ventas', f"Venta {venta.numero_factura} anulada")
        flash('Anulada.', 'secondary')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al cancelar: {str(e)}', 'danger')
        
    return redirect(url_for('ventas.lista_ventas'))


@ventas_bp.route('/api/ventas/buscar', methods=['GET'])
@login_required
def buscar_items_venta_api():
    q = request.args.get('q', '').strip()
    res = []
    
    if not q: return jsonify([])
    
    insumos_query = filtrar_por_empresa(Insumo.query, Insumo)
    for i in insumos_query.filter(or_(Insumo.nombre.ilike(f'%{q}%'), Insumo.codigo.ilike(f'%{q}%')), Insumo.cantidad_actual > 0).limit(15).all():
        res.append({
            'type': 'insumo', 
            'id': i.id, 
            'nombre': i.nombre, 
            'codigo': i.codigo, 
            'unidad': i.unidad.abreviatura if i.unidad else '', 
            'stock': i.cantidad_actual, 
            'costo': i.costo_promedio,
            'precio': i.precio_venta or 0,
            'origen': 'Bodega'
        })
    
    lotes_query = filtrar_por_empresa(LoteProduccion.query, LoteProduccion)
    lotes = lotes_query.join(Especie).filter(
        or_(Especie.nombre_comun.ilike(f'%{q}%'), LoteProduccion.codigo_lote.ilike(f'%{q}%')), 
        LoteProduccion.cantidad_actual > 0, 
        LoteProduccion.estado == 'Disponible', 
        LoteProduccion.proposito == 'Venta Plantula'
    ).limit(15).all()

    for l in lotes:
        res.append({
            'type': 'lote', 
            'id': l.id, 
            'nombre': f"{l.especie.nombre_comun} - {l.codigo_lote}", 
            'codigo': l.codigo_lote, 
            'unidad': 'Und', 
            'stock': l.cantidad_actual, 
            'costo': l.costo_total/l.cantidad_actual if l.cantidad_actual else 0, 
            'precio': l.especie.precio_venta_sugerido if l.especie else 0,
            'origen': 'Cultivo'
        })
        
    animales_query = filtrar_por_empresa(LoteAnimal.query, LoteAnimal)
    animales = animales_query.filter(
        or_(LoteAnimal.nombre.ilike(f'%{q}%'), LoteAnimal.codigo.ilike(f'%{q}%'), LoteAnimal.especie.ilike(f'%{q}%')),
        LoteAnimal.cantidad_actual > 0,
        LoteAnimal.estado.in_(['Activo', 'Disponible', 'Engorde', 'Leche', 'Cría', 'Cria'])
    ).limit(15).all()

    for a in animales:
        precio_est = a.raza_rel.valor_mercado_estimado if a.raza_rel and a.raza_rel.valor_mercado_estimado else ((a.costo_acumulado * 1.3) if a.costo_acumulado else 150000.0)
        res.append({
            'type': 'animal',
            'id': a.id,
            'nombre': f"🐄 {a.nombre or a.codigo} ({a.especie or 'Pecuario'})",
            'codigo': a.codigo,
            'unidad': 'Und' if a.tipo == 'Individual' else 'Lote',
            'stock': a.cantidad_actual,
            'costo': a.costo_acumulado / a.cantidad_actual if a.cantidad_actual else 0,
            'precio': precio_est,
            'origen': 'Pecuario'
        })

    return jsonify(res)


# =========================================================================
# GESTIÓN DE PEDIDOS WEB / TIENDA ONLINE (Estilo OPTICAL -> Enviar a POS)
# =========================================================================

@ventas_bp.route('/pedidos-web')
@login_required
def lista_pedidos_web():
    """Listado ejecutivo de pedidos realizados por clientes desde el Catálogo Digital."""
    q = request.args.get('q', '').strip()
    estado_filtro = request.args.get('estado', 'todos').strip()
    tiempo_filtro = request.args.get('tiempo', '').strip()
    
    base_query = filtrar_por_empresa(Venta.query, Venta).filter(
        or_(
            Venta.numero_factura.ilike('WEB-%'),
            Venta.estado == 'Pedido Web'
        )
    )
    
    todos_pedidos = base_query.all()
    kpi_total = len(todos_pedidos)
    kpi_pendientes_list = [p for p in todos_pedidos if p.estado in ['Pedido Web', 'Borrador']]
    kpi_pendientes = len(kpi_pendientes_list)
    kpi_monto_pendiente = sum(p.total or 0 for p in kpi_pendientes_list)
    kpi_facturados = sum(1 for p in todos_pedidos if p.estado == 'Finalizada')
    kpi_cancelados = sum(1 for p in todos_pedidos if p.estado == 'Cancelado')
    
    query = base_query
    if q:
        query = query.join(Cliente, Venta.cliente_id == Cliente.id).filter(or_(
            Venta.numero_factura.ilike(f'%{q}%'),
            Cliente.nombre.ilike(f'%{q}%'),
            Cliente.telefono.ilike(f'%{q}%'),
            Cliente.documento.ilike(f'%{q}%'),
            Cliente.direccion.ilike(f'%{q}%')
        ))
        
    if estado_filtro == 'pendientes':
        query = query.filter(Venta.estado.in_(['Pedido Web', 'Borrador']))
    elif estado_filtro == 'facturados':
        query = query.filter(Venta.estado == 'Finalizada')
    elif estado_filtro == 'cancelados':
        query = query.filter(Venta.estado == 'Cancelado')
        
    if tiempo_filtro == 'hoy':
        today = datetime.now(timezone.utc).date()
        query = query.filter(db.func.date(Venta.fecha) == today)
    elif tiempo_filtro == 'mes':
        today = datetime.now(timezone.utc)
        query = query.filter(
            db.extract('month', Venta.fecha) == today.month,
            db.extract('year', Venta.fecha) == today.year
        )
        
    pedidos = query.order_by(Venta.fecha.desc()).all()
    
    return render_template(
        'ventas/pedidos_web.html',
        pedidos=pedidos,
        q=q,
        estado_filtro=estado_filtro,
        tiempo_filtro=tiempo_filtro,
        kpi_total=kpi_total,
        kpi_pendientes=kpi_pendientes,
        kpi_monto_pendiente=kpi_monto_pendiente,
        kpi_facturados=kpi_facturados,
        kpi_cancelados=kpi_cancelados
    )


@ventas_bp.route('/pedidos-web/<int:venta_id>/enviar-pos')
@login_required
def enviar_pedido_pos(venta_id):
    """Carga un pedido web directamente al POS con todos sus ítems para cuadrar medio de pago y cobrar."""
    venta = get_or_404_empresa(Venta, venta_id)
    if venta.estado == 'Finalizada':
        flash(f'El pedido #{venta.numero_factura} ya fue facturado y finalizado.', 'info')
        return redirect(url_for('ventas.ver_venta', venta_id=venta.id))
        
    if venta.estado == 'Cancelado':
        flash(f'El pedido #{venta.numero_factura} estaba cancelado. Se ha reactivado para cobrar en POS.', 'warning')
        venta.estado = 'Pedido Web'
        
    # Asignar cajero/usuario actual al pedido
    venta.usuario_id = current_user.id
    db.session.commit()
    
    nombre_cli = venta.cliente.nombre if venta.cliente else 'Cliente Web'
    flash(f'🌱 Pedido #{venta.numero_factura} de {nombre_cli} cargado con éxito en el Punto de Venta. Cuadra el método de pago y cobra la venta.', 'success')
    return redirect(url_for('ventas.ver_venta', venta_id=venta.id))


@ventas_bp.route('/pedidos-web/<int:venta_id>/cancelar', methods=['POST'])
@login_required
def cancelar_pedido_web(venta_id):
    """Marca un pedido web como cancelado si el cliente desistió o no concretó el pago."""
    venta = get_or_404_empresa(Venta, venta_id)
    if venta.estado == 'Finalizada':
        flash('No se puede cancelar un pedido que ya fue facturado en el POS.', 'danger')
    else:
        venta.estado = 'Cancelado'
        db.session.commit()
        flash(f'Pedido #{venta.numero_factura} marcado como Cancelado.', 'info')
    return redirect(url_for('ventas.lista_pedidos_web'))


@ventas_bp.route('/pedidos-web/<int:venta_id>/detalle-json')
@login_required
def pedido_web_detalle_json(venta_id):
    """Retorna los datos del pedido en formato JSON para visualización rápida en modal."""
    venta = get_or_404_empresa(Venta, venta_id)
    detalles = []
    for d in venta.detalles:
        nom = d.lote_origen.especie.nombre_comun if d.lote_id and d.lote_origen and d.lote_origen.especie else (d.insumo.nombre if d.insumo else 'Producto')
        detalles.append({
            'nombre': nom,
            'cantidad': d.cantidad,
            'precio_unitario': d.precio_venta_unitario,
            'subtotal': d.subtotal,
            'tipo': 'Planta' if d.lote_id else 'Insumo'
        })
        
    return jsonify({
        'id': venta.id,
        'numero_factura': venta.numero_factura,
        'fecha': venta.fecha.strftime('%d/%m/%Y %H:%M') if venta.fecha else '',
        'estado': venta.estado,
        'total': venta.total,
        'cliente': {
            'nombre': venta.cliente.nombre if venta.cliente else 'Consumidor',
            'telefono': venta.cliente.telefono if venta.cliente else '',
            'direccion': venta.cliente.direccion if venta.cliente else '',
            'documento': venta.cliente.documento if venta.cliente else ''
        },
        'detalles': detalles
    })


# ==================================================
# INTEGRACIONES: FACTURACIÓN ELECTRÓNICA & PASARELAS
# ==================================================

@ventas_bp.route('/venta/<int:venta_id>/emitir-fe', methods=['POST'])
@login_required
def emitir_factura_electronica(venta_id):
    """Emite la factura electrónica ante la DIAN o el proveedor configurado."""
    venta = get_or_404_empresa(Venta, venta_id)
    exito, mensaje, venta = FacturacionElectronicaService.emitir_factura(venta)
    if exito:
        flash(f"¡Factura Electrónica emitida con éxito! {mensaje}", "success")
    else:
        flash(f"Aviso de Facturación Electrónica: {mensaje}", "warning")
    return redirect(url_for('ventas.ver_venta', venta_id=venta.id))


@ventas_bp.route('/venta/<int:venta_id>/iniciar-pago-online')
@login_required
def iniciar_pago_online(venta_id):
    """Inicia la pasarela de pagos para la venta (Wompi, Mercado Pago o Sandbox)."""
    venta = get_or_404_empresa(Venta, venta_id)
    if venta.estado_pago == 'APROBADO':
        flash('Esta venta ya se encuentra totalmente pagada.', 'info')
        return redirect(url_for('ventas.ver_venta', venta_id=venta.id))

    exito, url_pago, referencia = PasarelaPagosService.crear_sesion_pago(venta)
    if exito and url_pago:
        return redirect(url_pago)
    
    flash("No fue posible generar la sesión de pago online.", "danger")
    return redirect(url_for('ventas.ver_venta', venta_id=venta.id))


@ventas_bp.route('/venta/<int:venta_id>/checkout-simulado', methods=['GET', 'POST'])
def checkout_simulado(venta_id):
    """Página de pasarela de pago interactiva (Simulador Sandbox para pruebas sin contrato)."""
    venta = Venta.query.get_or_404(venta_id)
    if request.method == 'POST':
        accion = request.form.get('accion')
        metodo = request.form.get('metodo', 'Nequi / PSE')
        if accion == 'aprobar':
            PasarelaPagosService.aprobar_pago(venta, pasarela='SANDBOX', metodo=metodo)
            flash(f"¡Pago aprobado con éxito vía {metodo} (Simulación Sandbox)! Comprobante generado.", "success")
            return redirect(url_for('ventas.ver_venta', venta_id=venta.id))
        else:
            venta.estado_pago = 'RECHAZADO'
            db.session.commit()
            flash("El pago fue rechazado por la entidad bancaria simulada.", "warning")
            return redirect(url_for('ventas.ver_venta', venta_id=venta.id))

    return render_template('ventas/checkout_simulado.html', venta=venta)


@ventas_bp.route('/api/pagos/webhook/wompi', methods=['POST'])
def webhook_wompi():
    """Endpoint webhook para confirmaciones automáticas de Wompi Bancolombia."""
    data = request.get_json(silent=True) or {}
    evento = data.get('event')
    if evento == 'transaction.updated':
        trans = data.get('data', {}).get('transaction', {})
        referencia = trans.get('reference')
        status = trans.get('status')
        if referencia:
            venta = Venta.query.filter_by(referencia_pago=referencia).first()
            if venta and status == 'APPROVED':
                PasarelaPagosService.aprobar_pago(
                    venta,
                    pasarela='WOMPI',
                    id_transaccion=trans.get('id'),
                    metodo=trans.get('payment_method_type', 'Wompi')
                )
                logger.info(f"Pago Wompi aprobado para venta #{venta.id}")
    return jsonify({'status': 'received'}), 200


@ventas_bp.route('/api/pagos/webhook/mercadopago', methods=['POST'])
def webhook_mercadopago():
    """Endpoint webhook para confirmaciones automáticas de Mercado Pago."""
    data = request.get_json(silent=True) or {}
    topic = data.get('type') or request.args.get('topic')
    if topic in ('payment', 'collection'):
        payment_id = data.get('data', {}).get('id') or request.args.get('id')
        logger.info(f"Notificación recibida de Mercado Pago: payment_id={payment_id}")
    return jsonify({'status': 'received'}), 200


@ventas_bp.route('/empresa/configuracion-integraciones', methods=['GET', 'POST'])
@login_required
@solo_admin
def configuracion_integraciones():
    """Configuración de Facturación Electrónica DIAN y Pasarelas de Pago."""
    empresa = current_user.empresa
    if request.method == 'POST':
        # Facturación Electrónica
        empresa.fe_habilitada = (request.form.get('fe_habilitada') == 'on')
        empresa.fe_proveedor = request.form.get('fe_proveedor', 'SANDBOX')
        empresa.fe_ambiente = request.form.get('fe_ambiente', 'HABILITACION')
        empresa.fe_api_token = request.form.get('fe_api_token', '').strip() or None
        empresa.fe_resolucion = request.form.get('fe_resolucion', '').strip()
        empresa.fe_prefijo = request.form.get('fe_prefijo', 'SETP').strip()
        empresa.fe_clave_tecnica = request.form.get('fe_clave_tecnica', '').strip() or None

        # Pasarela de Pagos
        empresa.pagos_online_habilitados = (request.form.get('pagos_online_habilitados') == 'on')
        empresa.pasarela_predeterminada = request.form.get('pasarela_predeterminada', 'SANDBOX')
        empresa.wompi_public_key = request.form.get('wompi_public_key', '').strip() or None
        empresa.wompi_private_key = request.form.get('wompi_private_key', '').strip() or None
        empresa.wompi_integrity_secret = request.form.get('wompi_integrity_secret', '').strip() or None
        empresa.mercadopago_public_key = request.form.get('mercadopago_public_key', '').strip() or None
        empresa.mercadopago_access_token = request.form.get('mercadopago_access_token', '').strip() or None

        db.session.commit()
        registrar_auditoria('CONFIGURACION', 'Modificación de integraciones DIAN y Pagos Online')
        flash('Configuración de Facturación Electrónica y Pasarelas guardada con éxito.', 'success')
        return redirect(url_for('ventas.configuracion_integraciones'))

    return render_template('ventas/configuracion_integraciones.html', empresa=empresa)


# ==================================================
# MÓDULO DE CAJA POS: TURNOS, ARQUEO X Y CIERRE Z
# ==================================================

@ventas_bp.route('/caja')
@login_required
def control_caja():
    """
    Vista principal de Caja:
    - Si no hay turno abierto: Pantalla para abrir caja con base inicial en efectivo.
    - Si hay turno abierto: Panel de control de Arqueo X en tiempo real con ventas por método,
      movimientos menores y opción de Cierre Z.
    """
    empresa_id = current_user.empresa_id if hasattr(current_user, 'empresa_id') and current_user.empresa_id else None
    
    query = CajaTurno.query
    if empresa_id:
        query = query.filter_by(empresa_id=empresa_id)
    
    turno_activo = query.filter_by(estado='Abierta').order_by(CajaTurno.id.desc()).first()
    
    if not turno_activo:
        ultimo_turno = query.filter_by(estado='Cerrada').order_by(CajaTurno.id.desc()).first()
        return render_template('ventas/caja_apertura.html', ultimo_turno=ultimo_turno)
    
    totales = turno_activo.calcular_totales_actuales()
    movimientos = MovimientoCaja.query.filter_by(caja_turno_id=turno_activo.id).order_by(MovimientoCaja.fecha.desc()).all()
    ventas_turno = Venta.query.filter_by(caja_turno_id=turno_activo.id, estado='Finalizada').order_by(Venta.fecha.desc()).all()
    
    return render_template('ventas/caja_control.html', 
                           turno=turno_activo, 
                           totales=totales, 
                           movimientos=movimientos, 
                           ventas_turno=ventas_turno)


@ventas_bp.route('/caja/abrir', methods=['POST'])
@login_required
def abrir_caja():
    """Abre un nuevo turno de caja con la base inicial de efectivo."""
    empresa_id = current_user.empresa_id if hasattr(current_user, 'empresa_id') and current_user.empresa_id else None
    
    query = CajaTurno.query
    if empresa_id:
        query = query.filter_by(empresa_id=empresa_id)
    existente = query.filter_by(estado='Abierta').first()
    if existente:
        flash('Ya tienes un turno de caja abierto actualmente.', 'warning')
        return redirect(url_for('ventas.control_caja'))
        
    try:
        monto_apertura = safe_float(request.form.get('monto_apertura'), 0.0)
        observaciones = request.form.get('observaciones_apertura', '').strip()
        
        nuevo_turno = CajaTurno(
            empresa_id=empresa_id,
            usuario_apertura_id=current_user.id,
            fecha_apertura=datetime.now(timezone.utc),
            estado='Abierta',
            monto_apertura=monto_apertura,
            observaciones_apertura=observaciones
        )
        db.session.add(nuevo_turno)
        db.session.commit()
        
        flash(f'¡Turno de Caja #{nuevo_turno.id} abierto exitosamente con base de ${monto_apertura:,.0f}!', 'success')
        return redirect(url_for('ventas.control_caja'))
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error al abrir caja: {e}')
        flash(f'Error al abrir turno de caja: {e}', 'danger')
        return redirect(url_for('ventas.control_caja'))


@ventas_bp.route('/caja/movimiento', methods=['POST'])
@login_required
def registrar_movimiento_caja():
    """Registra una entrada adicional o gasto/retiro menor de efectivo en la gaveta."""
    empresa_id = current_user.empresa_id if hasattr(current_user, 'empresa_id') and current_user.empresa_id else None
    query = CajaTurno.query
    if empresa_id:
        query = query.filter_by(empresa_id=empresa_id)
    turno = query.filter_by(estado='Abierta').order_by(CajaTurno.id.desc()).first()
    
    if not turno:
        flash('No hay un turno de caja abierto para registrar movimientos.', 'warning')
        return redirect(url_for('ventas.control_caja'))
        
    try:
        tipo = request.form.get('tipo', 'Egreso').strip()
        concepto = request.form.get('concepto', '').strip()
        categoria = request.form.get('categoria', 'Varios').strip()
        monto = safe_float(request.form.get('monto'), 0.0)
        
        if monto <= 0:
            flash('El monto del movimiento debe ser superior a cero.', 'warning')
            return redirect(url_for('ventas.control_caja'))
            
        if not concepto:
            flash('Debe indicar un concepto o motivo para el movimiento.', 'warning')
            return redirect(url_for('ventas.control_caja'))
            
        mov = MovimientoCaja(
            empresa_id=empresa_id,
            caja_turno_id=turno.id,
            usuario_id=current_user.id,
            tipo=tipo,
            concepto=concepto,
            categoria=categoria,
            monto=monto,
            fecha=datetime.now(timezone.utc)
        )
        db.session.add(mov)
        db.session.commit()
        
        flash(f'Movimiento de {tipo} por ${monto:,.0f} registrado en caja.', 'success')
        return redirect(url_for('ventas.control_caja'))
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error registrando movimiento de caja: {e}')
        flash(f'Error registrando movimiento: {e}', 'danger')
        return redirect(url_for('ventas.control_caja'))


@ventas_bp.route('/caja/cerrar', methods=['POST'])
@login_required
def cerrar_caja():
    """Cierra el turno de caja definitivamente (Cierre Z), calcula diferencias y genera comprobante."""
    empresa_id = current_user.empresa_id if hasattr(current_user, 'empresa_id') and current_user.empresa_id else None
    query = CajaTurno.query
    if empresa_id:
        query = query.filter_by(empresa_id=empresa_id)
    turno = query.filter_by(estado='Abierta').order_by(CajaTurno.id.desc()).first()
    
    if not turno:
        flash('No hay un turno de caja abierto para cerrar.', 'warning')
        return redirect(url_for('ventas.control_caja'))
        
    try:
        monto_cierre_efectivo = safe_float(request.form.get('monto_cierre_efectivo'), 0.0)
        observaciones_cierre = request.form.get('observaciones_cierre', '').strip()
        
        # Calcular totales finales consolidados
        totales = turno.calcular_totales_actuales()
        
        turno.fecha_cierre = datetime.now(timezone.utc)
        turno.usuario_cierre_id = current_user.id
        turno.estado = 'Cerrada'
        
        v_tot = totales['ventas']
        turno.total_ventas_efectivo = v_tot['efectivo']
        turno.total_ventas_nequi = v_tot['nequi']
        turno.total_ventas_daviplata = v_tot['daviplata']
        turno.total_ventas_tarjeta = v_tot['tarjeta']
        turno.total_ventas_transferencia = v_tot['transferencia']
        turno.total_ventas_credito = v_tot['credito']
        turno.total_ventas_otros = v_tot['otros']
        turno.total_ventas = v_tot['global']
        
        turno.total_ingresos_caja = totales['total_ingresos']
        turno.total_egresos_caja = totales['total_egresos']
        
        turno.efectivo_esperado = totales['efectivo_esperado']
        turno.monto_cierre_efectivo = monto_cierre_efectivo
        turno.diferencia_efectivo = monto_cierre_efectivo - totales['efectivo_esperado']
        
        turno.observaciones_cierre = observaciones_cierre
        turno.comprobante_numero = f"CIERRE-Z-{datetime.now().strftime('%Y%m%d')}-{turno.id:04d}"
        
        db.session.commit()
        
        flash(f'¡Turno de Caja #{turno.id} cerrado exitosamente! Comprobante: {turno.comprobante_numero}', 'success')
        return redirect(url_for('ventas.comprobante_caja', turno_id=turno.id))
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error al cerrar caja: {e}')
        flash(f'Error al cerrar turno de caja: {e}', 'danger')
        return redirect(url_for('ventas.control_caja'))


@ventas_bp.route('/caja/turno/<int:turno_id>/comprobante')
@login_required
def comprobante_caja(turno_id):
    """Muestra el comprobante de Cierre Z o Arqueo X en formato térmico 80mm."""
    turno = get_or_404_empresa(CajaTurno, turno_id)
    
    es_parcial_x = (turno.estado == 'Abierta')
    totales = turno.calcular_totales_actuales()
    movimientos = MovimientoCaja.query.filter_by(caja_turno_id=turno.id).order_by(MovimientoCaja.fecha.asc()).all()
    
    return render_template('ventas/caja_comprobante.html', 
                           turno=turno, 
                           totales=totales, 
                           movimientos=movimientos, 
                           es_parcial_x=es_parcial_x)


@ventas_bp.route('/caja/historial')
@login_required
def historial_cajas():
    """Historial completo de turnos de caja con filtros y métricas consolidadas."""
    empresa_id = current_user.empresa_id if hasattr(current_user, 'empresa_id') and current_user.empresa_id else None
    query = CajaTurno.query
    if empresa_id:
        query = query.filter_by(empresa_id=empresa_id)
        
    turnos = query.order_by(CajaTurno.id.desc()).all()
    
    total_recaudado = sum(t.total_ventas or 0.0 for t in turnos if t.estado == 'Cerrada')
    total_cierres = len([t for t in turnos if t.estado == 'Cerrada'])
    
    return render_template('ventas/caja_historial.html', 
                           turnos=turnos, 
                           total_recaudado=total_recaudado, 
                           total_cierres=total_cierres)



