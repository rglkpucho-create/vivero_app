"""
Dashboard y motor de IA para tareas sugeridas.
"""
import logging
from datetime import datetime, timezone, timedelta
from flask import Blueprint, render_template, url_for
from flask_login import login_required, current_user
from sqlalchemy import func
from ..models import (
    LoteProduccion, Especie, Insumo, LoteAnimal, RazaAnimal,
    Venta, ConsumoInsumo, LaborCampo, ConsumoAnimal, EventoSanitario,
    PedidoCompra, Proveedor
)
from ..extensions import db
from .helpers import filtrar_por_empresa
from sqlalchemy import or_

logger = logging.getLogger(__name__)
dashboard_bp = Blueprint('dashboard', __name__)


def analizar_necesidades_insumos(tareas):
    """Analiza si las tareas sugeridas requieren insumos sin stock y agrupa inteligentemente las alertas."""
    alertas = []
    mapping = {
        'Fertilización': ['Fertilizante', 'Abono', 'Triple 15', 'Urea'],
        'Control de Plagas': ['Insecticida', 'Plaguicida', 'Fungicida', 'Veneno'],
        'Chequeo Médico': ['Medicamento', 'Vacuna', 'Antibiótico', 'Vitamina']
    }
    
    agrupadas = {}
    for tarea in tareas:
        titulo_tarea = tarea.get('titulo', '')
        for key, palabras_clave in mapping.items():
            if key in titulo_tarea:
                stock_disponible = filtrar_por_empresa(
                    db.session.query(func.sum(Insumo.cantidad_actual)),
                    Insumo
                ).filter(
                    or_(*(Insumo.nombre.ilike(f'%{kw}%') for kw in palabras_clave))
                ).scalar() or 0
                
                if stock_disponible <= 0:
                    entidad = titulo_tarea.split(':')[-1].strip() if ':' in titulo_tarea else ''
                    if key not in agrupadas:
                        agrupadas[key] = {
                            'clave_principal': palabras_clave[0],
                            'sugeridos': ", ".join(palabras_clave[:3]),
                            'entidades': [entidad] if entidad else [],
                            'count': 1
                        }
                    else:
                        if entidad and entidad not in agrupadas[key]['entidades']:
                            agrupadas[key]['entidades'].append(entidad)
                        agrupadas[key]['count'] += 1
                break

    for key, data in agrupadas.items():
        if data['count'] > 1:
            ejemplos = ", ".join(data['entidades'][:2])
            mas = f" y {len(data['entidades']) - 2} más" if len(data['entidades']) > 2 else ""
            detalle = f"Requerido para {data['count']} registros ({ejemplos}{mas}). Stock disponible: 0 unidades."
            badge_texto = f"{data['count']} pendientes"
        else:
            elem = data['entidades'][0] if data['entidades'] else key
            detalle = f"Requerido para {elem}. Stock disponible: 0 unidades."
            badge_texto = elem

        alertas.append({
            'titulo': f"Sin Stock: {data['clave_principal']}",
            'detalle': detalle,
            'lote': badge_texto
        })

    return alertas


