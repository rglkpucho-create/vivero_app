"""
Módulo SuperAdmin — Panel del proveedor del software.
Gestión de empresas clientes, licencias, activación/desactivación.
Solo accesible por usuarios con es_superadmin=True.
"""
import logging
import urllib.parse
from datetime import datetime, timezone, date, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from sqlalchemy import func
from ..models import (
    Empresa, Usuario, Rol, Venta, LoteProduccion, LoteAnimal, Insumo, AuditoriaLog, PagoSuscripcion, PLANES_SAAS
)
from ..extensions import db
from .helpers import solo_superadmin, guardar_imagen, registrar_auditoria

logger = logging.getLogger(__name__)
superadmin_bp = Blueprint('superadmin', __name__)


@superadmin_bp.route('/superadmin/empresas')
@solo_superadmin
def lista_empresas():
    empresas = Empresa.query.order_by(Empresa.licencia_activa.desc(), Empresa.nombre).all()
    
    # Estadísticas ejecutivas y métricas por empresa
    stats = {}
    today = datetime.now(timezone.utc).date()
    mrr_total = 0.0
    empresas_alerta_cobro = []
    
    for emp in empresas:
        # 1. Progreso y salud de licencia
        total_dias = None
        dias_restantes = None
        dias_transcurridos = None
        porcentaje_consumido = 0
        estado_licencia = 'vitalicia' # 'vitalicia', 'al_dia', 'por_vencer', 'vencida'
        color_progreso = 'success'
        
        if emp.fecha_vencimiento:
            fecha_reg_date = emp.fecha_registro.date() if emp.fecha_registro else today
            total_dias = (emp.fecha_vencimiento - fecha_reg_date).days
            if total_dias <= 0:
                total_dias = 1
            dias_transcurridos = (today - fecha_reg_date).days
            dias_restantes = (emp.fecha_vencimiento - today).days
            
            porcentaje_consumido = int((dias_transcurridos / total_dias) * 100)
            porcentaje_consumido = min(100, max(0, porcentaje_consumido))
            
            if dias_restantes < 0:
                estado_licencia = 'vencida'
                color_progreso = 'danger'
                porcentaje_consumido = 100
            elif dias_restantes <= 7: # Menos de una semana para vencer
                estado_licencia = 'por_vencer'
                color_progreso = 'warning'
            else:
                estado_licencia = 'al_dia'
                color_progreso = 'success'
        
        # 2. Contribución a MRR (Monthly Recurring Revenue)
        precio = float(emp.precio_suscripcion or 0.0)
        ciclo = (emp.ciclo_pago or 'Mensual').lower()
        if 'anual' in ciclo:
            mrr_emp = precio / 12.0
        elif 'semestral' in ciclo:
            mrr_emp = precio / 6.0
        else:
            mrr_emp = precio
            
        if emp.licencia_activa:
            mrr_total += mrr_emp

        # 3. Histórico de Pagos de Suscripción
        total_pagado = db.session.query(func.sum(PagoSuscripcion.monto)).filter_by(empresa_id=emp.id, estado='Aprobado').scalar() or 0.0
        conteo_pagos = PagoSuscripcion.query.filter_by(empresa_id=emp.id).count()

        # 4. Semáforo de Actividad y Adopción (Customer Health / Churn Risk)
        last_audit = AuditoriaLog.query.filter_by(empresa_id=emp.id).order_by(AuditoriaLog.fecha.desc()).first()
        last_venta = Venta.query.filter_by(empresa_id=emp.id).order_by(Venta.fecha.desc()).first()
        
        fechas_actividad = []
        if last_audit and last_audit.fecha:
            fechas_actividad.append(last_audit.fecha.date() if hasattr(last_audit.fecha, 'date') else last_audit.fecha)
        if last_venta and last_venta.fecha:
            fechas_actividad.append(last_venta.fecha.date() if hasattr(last_venta.fecha, 'date') else last_venta.fecha)
            
        if fechas_actividad:
            reciente = max(fechas_actividad)
            reciente_date = reciente.date() if hasattr(reciente, 'date') else reciente
            dias_inactivo = (today - reciente_date).days
            if dias_inactivo <= 0:
                texto_actividad = "Hoy"
                nivel_adopcion = "excelente"
                badge_adopcion_color = "success"
                adopcion_icono = "bi-fire"
            elif dias_inactivo == 1:
                texto_actividad = "Ayer"
                nivel_adopcion = "bueno"
                badge_adopcion_color = "success"
                adopcion_icono = "bi-check-circle"
            elif dias_inactivo <= 5:
                texto_actividad = f"Hace {dias_inactivo} días"
                nivel_adopcion = "bueno"
                badge_adopcion_color = "info"
                adopcion_icono = "bi-activity"
            elif dias_inactivo <= 12:
                texto_actividad = f"Hace {dias_inactivo} días"
                nivel_adopcion = "moderado"
                badge_adopcion_color = "warning"
                adopcion_icono = "bi-exclamation-triangle"
            else:
                texto_actividad = f"Hace {dias_inactivo} días (Sin uso)"
                nivel_adopcion = "riesgo"
                badge_adopcion_color = "danger"
                adopcion_icono = "bi-exclamation-octagon"
        else:
            if emp.fecha_registro:
                dias_reg = (today - emp.fecha_registro.date()).days
                texto_actividad = f"Nuevo (hace {dias_reg}d)"
            else:
                texto_actividad = "Sin registros"
            nivel_adopcion = "sin_datos"
            badge_adopcion_color = "secondary"
            adopcion_icono = "bi-clock-history"

        # 5. Enlace Inteligente de WhatsApp (Cobranza o Acompañamiento por Riesgo)
        tel = emp.telefono or ''
        tel_limpio = ''.join(c for c in tel if c.isdigit())
        if len(tel_limpio) == 10 and tel_limpio.startswith('3'):
            tel_limpio = '57' + tel_limpio
        elif len(tel_limpio) == 10:
            tel_limpio = '57' + tel_limpio

        valor_cobro_fmt = f"${precio:,.0f} COP" if precio > 0 else "su suscripción"
        if estado_licencia == 'vencida' or not emp.licencia_activa:
            dias_mora = abs(dias_restantes) if dias_restantes is not None else 0
            dias_txt = f"hace {dias_mora} día(s)" if dias_mora > 0 else "recientemente"
            msg = (
                f"Hola {emp.nombre} 🌱, le saludamos del equipo de EcoSistem.\n\n"
                f"Nos comunicamos cordialmente para informarle que su suscripción ({emp.plan_nombre or 'Plan SaaS'}) "
                f"se encuentra vencida {dias_txt} por valor de {valor_cobro_fmt}.\n\n"
                f"Para mantener activo su acceso, catálogos y registro de lotes sin interrupciones, puede renovar por transferencia a:\n"
                f"📱 Nequi / Daviplata: 310 000 0000\n"
                f"🏦 Bancolombia Ahorros: 000-000000-00\n\n"
                f"Por favor nos envía el soporte de pago por este chat para reactivar de inmediato su licencia. ¡Muchas gracias!"
            )
        elif estado_licencia == 'por_vencer':
            fecha_str = emp.fecha_vencimiento.strftime('%d/%m/%Y') if emp.fecha_vencimiento else ''
            msg = (
                f"Hola {emp.nombre} 🌱, un cordial saludo de EcoSistem.\n\n"
                f"Le recordamos amablemente que su suscripción ({emp.plan_nombre or 'Plan SaaS'}) "
                f"está próxima a vencer el día {fecha_str} (en {dias_restantes} día(s)) por valor de {valor_cobro_fmt}.\n\n"
                f"Puede realizar su renovación anticipada a:\n"
                f"📱 Nequi / Daviplata: 310 000 0000\n"
                f"🏦 Bancolombia Ahorros: 000-000000-00\n\n"
                f"¡Gracias por confiar en EcoSistem para la gestión de su vivero!"
            )
        elif nivel_adopcion == 'riesgo':
            msg = (
                f"Hola {emp.nombre} 🌱, le saluda el equipo de EcoSistem.\n\n"
                f"Notamos que hace varios días no han tenido movimiento en el sistema. "
                f"Queremos ofrecerle una breve sesión de acompañamiento de 15 minutos para ayudarle a cargar "
                f"sus plantas, organizar lotes o resolver dudas para que le saque el máximo provecho a su software.\n\n"
                f"¿Tiene disponibilidad esta semana para ayudarle?"
            )
        else:
            msg = f"Hola {emp.nombre} 🌱, un saludo del equipo de soporte de EcoSistem. ¿Cómo ha estado la gestión de su vivero hoy? Estamos a su servicio para cualquier duda o apoyo."

        whatsapp_cobro_url = f"https://wa.me/{tel_limpio}?text={urllib.parse.quote(msg)}" if tel_limpio else None

        # 6. Agrupar en lista de alerta de cobro si vence pronto o está vencida
        if (estado_licencia in ('vencida', 'por_vencer') or not emp.licencia_activa):
            empresas_alerta_cobro.append({
                'empresa': emp,
                'estado': estado_licencia,
                'dias_restantes': dias_restantes,
                'monto': precio,
                'ciclo': emp.ciclo_pago or 'Mensual',
                'whatsapp_url': whatsapp_cobro_url,
                'telefono': emp.telefono
            })

        stats[emp.id] = {
            'usuarios': Usuario.query.filter_by(empresa_id=emp.id).count(),
            'ventas_mes': db.session.query(func.sum(Venta.total)).filter(
                Venta.empresa_id == emp.id,
                Venta.estado != 'Cancelada',
                db.extract('month', Venta.fecha) == datetime.now(timezone.utc).month,
                db.extract('year', Venta.fecha) == datetime.now(timezone.utc).year
            ).scalar() or 0,
            'total_pagado': total_pagado,
            'conteo_pagos': conteo_pagos,
            # Campos de licencia
            'total_dias': total_dias,
            'dias_transcurridos': dias_transcurridos,
            'dias_restantes': dias_restantes,
            'porcentaje_consumido': porcentaje_consumido,
            'estado_licencia': estado_licencia,
            'color_progreso': color_progreso,
            'mrr_emp': mrr_emp,
            'whatsapp_url': whatsapp_cobro_url,
            'texto_actividad': texto_actividad,
            'nivel_adopcion': nivel_adopcion,
            'badge_adopcion_color': badge_adopcion_color,
            'adopcion_icono': adopcion_icono
        }

    # Ordenar alertas de cobro: primero vencidas, luego menor días restantes
    empresas_alerta_cobro.sort(key=lambda x: (0 if x['estado'] == 'vencida' else 1, x['dias_restantes'] if x['dias_restantes'] is not None else 999))

    total_recaudado_saas = sum(s['total_pagado'] for s in stats.values())
    total_pagos_saas = sum(s['conteo_pagos'] for s in stats.values())
    activas_count = len([e for e in empresas if e.licencia_activa])
    suspendidas_count = len(empresas) - activas_count
    por_vencer_count = len([e for e in empresas if stats[e.id]['estado_licencia'] == 'por_vencer'])
    vencidas_count = len([e for e in empresas if stats[e.id]['estado_licencia'] == 'vencida'])
    conteo_semilla = len([e for e in empresas if 'semilla' in (e.plan_nombre or '').lower()])
    conteo_cosecha = len([e for e in empresas if 'cosecha' in (e.plan_nombre or '').lower()])
    conteo_hacienda = len([e for e in empresas if 'hacienda' in (e.plan_nombre or '').lower()])
    conteo_riesgo = len([e for e in empresas if stats[e.id]['nivel_adopcion'] == 'riesgo'])
    arr_total = mrr_total * 12.0

    return render_template(
        'superadmin/lista_empresas.html', 
        empresas=empresas, 
        stats=stats,
        total_recaudado_saas=total_recaudado_saas,
        total_pagos_saas=total_pagos_saas,
        mrr_total=mrr_total,
        arr_total=arr_total,
        activas_count=activas_count,
        suspendidas_count=suspendidas_count,
        por_vencer_count=por_vencer_count,
        vencidas_count=vencidas_count,
        empresas_alerta_cobro=empresas_alerta_cobro,
        conteo_semilla=conteo_semilla,
        conteo_cosecha=conteo_cosecha,
        conteo_hacienda=conteo_hacienda,
        conteo_riesgo=conteo_riesgo
    )


