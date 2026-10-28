"""
Módulo Pro: Control de Mano de Obra, Jornales, Tareas y Nómina (Finca / Vivero)
Permite gestionar colaboradores, jornales diarios, labores al destajo (guadaña, poda)
y sueldos fijos con liquidación, recibos imprimibles y costeo directo.
"""
import logging
from datetime import datetime, timezone, date, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func, extract

from ..extensions import db
from ..models import (
    Trabajador, PagoManoObra, LoteProduccion, Sede, Empresa
)
from .helpers import (
    filtrar_por_empresa, asignar_empresa, get_or_404_empresa, registrar_auditoria
)

logger = logging.getLogger(__name__)
mano_obra_bp = Blueprint('mano_obra', __name__, url_prefix='/mano-obra')


# ==========================================================
# 1. DASHBOARD PRINCIPAL & HISTORIAL DE PAGOS
# ==========================================================
@mano_obra_bp.route('/', methods=['GET'])
@login_required
def dashboard():
    """
    Vista principal de Mano de Obra: KPIs del mes, filtros y registro rápido.
    """
    hoy = date.today()
    primer_dia_mes = date(hoy.year, hoy.month, 1)
    
    # Parámetros de filtrado
    filtro_estado = request.args.get('estado', '')
    filtro_modalidad = request.args.get('modalidad', '')
    filtro_trabajador = request.args.get('trabajador_id', '')
    filtro_fecha_desde = request.args.get('fecha_desde', '')
    filtro_fecha_hasta = request.args.get('fecha_hasta', '')
    busqueda = request.args.get('q', '').strip()

    # Query base filtrada por tenant
    query = filtrar_por_empresa(PagoManoObra.query, PagoManoObra)

    if filtro_estado:
        query = query.filter(PagoManoObra.estado == filtro_estado)
    if filtro_modalidad:
        query = query.filter(PagoManoObra.modalidad == filtro_modalidad)
    if filtro_trabajador:
        try:
            query = query.filter(PagoManoObra.trabajador_id == int(filtro_trabajador))
        except ValueError:
            pass
    if filtro_fecha_desde:
        try:
            f_desde = datetime.strptime(filtro_fecha_desde, '%Y-%m-%d').date()
            query = query.filter(PagoManoObra.fecha_labor >= f_desde)
        except ValueError:
            pass
    if filtro_fecha_hasta:
        try:
            f_hasta = datetime.strptime(filtro_fecha_hasta, '%Y-%m-%d').date()
            query = query.filter(PagoManoObra.fecha_labor <= f_hasta)
        except ValueError:
            pass
    if busqueda:
        query = query.join(Trabajador).filter(
            db.or_(
                PagoManoObra.labor_realizada.ilike(f'%{busqueda}%'),
                PagoManoObra.comprobante_numero.ilike(f'%{busqueda}%'),
                Trabajador.nombre_completo.ilike(f'%{busqueda}%'),
                Trabajador.documento.ilike(f'%{busqueda}%')
            )
        )

    pagos = query.order_by(PagoManoObra.fecha_labor.desc(), PagoManoObra.id.desc()).all()

    # Cálculo de KPIs (sobre el mes en curso)
    query_mes = filtrar_por_empresa(PagoManoObra.query, PagoManoObra).filter(
        PagoManoObra.fecha_labor >= primer_dia_mes
    )
    
    # 1. Total Pagado en el mes
    kpi_pagado_mes = query_mes.filter_by(estado='Pagado').with_entities(
        func.coalesce(func.sum(PagoManoObra.total_pagar), 0.0)
    ).scalar() or 0.0

    # 2. Pendientes por liquidar (histórico total pendiente)
    query_pendientes = filtrar_por_empresa(PagoManoObra.query, PagoManoObra).filter_by(estado='Pendiente')
    kpi_pendiente_monto = query_pendientes.with_entities(
        func.coalesce(func.sum(PagoManoObra.total_pagar), 0.0)
    ).scalar() or 0.0
    kpi_pendiente_conteo = query_pendientes.count()

    # 3. Total de Jornales liquidados este mes
    kpi_jornales_mes = query_mes.filter_by(modalidad='Jornal', estado='Pagado').with_entities(
        func.coalesce(func.sum(PagoManoObra.cantidad), 0.0)
    ).scalar() or 0.0

    # 4. Total Colaboradores activos
    kpi_colaboradores_activos = filtrar_por_empresa(Trabajador.query, Trabajador).filter_by(activo=True).count()

    # Listas auxiliares para modal de nuevo registro
    colaboradores = filtrar_por_empresa(Trabajador.query, Trabajador).filter_by(activo=True).order_by(Trabajador.nombre_completo).all()
    lotes = filtrar_por_empresa(LoteProduccion.query, LoteProduccion).order_by(LoteProduccion.id.desc()).all()
    sedes = filtrar_por_empresa(Sede.query, Sede).order_by(Sede.nombre).all()

    return render_template(
        'mano_obra/dashboard.html',
        pagos=pagos,
        kpi_pagado_mes=kpi_pagado_mes,
        kpi_pendiente_monto=kpi_pendiente_monto,
        kpi_pendiente_conteo=kpi_pendiente_conteo,
        kpi_jornales_mes=kpi_jornales_mes,
        kpi_colaboradores_activos=kpi_colaboradores_activos,
        colaboradores=colaboradores,
        lotes=lotes,
        sedes=sedes,
        filtro_estado=filtro_estado,
        filtro_modalidad=filtro_modalidad,
        filtro_trabajador=filtro_trabajador,
        filtro_fecha_desde=filtro_fecha_desde,
        filtro_fecha_hasta=filtro_fecha_hasta,
        busqueda=busqueda
    )