def obtener_tareas_sugeridas():
    """Motor de IA: genera sugerencias inteligentes y proactivas basadas en ciclo de vida y eventos."""
    today = datetime.now(timezone.utc).date()
    tareas = []
    
    # --- 1. Sugerencias para Cultivos ---
    lotes_agri = filtrar_por_empresa(LoteProduccion.query, LoteProduccion).filter_by(estado='En Crecimiento').all()
    for lote in lotes_agri:
        dias = (today - lote.fecha_siembra).days
        ciclo_est = (lote.especie.dias_ciclo_estimado if lote.especie and lote.especie.dias_ciclo_estimado else 90)
        
        # Última labor registrada
        ultima_labor = LaborCampo.query.filter_by(lote_id=lote.id).order_by(LaborCampo.fecha.desc()).first()
        dias_desde_labor = (today - ultima_labor.fecha).days if ultima_labor and ultima_labor.fecha else dias
        
        # A) ¿Lote listo para venta de plántulas?
        if lote.proposito == 'Venta Plantula' and dias >= ciclo_est:
            tareas.append({
                'titulo': f'Lote Maduro: {lote.codigo_lote}',
                'sub': f'{dias} días cumplidos. ¡Listo para cambiar a Disponible y vender!',
                'icon': 'bi-shop', 'color': 'success',
                'url': url_for('produccion.ver_lote', lote_id=lote.id)
            })
            continue

        # B) Fertilización inicial (Días 0 a 7 si no hay labor de nutrición)
        if 0 <= dias <= 7:
            has_fert = LaborCampo.query.filter(
                LaborCampo.lote_id == lote.id,
                LaborCampo.tipo_labor.ilike('%fertiliz%')
            ).first()
            if not has_fert:
                tareas.append({
                    'titulo': f'Fertilización Inicial: {lote.codigo_lote}',
                    'sub': f'Día {dias} de {lote.especie.nombre_comun if lote.especie else "cultivo"} (Enraizamiento)',
                    'icon': 'bi-droplet-half', 'color': 'primary',
                    'url': url_for('produccion.ver_lote', lote_id=lote.id)
                })

        # C) Control fitosanitario / plagas (Días 10 a 25)
        elif 10 <= dias <= 25 and dias_desde_labor >= 10:
            tareas.append({
                'titulo': f'Control Fitosanitario: {lote.codigo_lote}',
                'sub': f'Día {dias} - Inspección preventiva de plagas y hongos',
                'icon': 'bi-shield-check', 'color': 'warning',
                'url': url_for('produccion.ver_lote', lote_id=lote.id)
            })

        # D) Cosecha inminente por fecha estimada
        if lote.fecha_cosecha_est:
            dias_cosecha = (lote.fecha_cosecha_est - today).days
            if dias_cosecha <= 5:
                sub_txt = f'Faltan {dias_cosecha} días para recolectar' if dias_cosecha >= 0 else f'Fecha estimada superada por {abs(dias_cosecha)} días'
                tareas.append({
                    'titulo': f'Cosecha Requerida: {lote.codigo_lote}',
                    'sub': f'{sub_txt} ({lote.especie.nombre_comun if lote.especie else "Planta"})',
                    'icon': 'bi-basket', 'color': 'danger' if dias_cosecha < 0 else 'success',
                    'url': url_for('produccion.ver_lote', lote_id=lote.id)
                })

        # E) Lote con más de 25 días sin labores
        elif dias_desde_labor >= 25 and dias > 15:
            tareas.append({
                'titulo': f'Mantenimiento / Deshierbe: {lote.codigo_lote}',
                'sub': f'{dias_desde_labor} días sin registrar labores de campo',
                'icon': 'bi-scissors', 'color': 'secondary',
                'url': url_for('produccion.ver_lote', lote_id=lote.id)
            })

    # --- 2. Sugerencias para Animales ---
    animales = filtrar_por_empresa(LoteAnimal.query, LoteAnimal).filter_by(estado='Activo').all()
    for animal in animales:
        ultimo_e = EventoSanitario.query.filter_by(lote_animal_id=animal.id).order_by(EventoSanitario.fecha.desc()).first()
        dias_salud = (today - ultimo_e.fecha).days if ultimo_e and ultimo_e.fecha else 999
        
        if dias_salud > 30:
            tareas.append({
                'titulo': f'Chequeo Médico: {animal.nombre or animal.codigo}',
                'sub': f'{dias_salud if dias_salud < 900 else ">30"} días sin revisión veterinaria ({animal.especie})',
                'icon': 'bi-heart-pulse', 'color': 'danger',
                'url': url_for('pecuario.ver_animal', id=animal.id)
            })

    # --- 3. Sugerencias de Insumos Críticos ---
    insumos_agotados = filtrar_por_empresa(Insumo.query, Insumo).filter(
        Insumo.cantidad_actual <= Insumo.stock_minimo,
        Insumo.cantidad_actual >= 0
    ).limit(2).all()
    
    for ins in insumos_agotados:
        tareas.append({
            'titulo': f'Comprar Insumo: {ins.nombre}',
            'sub': f'Stock crítico ({ins.cantidad_actual} {ins.unidad.abreviatura if ins.unidad else "und"}). Punto de reorden alcanzado',
            'icon': 'bi-cart-plus', 'color': 'warning',
            'url': url_for('compras.nuevo_pedido')
        })
            
    return tareas[:6]