@superadmin_bp.route('/superadmin/empresa/nueva', methods=['GET', 'POST'])
@solo_superadmin
def nueva_empresa():
    if request.method == 'POST':
        try:
            logo_path = None
            if 'logo' in request.files and request.files['logo'].filename != '':
                logo_path = guardar_imagen(request.files['logo'], 'logos')
            
            # Plan SaaS y Licencia Inicial
            plan_nombre = request.form.get('plan_nombre', 'Plan Cosecha Pro')
            try:
                precio_suscripcion = float(request.form.get('precio_suscripcion') or 119000.0)
            except ValueError:
                precio_suscripcion = 119000.0
            ciclo_pago = request.form.get('ciclo_pago', 'Mensual')
            
            # Vigencia de la licencia
            periodo_inicial = request.form.get('periodo_inicial', '30d')
            today = datetime.now(timezone.utc).date()
            if periodo_inicial == '30d':
                fecha_vencimiento = today + timedelta(days=30)
            elif periodo_inicial == '90d':
                fecha_vencimiento = today + timedelta(days=90)
            elif periodo_inicial == '365d':
                fecha_vencimiento = today + timedelta(days=365)
            elif periodo_inicial == 'vitalicia':
                fecha_vencimiento = None
            elif periodo_inicial == 'manual' and request.form.get('fecha_vencimiento'):
                fecha_vencimiento = datetime.strptime(request.form.get('fecha_vencimiento'), '%Y-%m-%d').date()
            else:
                fecha_vencimiento = today + timedelta(days=30)

            emp = Empresa(
                nombre=request.form.get('nombre'),
                nit_rut=request.form.get('nit_rut'),
                razon_social=request.form.get('razon_social'),
                telefono=request.form.get('telefono'),
                email=request.form.get('email'),
                direccion=request.form.get('direccion'),
                ciudad=request.form.get('ciudad'),
                sitio_web=request.form.get('sitio_web'),
                logo_url=logo_path,
                licencia_activa=True,
                plan_nombre=plan_nombre,
                precio_suscripcion=precio_suscripcion,
                ciclo_pago=ciclo_pago,
                fecha_vencimiento=fecha_vencimiento,
                notas_admin=request.form.get('notas_admin')
            )
            db.session.add(emp)
            db.session.commit()
            
            # Crear usuario admin para la empresa
            admin_password = request.form.get('admin_password', 'Admin123!')
            admin_email = request.form.get('admin_email')
            if admin_email:
                admin_rol = Rol.query.filter_by(nivel=1).first()
                u = Usuario(
                    nombre_completo=request.form.get('admin_nombre', 'Administrador'),
                    email=admin_email.strip().lower(),
                    telefono=request.form.get('admin_telefono'),
                    rol_id=admin_rol.id if admin_rol else None,
                    empresa_id=emp.id,
                    activo=True
                )
                u.set_password(admin_password)
                db.session.add(u)
                db.session.commit()
            
            registrar_auditoria('CREAR', 'SuperAdmin', f"Empresa '{emp.nombre}' creada con {emp.plan_nombre}")
            db.session.commit()
            flash(f'Empresa "{emp.nombre}" creada exitosamente con {emp.plan_nombre}.', 'success')
            return redirect(url_for('superadmin.lista_empresas'))
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error creando empresa: {e}')
            flash(f'Error: {e}', 'danger')
    
    roles = Rol.query.all()
    return render_template('superadmin/form_empresa.html', empresa=None, roles=roles, planes_saas=PLANES_SAAS)