# ==========================================================
# 2. REGISTRAR PAGO O LABOR
# ==========================================================
@mano_obra_bp.route('/pagos/nuevo', methods=['POST'])
@login_required
def nuevo_pago():
    """
    Registra una labor ejecutada o liquidación de jornal / sueldo / tarea.
    Calcula: (cantidad * tarifa_unitaria) + bonificaciones - deducciones = total_pagar
    """
    try:
        trabajador_id = int(request.form.get('trabajador_id'))
        trabajador = get_or_404_empresa(Trabajador, trabajador_id)

        fecha_labor_str = request.form.get('fecha_labor')
        fecha_labor = datetime.strptime(fecha_labor_str, '%Y-%m-%d').date() if fecha_labor_str else date.today()

        modalidad = request.form.get('modalidad', trabajador.modalidad or 'Jornal')
        labor_realizada = request.form.get('labor_realizada', '').strip()
        if not labor_realizada:
            flash('Debe especificar la labor realizada o concepto.', 'warning')
            return redirect(url_for('mano_obra.dashboard'))

        cantidad = float(request.form.get('cantidad', 1.0))
        unidad_medida = request.form.get('unidad_medida', 'Días')
        tarifa_unitaria = float(request.form.get('tarifa_unitaria', trabajador.tarifa_base or 0.0))
        bonificaciones = float(request.form.get('bonificaciones', 0.0) or 0.0)
        deducciones = float(request.form.get('deducciones', 0.0) or 0.0)

        # Cálculo de liquidación
        subtotal = round(cantidad * tarifa_unitaria, 2)
        total_pagar = max(0.0, round(subtotal + bonificaciones - deducciones, 2))

        estado = request.form.get('estado', 'Pagado')
        metodo_pago = request.form.get('metodo_pago', 'Efectivo')
        fecha_pago = date.today() if estado == 'Pagado' else None

        lote_id = request.form.get('lote_id')
        lote_id = int(lote_id) if lote_id and lote_id.isdigit() else None

        sede_id = request.form.get('sede_id')
        sede_id = int(sede_id) if sede_id and sede_id.isdigit() else (trabajador.sede_id or None)

        notas = request.form.get('notas', '').strip()

        # Número de comprobante único
        numero_comp = f"REC-MO-{int(datetime.now().timestamp())}"

        nuevo = PagoManoObra(
            trabajador_id=trabajador.id,
            fecha_labor=fecha_labor,
            modalidad=modalidad,
            labor_realizada=labor_realizada,
            lote_id=lote_id,
            sede_id=sede_id,
            cantidad=cantidad,
            unidad_medida=unidad_medida,
            tarifa_unitaria=tarifa_unitaria,
            bonificaciones=bonificaciones,
            deducciones=deducciones,
            total_pagar=total_pagar,
            estado=estado,
            fecha_pago=fecha_pago,
            metodo_pago=metodo_pago,
            comprobante_numero=numero_comp,
            notas=notas,
            registrado_por_id=current_user.id
        )
        asignar_empresa(nuevo)
        db.session.add(nuevo)

        # Si está vinculado a un Lote de Producción, podemos sumar opcionalmente al costo_total del lote
        if lote_id and estado == 'Pagado':
            lote = LoteProduccion.query.get(lote_id)
            if lote and lote.empresa_id == nuevo.empresa_id:
                lote.costo_total = (lote.costo_total or 0.0) + total_pagar

        db.session.commit()
        registrar_auditoria('CREAR', 'ManoDeObra', f'Pago registrado #{numero_comp} a {trabajador.nombre_completo}: ${total_pagar:,.0f}')
        flash(f'¡Registro de mano de obra #{numero_comp} guardado exitosamente!', 'success')

    except Exception as e:
        db.session.rollback()
        logger.error(f'Error registrando pago de mano de obra: {e}')
        flash(f'Error al registrar labor: {str(e)}', 'danger')

    return redirect(url_for('mano_obra.dashboard'))