@dashboard_bp.route('/dashboard')
@login_required
def dashboard():
    from flask import session
    today = datetime.now(timezone.utc).date()
    
    # 1. KPI: Activos Vivos (Plantas en Crecimiento y Disponibles)
    total_plantas_crecimiento = filtrar_por_empresa(
        db.session.query(func.sum(LoteProduccion.cantidad_actual)), 
        LoteProduccion
    ).filter(LoteProduccion.estado.in_(['En Crecimiento', 'Disponible'])).scalar() or 0
    
    lotes_activos_count = filtrar_por_empresa(
        LoteProduccion.query, 
        LoteProduccion
    ).filter(LoteProduccion.estado.in_(['En Crecimiento', 'Disponible'])).count()

    valor_activos_agri = filtrar_por_empresa(db.session.query(
        func.sum(LoteProduccion.cantidad_actual * Especie.precio_venta_sugerido)
    ), LoteProduccion).join(Especie).filter(LoteProduccion.estado.in_(['En Crecimiento', 'Disponible'])).scalar() or 0
    
    valor_activos_pecu = filtrar_por_empresa(db.session.query(
        func.sum(LoteAnimal.cantidad_actual * RazaAnimal.valor_mercado_estimado)
    ), LoteAnimal).join(RazaAnimal).filter(LoteAnimal.estado == 'Activo').scalar() or 0
    
    valor_total_activos = valor_activos_agri + valor_activos_pecu

    # 2. KPI: Salud Financiera del Mes
    ingresos_mes = filtrar_por_empresa(db.session.query(func.sum(Venta.total)), Venta).filter(
        db.extract('month', Venta.fecha) == today.month,
        db.extract('year', Venta.fecha) == today.year,
        Venta.estado != 'Cancelada'
    ).scalar() or 0

    active_emp_id = None
    if current_user.is_authenticated:
        if current_user.es_superadmin:
            active_emp_id = session.get('superadmin_empresa_id')
        else:
            active_emp_id = current_user.empresa_id

    # Consumos de Insumos (agricola)
    q_insumos = db.session.query(func.sum(ConsumoInsumo.subtotal)).join(LaborCampo).join(LoteProduccion).filter(
        db.extract('month', LaborCampo.fecha) == today.month,
        db.extract('year', LaborCampo.fecha) == today.year
    )
    if active_emp_id:
        q_insumos = q_insumos.filter(LoteProduccion.empresa_id == int(active_emp_id))
    gastos_insumos = q_insumos.scalar() or 0

    q_pecuario = db.session.query(func.sum(ConsumoAnimal.costo_calculado)).join(LoteAnimal).filter(
        db.extract('month', ConsumoAnimal.fecha) == today.month,
        db.extract('year', ConsumoAnimal.fecha) == today.year
    )
    if active_emp_id:
        q_pecuario = q_pecuario.filter(LoteAnimal.empresa_id == int(active_emp_id))
    gastos_pecuario = q_pecuario.scalar() or 0

    q_medicos = db.session.query(func.sum(EventoSanitario.costo_servicio)).join(LoteAnimal).filter(
        db.extract('month', EventoSanitario.fecha) == today.month,
        db.extract('year', EventoSanitario.fecha) == today.year
    )
    if active_emp_id:
        q_medicos = q_medicos.filter(LoteAnimal.empresa_id == int(active_emp_id))
    servicios_medicos = q_medicos.scalar() or 0

    total_gastos_mes = (gastos_insumos or 0) + (gastos_pecuario or 0) + (servicios_medicos or 0)
    margen_mes = (ingresos_mes or 0) - total_gastos_mes

    # --- IA: ALERTAS DE REABASTECIMIENTO ---
    tareas_ia = obtener_tareas_sugeridas()
    alertas_compra = analizar_necesidades_insumos(tareas_ia)

    # 3. Semáforo de Progreso (Lotes en crecimiento y disponibles)
    lotes_crecimiento = filtrar_por_empresa(LoteProduccion.query, LoteProduccion).filter_by(
        estado='En Crecimiento'
    ).join(Especie).order_by(LoteProduccion.fecha_siembra.asc()).all()

    lotes_disponibles = filtrar_por_empresa(LoteProduccion.query, LoteProduccion).filter_by(
        estado='Disponible'
    ).join(Especie).order_by(LoteProduccion.fecha_siembra.desc()).all()

    lotes_para_semaforo = (lotes_crecimiento + lotes_disponibles)[:6]

    lotes_progreso_data = []
    for lote in lotes_para_semaforo:
        dias_estimados = lote.especie.dias_ciclo_estimado or 90
        dias_transcurridos = (today - lote.fecha_siembra).days
        
        if lote.estado == 'Disponible':
            progreso_pct = 100
            color = 'success'
        else:
            progreso_pct = min(max((dias_transcurridos / dias_estimados) * 100, 0), 100)
            color = 'danger' if progreso_pct >= 90 else ('warning' if progreso_pct >= 50 else 'primary')

        lotes_progreso_data.append({
            'lote_obj': lote,
            'dias_transcurridos': dias_transcurridos,
            'progreso_pct': int(progreso_pct),
            'color_estado': color
        })
        
    # 4. Alertas y Otros Contadores
    insumos_alerta = filtrar_por_empresa(Insumo.query, Insumo).filter(
        Insumo.cantidad_actual <= Insumo.stock_minimo, 
        Insumo.cantidad_actual > 0
    ).order_by(Insumo.cantidad_actual.asc()).limit(5).all()

    total_animales = filtrar_por_empresa(db.session.query(func.sum(LoteAnimal.cantidad_actual)), LoteAnimal).filter(LoteAnimal.estado == 'Activo').scalar() or 0
    
    # 5. Histórico para Gráficos (6 meses)
    meses_nombres = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
    chart_labels = []
    chart_data = []
    
    for i in range(5, -1, -1):
        m = today.month - i
        y = today.year
        if m <= 0:
            m += 12
            y -= 1
        
        label = f"{meses_nombres[m-1]} {str(y)[2:]}"
        total_v = filtrar_por_empresa(db.session.query(func.sum(Venta.total)), Venta).filter(
            db.extract('month', Venta.fecha) == m,
            db.extract('year', Venta.fecha) == y,
            Venta.estado != 'Cancelada'
        ).scalar() or 0
        chart_labels.append(label)
        chart_data.append(float(total_v or 0))

    # --- 6. MÉTRICAS PREDICTIVAS DE INTELIGENCIA ARTIFICIAL (HUD AI) ---
    ventas_ultimos_30d = filtrar_por_empresa(db.session.query(func.sum(Venta.total)), Venta).filter(
        Venta.fecha >= today - timedelta(days=30),
        Venta.estado != 'Cancelada'
    ).scalar() or (ingresos_mes or 0)
    proyeccion_ventas_30d = float(ventas_ultimos_30d) * 1.18

    total_lotes_monitoreados = len(lotes_para_semaforo)
    lotes_saludables = sum(1 for item in lotes_progreso_data if item['color_estado'] in ['success', 'primary'])
    indice_salud_vivero = int((lotes_saludables / total_lotes_monitoreados * 100)) if total_lotes_monitoreados > 0 else 98

    total_plantas_disponibles = filtrar_por_empresa(db.session.query(func.sum(LoteProduccion.cantidad_actual)), LoteProduccion).filter_by(estado='Disponible').scalar() or 0
    total_plantas_vivero = total_plantas_crecimiento + total_plantas_disponibles
    co2_captura_anual_toneladas = round((total_plantas_vivero * 22) / 1000.0, 1)

    lotes_quiebre_stock = filtrar_por_empresa(LoteProduccion.query, LoteProduccion).filter(
        LoteProduccion.estado == 'Disponible',
        LoteProduccion.cantidad_actual > 0,
        LoteProduccion.cantidad_actual <= 35
    ).limit(3).all()

    return render_template('dashboard.html',
                           total_plantas_crecimiento=int(total_plantas_crecimiento),
                           total_plantas_disponibles=int(total_plantas_disponibles),
                           lotes_activos_count=lotes_activos_count,
                           lotes_progreso=lotes_progreso_data,
                           insumos_alerta=insumos_alerta,
                           total_animales=int(total_animales),
                           valor_total_activos=valor_total_activos,
                           ingresos_mes=ingresos_mes,
                           margen_mes=margen_mes,
                           chart_labels=chart_labels,
                           chart_data=chart_data,
                           lotes_para_semaforo=lotes_para_semaforo, 
                           tareas_ia=tareas_ia,
                           alertas_compra=alertas_compra,
                           hoy=today,
                           proyeccion_ventas_30d=proyeccion_ventas_30d,
                           indice_salud_vivero=indice_salud_vivero,
                           co2_captura_anual_toneladas=co2_captura_anual_toneladas,
                           lotes_quiebre_stock=lotes_quiebre_stock,
                           total_insumos=filtrar_por_empresa(Insumo.query, Insumo).count(),
                           pedidos_pendientes=filtrar_por_empresa(PedidoCompra.query, PedidoCompra).filter_by(estado='Solicitado').count(),
                           total_especies=filtrar_por_empresa(Especie.query, Especie).count(),
                           proveedores=filtrar_por_empresa(Proveedor.query, Proveedor).all())