@superadmin_bp.route('/superadmin/empresa/editar/<int:id>', methods=['GET', 'POST'])
@solo_superadmin
def editar_empresa(id):
    emp = Empresa.query.get_or_404(id)
    if request.method == 'POST':
        try:
            emp.nombre = request.form.get('nombre')
            emp.nit_rut = request.form.get('nit_rut')
            emp.razon_social = request.form.get('razon_social')
            emp.telefono = request.form.get('telefono')
            emp.email = request.form.get('email')
            emp.direccion = request.form.get('direccion')
            emp.ciudad = request.form.get('ciudad')
            emp.sitio_web = request.form.get('sitio_web')
            emp.notas_admin = request.form.get('notas_admin')
            
            # Plan SaaS y Cobranza
            if request.form.get('plan_nombre'):
                emp.plan_nombre = request.form.get('plan_nombre')
            if request.form.get('precio_suscripcion'):
                try:
                    emp.precio_suscripcion = float(request.form.get('precio_suscripcion'))
                except ValueError:
                    pass
            if request.form.get('ciclo_pago'):
                emp.ciclo_pago = request.form.get('ciclo_pago')
            if 'licencia_activa' in request.form:
                emp.licencia_activa = request.form.get('licencia_activa') == '1'
            
            if 'logo' in request.files and request.files['logo'].filename != '':
                emp.logo_url = guardar_imagen(request.files['logo'], 'logos')
            
            fecha_v = request.form.get('fecha_vencimiento')
            if fecha_v:
                emp.fecha_vencimiento = datetime.strptime(fecha_v, '%Y-%m-%d').date()
            else:
                emp.fecha_vencimiento = None
            
            db.session.commit()
            registrar_auditoria('EDITAR', 'SuperAdmin', f"Empresa '{emp.nombre}' editada")
            db.session.commit()
            flash('Empresa y plan SaaS actualizados correctamente.', 'success')
            return redirect(url_for('superadmin.lista_empresas'))
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error editando empresa: {e}')
            flash(f'Error: {e}', 'danger')
    
    usuarios = Usuario.query.filter_by(empresa_id=emp.id).all()
    roles = Rol.query.all()
    return render_template('superadmin/form_empresa.html', empresa=emp, usuarios=usuarios, roles=roles, planes_saas=PLANES_SAAS)