# ==========================================================
# 3. CAMBIAR ESTADO A PAGADO
# ==========================================================
@mano_obra_bp.route('/pagos/<int:pago_id>/marcar-pagado', methods=['POST'])
@login_required
def marcar_pagado(pago_id):
    """
    Liquida y marca como 'Pagado' un registro pendiente.
    """
    pago = get_or_404_empresa(PagoManoObra, pago_id)
    try:
        metodo = request.form.get('metodo_pago', 'Efectivo')
        pago.estado = 'Pagado'
        pago.metodo_pago = metodo
        pago.fecha_pago = date.today()

        # Si tiene lote y no se había cargado, sumamos el costo
        if pago.lote_id and pago.lote:
            pago.lote.costo_total = (pago.lote.costo_total or 0.0) + pago.total_pagar

        db.session.commit()
        registrar_auditoria('ACTUALIZAR', 'ManoDeObra', f'Pago #{pago.comprobante_numero} marcado como Pagado')
        flash(f'Labor #{pago.comprobante_numero} liquidada exitosamente.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error liquidando pago: {e}')
        flash(f'Error al liquidar pago: {e}', 'danger')

    return redirect(url_for('mano_obra.dashboard'))


# ==========================================================
# 4. ELIMINAR REGISTRO DE MANO DE OBRA
# ==========================================================
@mano_obra_bp.route('/pagos/<int:pago_id>/eliminar', methods=['POST'])
@login_required
def eliminar_pago(pago_id):
    """
    Elimina un registro de mano de obra erróneo.
    """
    pago = get_or_404_empresa(PagoManoObra, pago_id)
    try:
        num = pago.comprobante_numero
        db.session.delete(pago)
        db.session.commit()
        registrar_auditoria('ELIMINAR', 'ManoDeObra', f'Registro #{num} eliminado')
        flash(f'Registro #{num} eliminado con éxito.', 'info')
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error eliminando pago: {e}')
        flash(f'No se pudo eliminar el registro: {e}', 'danger')

    return redirect(url_for('mano_obra.dashboard'))


# ==========================================================
# 5. RECIBO DE PAGO IMPRIMIBLE (COMPROBANTE FORMAL)
# ==========================================================
@mano_obra_bp.route('/pagos/<int:pago_id>/recibo', methods=['GET'])
@login_required
def recibo_pago(pago_id):
    """
    Vista de impresión de comprobante / recibo de pago para firma del trabajador.
    """
    pago = get_or_404_empresa(PagoManoObra, pago_id)
    empresa = pago.empresa or current_user.empresa
    return render_template('mano_obra/recibo_pago.html', pago=pago, empresa=empresa)


