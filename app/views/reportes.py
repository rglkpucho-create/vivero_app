"""
Módulo de Reportes Financieros y Contables — EcoSistem
Genera reportes ejecutivos en pantalla y exportación de Libros de Ventas, Compras y Kardex a Excel (.xlsx).
"""
import logging
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, Response, flash, redirect, url_for
from flask_login import login_required, current_user

from ..models import Venta, PedidoCompra, Insumo, LoteProduccion, LoteAnimal
from .helpers import filtrar_por_empresa, safe_float
from ..services.excel_exporter import ExcelExporterService

logger = logging.getLogger(__name__)
reportes_bp = Blueprint('reportes', __name__)


@reportes_bp.route('/reportes')
@login_required
def index_reportes():
    """
    Panel Principal de Reportes y Centro de Descarga Contable a Excel.
    """
    empresa = current_user.empresa if hasattr(current_user, 'empresa') else None
    
    # Métricas para tarjetas de resumen
    ventas_q = filtrar_por_empresa(Venta.query, Venta).filter_by(estado='Finalizada')
    total_ventas = sum(v.total or 0.0 for v in ventas_q.all())
    
    compras_q = filtrar_por_empresa(PedidoCompra.query, PedidoCompra)
    total_compras = sum((getattr(c, 'total_estimado', 0.0) or getattr(c, 'total', 0.0) or 0.0) for c in compras_q.all())
    
    # Inventario
    insumos = filtrar_por_empresa(Insumo.query, Insumo).all()
    valor_insumos_costo = sum((i.cantidad_actual or 0.0) * (i.costo_promedio or 0.0) for i in insumos)
    
    cultivos = filtrar_por_empresa(LoteProduccion.query, LoteProduccion).filter(LoteProduccion.estado != 'Finalizado').all()
    valor_cultivos_costo = sum(l.costo_total or 0.0 for l in cultivos)
    
    animales = filtrar_por_empresa(LoteAnimal.query, LoteAnimal).filter(LoteAnimal.estado != 'Vendido').all()
    valor_animales_costo = sum(a.costo_acumulado or 0.0 for a in animales)
    
    gran_total_inventario = valor_insumos_costo + valor_cultivos_costo + valor_animales_costo

    return render_template(
        'reportes/index.html',
        empresa=empresa,
        total_ventas=total_ventas,
        total_compras=total_compras,
        gran_total_inventario=gran_total_inventario,
        hoy=datetime.now().strftime('%Y-%m-%d')
    )


@reportes_bp.route('/reportes/ventas/excel')
@login_required
def exportar_ventas_excel():
    """Descarga el Libro de Ventas en formato Excel (.xlsx)."""
    empresa = current_user.empresa
    f_ini_str = request.args.get('fecha_inicio')
    f_fin_str = request.args.get('fecha_fin')
    metodo = request.args.get('metodo_pago')

    query = filtrar_por_empresa(Venta.query, Venta).filter_by(estado='Finalizada')

    f_ini = None
    f_fin = None
    if f_ini_str:
        try:
            f_ini = datetime.strptime(f_ini_str, '%Y-%m-%d')
            query = query.filter(Venta.fecha >= f_ini)
        except Exception:
            pass

    if f_fin_str:
        try:
            f_fin = datetime.strptime(f_fin_str + ' 23:59:59', '%Y-%m-%d %H:%M:%S')
            query = query.filter(Venta.fecha <= f_fin)
        except Exception:
            pass

    if metodo and metodo != 'TODOS':
        query = query.filter(Venta.metodo_pago.ilike(f'%{metodo}%'))

    ventas = query.order_by(Venta.fecha.desc()).all()

    try:
        excel_io = ExcelExporterService.generar_libro_ventas(
            empresa=empresa,
            ventas=ventas,
            fecha_inicio=f_ini,
            fecha_fin=f_fin
        )
        nombre_archivo = f"Libro_Ventas_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        return Response(
            excel_io.getvalue(),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={nombre_archivo}"}
        )
    except Exception as e:
        logger.error(f"Error generando Excel de ventas: {e}")
        flash(f"Error generando reporte de ventas: {e}", "danger")
        return redirect(url_for('reportes.index_reportes'))


@reportes_bp.route('/reportes/compras/excel')
@login_required
def exportar_compras_excel():
    """Descarga el Libro de Compras en formato Excel (.xlsx)."""
    empresa = current_user.empresa
    f_ini_str = request.args.get('fecha_inicio')
    f_fin_str = request.args.get('fecha_fin')

    query = filtrar_por_empresa(PedidoCompra.query, PedidoCompra)

    f_ini = None
    f_fin = None
    if f_ini_str:
        try:
            f_ini = datetime.strptime(f_ini_str, '%Y-%m-%d').date()
            query = query.filter(PedidoCompra.fecha_solicitud >= f_ini)
        except Exception:
            pass

    if f_fin_str:
        try:
            f_fin = datetime.strptime(f_fin_str, '%Y-%m-%d').date()
            query = query.filter(PedidoCompra.fecha_solicitud <= f_fin)
        except Exception:
            pass

    compras = query.order_by(PedidoCompra.fecha_solicitud.desc()).all()

    try:
        excel_io = ExcelExporterService.generar_libro_compras(
            empresa=empresa,
            compras=compras,
            fecha_inicio=f_ini,
            fecha_fin=f_fin
        )
        nombre_archivo = f"Libro_Compras_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        return Response(
            excel_io.getvalue(),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={nombre_archivo}"}
        )
    except Exception as e:
        logger.error(f"Error generando Excel de compras: {e}")
        flash(f"Error generando reporte de compras: {e}", "danger")
        return redirect(url_for('reportes.index_reportes'))


@reportes_bp.route('/reportes/inventario/excel')
@login_required
def exportar_inventario_excel():
    """Descarga el Kardex Valorizado de Inventario en formato Excel (.xlsx)."""
    empresa = current_user.empresa

    insumos = filtrar_por_empresa(Insumo.query, Insumo).order_by(Insumo.nombre).all()
    cultivos = filtrar_por_empresa(LoteProduccion.query, LoteProduccion).filter(LoteProduccion.estado != 'Finalizado').all()
    animales = filtrar_por_empresa(LoteAnimal.query, LoteAnimal).filter(LoteAnimal.estado != 'Vendido').all()

    try:
        excel_io = ExcelExporterService.generar_kardex_inventario_valorizado(
            empresa=empresa,
            insumos=insumos,
            lotes_cultivo=cultivos,
            lotes_animal=animales
        )
        nombre_archivo = f"Kardex_Inventario_Valorizado_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        return Response(
            excel_io.getvalue(),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={nombre_archivo}"}
        )
    except Exception as e:
        logger.error(f"Error generando Excel de inventario: {e}")
        flash(f"Error generando kardex de inventario: {e}", "danger")
        return redirect(url_for('reportes.index_reportes'))
