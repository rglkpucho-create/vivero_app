import logging
from datetime import datetime, timezone, date
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, Response
from flask_login import login_required, current_user
from ..extensions import db
from ..models import (
    Venta, AbonoVenta, Cliente, CajaTurno, MovimientoCaja
)
from .helpers import (
    filtrar_por_empresa, asignar_empresa, get_or_404_empresa,
    empresa_id_actual, obtener_empresa_activa
)
from ..services.pdf_generator import generar_pdf_recibo_abono

logger = logging.getLogger(__name__)

cartera_bp = Blueprint('cartera', __name__, url_prefix='/cartera')


@cartera_bp.route('/')
@login_required
def index():
    """Tablero general de Cuentas por Cobrar y Gestión de Cartera."""
    estado_filtro = request.args.get('estado', 'pendiente').strip() # 'pendiente', 'vencida', 'saldada', 'todas'
    cliente_id = request.args.get('cliente_id', type=int)
    q = request.args.get('q', '').strip()

    hoy = date.today()

    # Base query: ventas de la empresa que sean a crédito o que hayan tenido saldo
    query = filtrar_por_empresa(Venta.query, Venta).filter(
        db.or_(
            Venta.tipo_venta == 'Credito',
            Venta.saldo > 0,
            Venta.abono > 0
        )
    )

    if cliente_id:
        query = query.filter(Venta.cliente_id == cliente_id)

    if q:
        query = query.join(Cliente, Venta.cliente_id == Cliente.id, isouter=True).filter(
            db.or_(
                Venta.numero_factura.ilike(f'%{q}%'),
                Cliente.nombre.ilike(f'%{q}%'),
                Cliente.documento.ilike(f'%{q}%')
            )
        )

    if estado_filtro == 'pendiente':
        query = query.filter(Venta.saldo > 0)
    elif estado_filtro == 'vencida':
        query = query.filter(Venta.saldo > 0, Venta.fecha_vencimiento < hoy)
    elif estado_filtro == 'saldada':
        query = query.filter(Venta.saldo <= 0)

    ventas_cartera = query.order_by(Venta.fecha.desc()).all()

    # Cálculo de KPIs globales de la empresa
    todas_credito = filtrar_por_empresa(Venta.query, Venta).filter(
        db.or_(Venta.tipo_venta == 'Credito', Venta.saldo > 0)
    ).all()

    total_cartera_pendiente = sum(v.saldo or 0.0 for v in todas_credito if (v.saldo or 0) > 0)
    cartera_vencida = sum(v.saldo or 0.0 for v in todas_credito if (v.saldo or 0) > 0 and v.fecha_vencimiento and v.fecha_vencimiento < hoy)
    cartera_al_dia = max(0.0, total_cartera_pendiente - cartera_vencida)
    
    deudores_ids = set(v.cliente_id for v in todas_credito if (v.saldo or 0) > 0 and v.cliente_id)
    clientes_deudores_count = len(deudores_ids)

    # Recaudo del mes actual
    primer_dia_mes = datetime(hoy.year, hoy.month, 1, tzinfo=timezone.utc)
    abonos_mes = filtrar_por_empresa(AbonoVenta.query, AbonoVenta).filter(
        AbonoVenta.fecha >= primer_dia_mes
    ).all()
    total_recaudado_mes = sum(a.monto or 0.0 for a in abonos_mes)

    clientes = filtrar_por_empresa(Cliente.query, Cliente).order_by(Cliente.nombre).all()

    # Turno de caja activo para sugerir método de cobro
    eid = empresa_id_actual()
    caja_activa = CajaTurno.query.filter_by(empresa_id=eid, estado='Abierta').order_by(CajaTurno.id.desc()).first()

    return render_template(
        'cartera/index.html',
        ventas_cartera=ventas_cartera,
        clientes=clientes,
        hoy=hoy,
        total_cartera_pendiente=total_cartera_pendiente,
        cartera_vencida=cartera_vencida,
        cartera_al_dia=cartera_al_dia,
        clientes_deudores_count=clientes_deudores_count,
        total_recaudado_mes=total_recaudado_mes,
        estado_filtro=estado_filtro,
        cliente_id=cliente_id,
        q=q,
        caja_activa=caja_activa
    )