# ==========================================================
# 6. GESTIÓN DE COLABORADORES / TRABAJADORES
# ==========================================================
@mano_obra_bp.route('/colaboradores', methods=['GET'])
@login_required
def lista_colaboradores():
    """
    Directorio de colaboradores y trabajadores de la finca/vivero.
    """
    colaboradores = filtrar_por_empresa(Trabajador.query, Trabajador).order_by(Trabajador.activo.desc(), Trabajador.nombre_completo).all()
    sedes = filtrar_por_empresa(Sede.query, Sede).order_by(Sede.nombre).all()
    return render_template('mano_obra/colaboradores.html', colaboradores=colaboradores, sedes=sedes)


@mano_obra_bp.route('/colaboradores/nuevo', methods=['POST'])
@login_required
def nuevo_colaborador():
    """
    Crea un nuevo colaborador con su modalidad y tarifa base.
    """
    try:
        nombre = request.form.get('nombre_completo', '').strip()
        if not nombre:
            flash('El nombre del colaborador es obligatorio.', 'warning')
            return redirect(url_for('mano_obra.lista_colaboradores'))

        doc = request.form.get('documento', '').strip()
        tel = request.form.get('telefono', '').strip()
        cargo = request.form.get('cargo', '').strip()
        modalidad = request.form.get('modalidad', 'Jornal')
        tarifa_base = float(request.form.get('tarifa_base', 0.0) or 0.0)
        
        sede_id = request.form.get('sede_id')
        sede_id = int(sede_id) if sede_id and sede_id.isdigit() else None
        
        obs = request.form.get('observaciones', '').strip()

        trabajador = Trabajador(
            nombre_completo=nombre,
            documento=doc,
            telefono=tel,
            cargo=cargo,
            modalidad=modalidad,
            tarifa_base=tarifa_base,
            sede_id=sede_id,
            observaciones=obs,
            activo=True
        )
        asignar_empresa(trabajador)
        db.session.add(trabajador)
        db.session.commit()
        registrar_auditoria('CREAR', 'Colaboradores', f'Nuevo colaborador: {nombre} ({modalidad})')
        flash(f'Colaborador {nombre} registrado exitosamente.', 'success')

    except Exception as e:
        db.session.rollback()
        logger.error(f'Error creando colaborador: {e}')
        flash(f'Error al registrar colaborador: {e}', 'danger')

    return redirect(url_for('mano_obra.lista_colaboradores'))


@mano_obra_bp.route('/colaboradores/<int:trabajador_id>/editar', methods=['POST'])
@login_required
def editar_colaborador(trabajador_id):
    """
    Edita la información, tarifa base o estado de un colaborador.
    """
    trabajador = get_or_404_empresa(Trabajador, trabajador_id)
    try:
        trabajador.nombre_completo = request.form.get('nombre_completo', trabajador.nombre_completo).strip()
        trabajador.documento = request.form.get('documento', trabajador.documento).strip()
        trabajador.telefono = request.form.get('telefono', trabajador.telefono).strip()
        trabajador.cargo = request.form.get('cargo', trabajador.cargo).strip()
        trabajador.modalidad = request.form.get('modalidad', trabajador.modalidad)
        trabajador.tarifa_base = float(request.form.get('tarifa_base', trabajador.tarifa_base or 0.0) or 0.0)

        sede_id = request.form.get('sede_id')
        trabajador.sede_id = int(sede_id) if sede_id and sede_id.isdigit() else None

        trabajador.activo = True if request.form.get('activo') == 'on' else False
        trabajador.observaciones = request.form.get('observaciones', '').strip()

        db.session.commit()
        registrar_auditoria('ACTUALIZAR', 'Colaboradores', f'Actualizado colaborador: {trabajador.nombre_completo}')
        flash(f'Colaborador {trabajador.nombre_completo} actualizado correctamente.', 'success')

    except Exception as e:
        db.session.rollback()
        logger.error(f'Error editando colaborador: {e}')
        flash(f'Error al actualizar: {e}', 'danger')

    return redirect(url_for('mano_obra.lista_colaboradores'))