@superadmin_bp.route('/superadmin/empresa/toggle/<int:id>', methods=['POST'])
@solo_superadmin
def toggle_licencia(id):
    emp = Empresa.query.get_or_404(id)
    try:
        emp.licencia_activa = not emp.licencia_activa
        estado = "ACTIVADA" if emp.licencia_activa else "SUSPENDIDA"
        db.session.commit()
        registrar_auditoria('LICENCIA', 'SuperAdmin', f"Empresa '{emp.nombre}' {estado}")
        db.session.commit()
        
        color = 'success' if emp.licencia_activa else 'warning'
        flash(f'Licencia de "{emp.nombre}" {estado}.', color)
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {e}', 'danger')
    
    return redirect(url_for('superadmin.lista_empresas'))


@superadmin_bp.route('/superadmin/estadisticas')
@solo_superadmin
def estadisticas_globales():
    # 1. Cartera y Licencias
    empresas = Empresa.query.order_by(Empresa.nombre).all()
    total_empresas = len(empresas)
    empresas_activas = len([e for e in empresas if e.licencia_activa])
    empresas_suspendidas = total_empresas - empresas_activas
    total_usuarios = Usuario.query.filter_by(es_superadmin=False).count()
    
    # 2. Distribución de Planes
    conteo_semilla = len([e for e in empresas if 'semilla' in (e.plan_nombre or '').lower()])
    conteo_cosecha = len([e for e in empresas if 'cosecha' in (e.plan_nombre or '').lower()])
    conteo_hacienda = len([e for e in empresas if 'hacienda' in (e.plan_nombre or '').lower()])
    
    pct_semilla = int((conteo_semilla / (total_empresas or 1)) * 100)
    pct_cosecha = int((conteo_cosecha / (total_empresas or 1)) * 100)
    pct_hacienda = int((conteo_hacienda / (total_empresas or 1)) * 100)
    
    # 3. Métricas Financieras SaaS
    mrr_total = sum(
        (e.precio_suscripcion or 0) / (12.0 if 'anual' in (e.ciclo_pago or '').lower() else (6.0 if 'semestral' in (e.ciclo_pago or '').lower() else 1.0))
        for e in empresas if e.licencia_activa
    )
    arr_total = mrr_total * 12.0
    arpu = mrr_total / (empresas_activas or 1)
    
    total_recaudado = db.session.query(func.sum(PagoSuscripcion.monto)).filter_by(estado='Aprobado').scalar() or 0.0
    total_pagos = PagoSuscripcion.query.filter_by(estado='Aprobado').count()
    
    # 4. Métodos de Pago Preferidos
    metodos_raw = db.session.query(
        PagoSuscripcion.metodo_pago,
        func.count(PagoSuscripcion.id),
        func.sum(PagoSuscripcion.monto)
    ).filter_by(estado='Aprobado').group_by(PagoSuscripcion.metodo_pago).order_by(func.sum(PagoSuscripcion.monto).desc()).all()
    
    metodos_pago = []
    for m in metodos_raw:
        pct = (m[2] / (total_recaudado or 1)) * 100
        metodos_pago.append({
            'nombre': m[0] or 'Transferencia',
            'conteo': m[1],
            'total': m[2],
            'porcentaje': round(pct, 1)
        })
        
    # 5. Top 5 Clientes Más Valiosos (Mayor Facturación SaaS)
    top_clientes_raw = db.session.query(
        Empresa,
        func.sum(PagoSuscripcion.monto).label('total_pagado'),
        func.count(PagoSuscripcion.id).label('num_pagos')
    ).join(PagoSuscripcion).filter(PagoSuscripcion.estado == 'Aprobado').group_by(Empresa.id).order_by(func.sum(PagoSuscripcion.monto).desc()).limit(5).all()
    
    top_clientes = []
    for emp, pagado, num_pagos in top_clientes_raw:
        top_clientes.append({
            'empresa': emp,
            'total_pagado': pagado or 0.0,
            'num_pagos': num_pagos
        })
        
    # 6. Cobertura Geográfica en Colombia
    ciudades_raw = db.session.query(
        Empresa.ciudad,
        func.count(Empresa.id)
    ).filter(Empresa.ciudad.isnot(None)).group_by(Empresa.ciudad).order_by(func.count(Empresa.id).desc()).all()
    
    # 7. Volumen e Impacto de la Plataforma (Platform Scale)
    ventas_procesadas = db.session.query(func.sum(Venta.total)).filter(Venta.estado != 'Cancelada').scalar() or 0.0
    plantas_gestionadas = db.session.query(func.sum(LoteProduccion.cantidad_actual)).scalar() or 0
    lotes_totales = LoteProduccion.query.count()
    animales_gestionados = db.session.query(func.sum(LoteAnimal.cantidad_actual)).scalar() or 0
    insumos_inventario = Insumo.query.count()
    pedidos_web = Venta.query.filter(Venta.numero_factura.ilike('WEB-%')).count()
    
    return render_template('superadmin/estadisticas.html',
                           total_empresas=total_empresas,
                           empresas_activas=empresas_activas,
                           empresas_suspendidas=empresas_suspendidas,
                           total_usuarios=total_usuarios,
                           conteo_semilla=conteo_semilla,
                           conteo_cosecha=conteo_cosecha,
                           conteo_hacienda=conteo_hacienda,
                           pct_semilla=pct_semilla,
                           pct_cosecha=pct_cosecha,
                           pct_hacienda=pct_hacienda,
                           mrr_total=mrr_total,
                           arr_total=arr_total,
                           arpu=arpu,
                           total_recaudado=total_recaudado,
                           total_pagos=total_pagos,
                           metodos_pago=metodos_pago,
                           top_clientes=top_clientes,
                           ciudades=ciudades_raw,
                           ventas_procesadas=ventas_procesadas,
                           plantas_gestionadas=plantas_gestionadas,
                           lotes_totales=lotes_totales,
                           animales_gestionados=animales_gestionados,
                           insumos_inventario=insumos_inventario,
                           pedidos_web=pedidos_web)