@cartera_bp.route('/abono', methods=['POST'])
@login_required
def registrar_abono():
    """Registra un abono parcial o total a una factura a crédito."""
    venta_id = request.form.get('venta_id', type=int)
    monto = float(request.form.get('monto', 0))
    metodo_pago = request.form.get('metodo_pago', 'Efectivo').strip()
    notas = request.form.get('notas', '').strip()

    venta = get_or_404_empresa(Venta, venta_id)

    if monto <= 0:
        flash("El valor del abono debe ser mayor a cero.", "danger")
        return redirect(url_for('cartera.index'))

    if monto > (venta.saldo + 0.01):
        flash(f"El monto (${monto:,.0f}) supera el saldo pendiente de la factura (${venta.saldo:,.0f}).", "warning")
        return redirect(url_for('cartera.index'))

    try:
        eid = empresa_id_actual()
        consecutivo = AbonoVenta.query.filter_by(empresa_id=eid).count() + 1
        num_recibo = f"RC-{consecutivo:04d}"

        saldo_anterior = venta.saldo
        saldo_nuevo = max(0.0, round(saldo_anterior - monto, 2))

        # Turno de caja para vincular el ingreso en efectivo
        caja_activa = CajaTurno.query.filter_by(empresa_id=eid, estado='Abierta').order_by(CajaTurno.id.desc()).first()
        caja_turno_id = caja_activa.id if caja_activa else None

        abono = AbonoVenta(
            numero_recibo=num_recibo,
            venta_id=venta.id,
            cliente_id=venta.cliente_id,
            usuario_id=current_user.id,
            caja_turno_id=caja_turno_id,
            monto=monto,
            metodo_pago=metodo_pago,
            saldo_anterior=saldo_anterior,
            saldo_nuevo=saldo_nuevo,
            notas=notas
        )
        asignar_empresa(abono)
        db.session.add(abono)

        # Actualizar acumulado de la venta
        venta.abono = (venta.abono or 0.0) + monto
        venta.saldo = saldo_nuevo

        # Si el pago es en efectivo y hay caja abierta, registrar movimiento de ingreso
        if metodo_pago.lower() == 'efectivo' and caja_activa:
            cli_nom = venta.cliente.nombre if venta.cliente else 'Cliente'
            mov = MovimientoCaja(
                caja_turno_id=caja_activa.id,
                tipo='Ingreso',
                monto=monto,
                concepto=f"Abono Factura #{venta.numero_factura} ({num_recibo}) - {cli_nom}",
                usuario_id=current_user.id
            )
            asignar_empresa(mov)
            db.session.add(mov)

        db.session.commit()

        estado_msg = "Factura totalmente pagada y cancelada." if saldo_nuevo <= 0 else f"Nuevo saldo pendiente: ${saldo_nuevo:,.0f}."
        flash(f"¡Abono #{num_recibo} por ${monto:,.0f} registrado con éxito! {estado_msg}", "success")
        return redirect(url_for('cartera.index'))

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error registrando abono a venta #{venta_id}: {e}")
        flash(f"Error registrando abono: {str(e)}", "danger")
        return redirect(url_for('cartera.index'))


@cartera_bp.route('/recibo/<int:abono_id>/pdf')
@login_required
def descargar_recibo_pdf(abono_id):
    """Genera y descarga en streaming el comprobante de abono / recibo de caja en PDF."""
    abono = get_or_404_empresa(AbonoVenta, abono_id)
    try:
        pdf_bytes = generar_pdf_recibo_abono(abono)
        filename = f"Recibo_{abono.numero_recibo}.pdf"
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={'Content-Disposition': f'inline; filename="{filename}"'}
        )
    except Exception as e:
        logger.error(f"Error generando PDF de recibo #{abono_id}: {e}")
        flash(f"Error al generar recibo en PDF: {str(e)}", "danger")
        return redirect(url_for('cartera.index'))


@cartera_bp.route('/cliente/<int:cliente_id>')
@login_required
def estado_cuenta_cliente(cliente_id):
    """Estado de cuenta consolidado del cliente con historial de compras a crédito y abonos."""
    cliente = get_or_404_empresa(Cliente, cliente_id)
    ventas = filtrar_por_empresa(Venta.query, Venta).filter_by(cliente_id=cliente.id).order_by(Venta.fecha.desc()).all()
    abonos = filtrar_por_empresa(AbonoVenta.query, AbonoVenta).filter_by(cliente_id=cliente.id).order_by(AbonoVenta.fecha.desc()).all()

    total_comprado = sum(v.total or 0 for v in ventas)
    saldo_total_pendiente = sum(v.saldo or 0 for v in ventas if (v.saldo or 0) > 0)
    total_abonado = sum(a.monto or 0 for a in abonos)

    return render_template(
        'cartera/cliente_detalle.html',
        cliente=cliente,
        ventas=ventas,
        abonos=abonos,
        total_comprado=total_comprado,
        saldo_total_pendiente=saldo_total_pendiente,
        total_abonado=total_abonado,
        hoy=date.today()
    )


@cartera_bp.route('/cliente/<int:cliente_id>/whatsapp-cobro')
@login_required
def whatsapp_recordatorio_cobro(cliente_id):
    """Genera un mensaje respetuoso y profesional de cobro / recordatorio de saldo por WhatsApp."""
    cliente = get_or_404_empresa(Cliente, cliente_id)
    empresa = obtener_empresa_activa()
    
    ventas_pendientes = filtrar_por_empresa(Venta.query, Venta).filter(
        Venta.cliente_id == cliente.id,
        Venta.saldo > 0
    ).all()

    saldo_total = sum(v.saldo for v in ventas_pendientes)

    telefono = (cliente.telefono or "").replace(" ", "").replace("+", "").replace("-", "")
    if telefono.startswith("3") and len(telefono) == 10:
        telefono = f"57{telefono}"

    nombre_empresa = empresa.nombre if empresa else "EcoSistem"
    
    lineas = [
        f"🌾 *¡Hola {cliente.nombre}!*",
        f"Te saludamos cordialmente de *{nombre_empresa}*.",
        "Nos comunicamos para compartirte el estado de cuenta actualizado de tus pedidos a crédito:",
        f"📌 *Saldo Pendiente:* ${saldo_total:,.0f} COP",
        f"📄 *Facturas Pendientes:* {len(ventas_pendientes)}",
        "",
        "Si ya realizaste tu pago o transferencia, te agradecemos enviarnos el soporte para conciliar tu cuenta. ¡Muchas gracias por tu compromiso!"
    ]
    mensaje = "%0A".join(lineas)
    wa_link = f"https://api.whatsapp.com/send?phone={telefono}&text={mensaje}" if telefono else f"https://api.whatsapp.com/send?text={mensaje}"

    return jsonify({'success': True, 'whatsapp_url': wa_link})