@superadmin_bp.route('/superadmin/seleccionar_empresa', methods=['POST', 'GET'])
@solo_superadmin
def seleccionar_empresa_activa():
    from flask import session
    empresa_id = request.form.get('superadmin_empresa_id') or request.args.get('superadmin_empresa_id')
    redir = request.form.get('redir') or request.args.get('redir')
    if empresa_id:
        if str(empresa_id).lower() == 'todas':
            session.pop('superadmin_empresa_id', None)
            flash('Visualizando datos globales de TODAS las empresas.', 'info')
        else:
            try:
                emp_id_int = int(empresa_id)
                session['superadmin_empresa_id'] = emp_id_int
                emp = Empresa.query.get(emp_id_int)
                if emp:
                    flash(f'Empresa activa cambiada a: {emp.nombre}.', 'success')
            except (ValueError, TypeError):
                pass
    if redir == 'dashboard':
        return redirect(url_for('dashboard.dashboard'))
    return redirect(request.referrer or url_for('dashboard.dashboard'))


# ==========================================================
# GESTIÓN DETALLADA DE EMPRESA Y SUSCRIPCIONES SAAS
# ==========================================================

@superadmin_bp.route('/superadmin/empresa/<int:id>/control')
@solo_superadmin
def control_empresa(id):
    """
    Ficha Maestra de Control Detallado de la Empresa para el Propietario del Software.
    Permite ver fecha exacta de registro, días activo, historial financiero de pagos,
    cobertura, métricas operativas y registrar nuevos cobros de licencia.
    """
    emp = Empresa.query.get_or_404(id)
    pagos = PagoSuscripcion.query.filter_by(empresa_id=emp.id).order_by(PagoSuscripcion.fecha_pago.desc()).all()
    
    total_recaudado = sum(p.monto for p in pagos if p.estado == 'Aprobado')
    conteo_pagos = len(pagos)
    
    # Calcular días como cliente
    today = datetime.now(timezone.utc).date()
    fecha_reg = emp.fecha_registro.date() if emp.fecha_registro else today
    dias_cliente = (today - fecha_reg).days
    
    # Métricas de licencia
    dias_restantes = (emp.fecha_vencimiento - today).days if emp.fecha_vencimiento else None
    
    # Métricas operativas de la empresa
    usuarios = Usuario.query.filter_by(empresa_id=emp.id).all()
    total_lotes_plantas = LoteProduccion.query.filter_by(empresa_id=emp.id).count()
    total_plantas_vivas = db.session.query(func.sum(LoteProduccion.cantidad_actual)).filter(
        LoteProduccion.empresa_id == emp.id,
        LoteProduccion.estado == 'Disponible'
    ).scalar() or 0
    total_animales = db.session.query(func.sum(LoteAnimal.cantidad_actual)).filter(
        LoteAnimal.empresa_id == emp.id
    ).scalar() or 0
    total_ventas_historicas = db.session.query(func.sum(Venta.total)).filter(
        Venta.empresa_id == emp.id,
        Venta.estado != 'Cancelada'
    ).scalar() or 0.0
    pedidos_web_count = Venta.query.filter(
        Venta.empresa_id == emp.id,
        Venta.numero_factura.ilike('WEB-%')
    ).count()
    insumos_count = Insumo.query.filter_by(empresa_id=emp.id).count()
    
    # Sugerir siguiente número de recibo
    next_recibo = f"REC-{datetime.now().year}-{PagoSuscripcion.query.count() + 1:04d}"
    
    return render_template(
        'superadmin/control_empresa.html',
        empresa=emp,
        pagos=pagos,
        total_recaudado=total_recaudado,
        conteo_pagos=conteo_pagos,
        dias_cliente=dias_cliente,
        dias_restantes=dias_restantes,
        usuarios=usuarios,
        total_lotes_plantas=total_lotes_plantas,
        total_plantas_vivas=total_plantas_vivas,
        total_animales=total_animales,
        total_ventas_historicas=total_ventas_historicas,
        pedidos_web_count=pedidos_web_count,
        insumos_count=insumos_count,
        next_recibo=next_recibo,
        today=today
    )


@superadmin_bp.route('/superadmin/empresa/<int:id>/pago/nuevo', methods=['POST'])
@solo_superadmin
def registrar_pago_suscripcion(id):
    emp = Empresa.query.get_or_404(id)
    try:
        numero_recibo = request.form.get('numero_recibo', '').strip()
        monto = float(request.form.get('monto', 0))
        metodo_pago = request.form.get('metodo_pago', 'Transferencia Bancaria')
        referencia = request.form.get('referencia', '').strip()
        plan = request.form.get('plan', emp.plan_nombre or 'Plan Pro Vivero')
        meses_cobertura = int(request.form.get('meses_cobertura', 1))
        concepto = request.form.get('concepto', f'Pago Suscripción {plan}').strip()
        notas = request.form.get('notas', '').strip()
        
        fecha_pago_str = request.form.get('fecha_pago')
        if fecha_pago_str:
            fecha_pago = datetime.strptime(fecha_pago_str, '%Y-%m-%d')
        else:
            fecha_pago = datetime.now(timezone.utc)
            
        fecha_inicio_str = request.form.get('fecha_inicio')
        if fecha_inicio_str:
            fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
        else:
            fecha_inicio = emp.fecha_vencimiento or datetime.now(timezone.utc).date()
            
        fecha_fin_str = request.form.get('fecha_fin')
        if fecha_fin_str:
            fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()
        else:
            fecha_fin = fecha_inicio + timedelta(days=meses_cobertura * 30)
            
        if not numero_recibo:
            numero_recibo = f"REC-{datetime.now().year}-{PagoSuscripcion.query.count() + 1:04d}"
            
        pago = PagoSuscripcion(
            empresa_id=emp.id,
            numero_recibo=numero_recibo,
            fecha_pago=fecha_pago,
            monto=monto,
            metodo_pago=metodo_pago,
            referencia=referencia,
            plan=plan,
            meses_cobertura=meses_cobertura,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            estado='Aprobado',
            concepto=concepto,
            notas=notas,
            registrado_por=request.form.get('registrado_por', 'SuperAdmin Propietario')
        )
        db.session.add(pago)
        
        # Extender automáticamente fecha de vencimiento si el usuario lo marcó
        if request.form.get('actualizar_vencimiento') == 'on':
            emp.fecha_vencimiento = fecha_fin
            emp.licencia_activa = True
            emp.plan_nombre = plan
            
        db.session.commit()
        registrar_auditoria('PAGO_SAAS', 'SuperAdmin', f"Pago {numero_recibo} por ${monto:,.0f} registrado para '{emp.nombre}'")
        db.session.commit()
        
        flash(f'¡Pago {numero_recibo} de ${monto:,.0f} registrado con éxito para {emp.nombre}!', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error registrando pago de suscripción: {e}')
        flash(f'Error al registrar el pago: {e}', 'danger')
        
    return redirect(url_for('superadmin.control_empresa', id=emp.id))


@superadmin_bp.route('/superadmin/empresa/<int:id>/extender-licencia', methods=['POST'])
@solo_superadmin
def extender_licencia(id):
    emp = Empresa.query.get_or_404(id)
    try:
        tipo = request.form.get('tipo', 'dias')
        today = datetime.now(timezone.utc).date()
        base_date = emp.fecha_vencimiento if (emp.fecha_vencimiento and emp.fecha_vencimiento > today) else today
        
        if tipo == 'vitalicia':
            emp.fecha_vencimiento = None
            emp.licencia_activa = True
            flash(f'Licencia de {emp.nombre} actualizada a VITALICIA (Sin vencimiento).', 'success')
        else:
            dias = int(request.form.get('dias', 30))
            emp.fecha_vencimiento = base_date + timedelta(days=dias)
            emp.licencia_activa = True
            flash(f'Licencia de {emp.nombre} extendida por {dias} días (Nuevo vencimiento: {emp.fecha_vencimiento.strftime("%d/%m/%Y")}).', 'success')
            
        db.session.commit()
        registrar_auditoria('EXTENDER_LICENCIA', 'SuperAdmin', f"Licencia de '{emp.nombre}' extendida hasta {emp.fecha_vencimiento or 'Vitalicia'}")
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f'Error extendiendo licencia: {e}', 'danger')
        
    return redirect(url_for('superadmin.control_empresa', id=emp.id))


@superadmin_bp.route('/superadmin/pagos')
@solo_superadmin
def lista_pagos_saas():
    filtro_empresa = request.args.get('empresa_id', type=int)
    filtro_metodo = request.args.get('metodo')
    
    query = PagoSuscripcion.query.join(Empresa)
    if filtro_empresa:
        query = query.filter(PagoSuscripcion.empresa_id == filtro_empresa)
    if filtro_metodo:
        query = query.filter(PagoSuscripcion.metodo_pago == filtro_metodo)
        
    pagos = query.order_by(PagoSuscripcion.fecha_pago.desc()).all()
    empresas = Empresa.query.order_by(Empresa.nombre).all()
    
    total_recaudo_historico = db.session.query(func.sum(PagoSuscripcion.monto)).filter(PagoSuscripcion.estado == 'Aprobado').scalar() or 0.0
    
    now = datetime.now(timezone.utc)
    recaudo_mes_actual = db.session.query(func.sum(PagoSuscripcion.monto)).filter(
        PagoSuscripcion.estado == 'Aprobado',
        db.extract('month', PagoSuscripcion.fecha_pago) == now.month,
        db.extract('year', PagoSuscripcion.fecha_pago) == now.year
    ).scalar() or 0.0
    
    total_transacciones = PagoSuscripcion.query.count()
    empresas_al_dia = Empresa.query.filter(
        Empresa.licencia_activa == True,
        (Empresa.fecha_vencimiento >= now.date()) | (Empresa.fecha_vencimiento == None)
    ).count()
    
    return render_template(
        'superadmin/lista_pagos.html',
        pagos=pagos,
        empresas=empresas,
        total_recaudo_historico=total_recaudo_historico,
        recaudo_mes_actual=recaudo_mes_actual,
        total_transacciones=total_transacciones,
        empresas_al_dia=empresas_al_dia,
        filtro_empresa=filtro_empresa,
        filtro_metodo=filtro_metodo
    )


@superadmin_bp.route('/superadmin/pago/<int:id>/recibo')
@solo_superadmin
def ver_recibo_pago(id):
    pago = PagoSuscripcion.query.get_or_404(id)
    empresa = pago.empresa
    return render_template('superadmin/recibo_pago.html', pago=pago, empresa=empresa)


@superadmin_bp.route('/superadmin/pago/<int:id>/anular', methods=['POST'])
@solo_superadmin
def anular_pago_suscripcion(id):
    pago = PagoSuscripcion.query.get_or_404(id)
    pago.estado = 'Anulado'
    db.session.commit()
    registrar_auditoria('ANULAR_PAGO', 'SuperAdmin', f"Recibo {pago.numero_recibo} anulado")
    db.session.commit()
    flash(f'Recibo {pago.numero_recibo} anulado correctamente.', 'warning')
    return redirect(url_for('superadmin.control_empresa', id=pago.empresa_id))
