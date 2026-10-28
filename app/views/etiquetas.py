import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from ..extensions import db
from ..models import LoteProduccion, Insumo, LoteAnimal
from .helpers import filtrar_por_empresa, get_or_404_empresa, obtener_empresa_activa

logger = logging.getLogger(__name__)

etiquetas_bp = Blueprint('etiquetas', __name__, url_prefix='/etiquetas')


@etiquetas_bp.route('/')
@login_required
def index():
    """Centro de generación e impresión de etiquetas con código de barras y QR."""
    lotes = filtrar_por_empresa(LoteProduccion.query, LoteProduccion).filter(
        LoteProduccion.estado.in_(['En Crecimiento', 'Listo para Venta', 'Cosechado']),
        LoteProduccion.cantidad_actual > 0
    ).order_by(LoteProduccion.codigo_lote).all()

    insumos = filtrar_por_empresa(Insumo.query, Insumo).filter(
        Insumo.cantidad_actual > 0
    ).order_by(Insumo.nombre).all()

    animales = filtrar_por_empresa(LoteAnimal.query, LoteAnimal).filter(
        LoteAnimal.cantidad_actual > 0
    ).order_by(LoteAnimal.codigo).all()

    empresa = obtener_empresa_activa()

    return render_template(
        'etiquetas/index.html',
        lotes=lotes,
        insumos=insumos,
        animales=animales,
        empresa=empresa
    )


@etiquetas_bp.route('/generar', methods=['POST'])
@login_required
def generar_etiquetas():
    """Genera la vista imprimible según el formato (rollo térmico u hoja adhesiva)."""
    formato = request.form.get('formato', 'rollo_50x30') # 'rollo_50x30', 'rollo_60x40', 'hoja_carta_30'
    tipo_origen = request.form.get('tipo_origen') # 'lote', 'insumo', 'animal', 'personalizado'
    item_id = request.form.get('item_id', type=int)
    cantidad_copias = request.form.get('cantidad_copias', 1, type=int)
    mostrar_precio = request.form.get('mostrar_precio') == '1'
    mostrar_qr = request.form.get('mostrar_qr') == '1'
    mostrar_barcode = request.form.get('mostrar_barcode', '1') == '1'

    cantidad_copias = max(1, min(500, cantidad_copias))

    titulo = ""
    subtitulo = ""
    codigo_barcode = ""
    precio = 0.0

    if tipo_origen == 'lote' and item_id:
        lote = get_or_404_empresa(LoteProduccion, item_id)
        titulo = lote.especie.nombre_comun if lote.especie else lote.codigo_lote
        subtitulo = lote.especie.nombre_cientifico if (lote.especie and lote.especie.nombre_cientifico) else f"Lote: {lote.codigo_lote}"
        codigo_barcode = lote.codigo_lote
        precio = lote.especie.precio_venta_sugerido if (lote.especie and lote.especie.precio_venta_sugerido) else (lote.costo_unitario * 1.5 if lote.costo_unitario else 5000.0)

    elif tipo_origen == 'insumo' and item_id:
        insumo = get_or_404_empresa(Insumo, item_id)
        titulo = insumo.nombre
        subtitulo = f"Ref: {insumo.codigo or 'General'}"
        codigo_barcode = insumo.codigo or f"INS-{insumo.id:04d}"
        precio = insumo.precio_venta or 0.0

    elif tipo_origen == 'animal' and item_id:
        animal = get_or_404_empresa(LoteAnimal, item_id)
        titulo = f"{animal.nombre or animal.codigo}"
        subtitulo = f"{animal.especie} - {animal.raza_rel.nombre if animal.raza_rel else ''}"
        codigo_barcode = animal.codigo or f"ANI-{animal.id:04d}"
        precio = animal.raza_rel.valor_mercado_estimado if (animal.raza_rel and animal.raza_rel.valor_mercado_estimado) else 150000.0

    else:
        titulo = request.form.get('titulo_personalizado', '').strip() or "Planta de Vivero"
        subtitulo = request.form.get('subtitulo_personalizado', '').strip() or "EcoSistem"
        codigo_barcode = request.form.get('codigo_personalizado', '').strip() or "AGRO-001"
        precio = float(request.form.get('precio_personalizado', 0))

    empresa = obtener_empresa_activa()

    etiquetas = [{
        'titulo': titulo,
        'subtitulo': subtitulo,
        'codigo_barcode': codigo_barcode,
        'precio': precio,
        'mostrar_precio': mostrar_precio,
        'mostrar_qr': mostrar_qr,
        'mostrar_barcode': mostrar_barcode
    }] * cantidad_copias

    return render_template(
        'etiquetas/imprimir.html',
        etiquetas=etiquetas,
        formato=formato,
        empresa=empresa
    )


@etiquetas_bp.route('/lote/<int:lote_id>')
@login_required
def imprimir_lote_directo(lote_id):
    """Atajo para imprimir etiquetas directamente desde un lote de cultivo."""
    lote = get_or_404_empresa(LoteProduccion, lote_id)
    empresa = obtener_empresa_activa()
    cant = min(100, max(1, lote.cantidad_actual or 10))

    etiquetas = [{
        'titulo': lote.especie.nombre_comun if lote.especie else lote.codigo_lote,
        'subtitulo': lote.especie.nombre_cientifico if (lote.especie and lote.especie.nombre_cientifico) else f"Lote: {lote.codigo_lote}",
        'codigo_barcode': lote.codigo_lote,
        'precio': lote.especie.precio_venta_sugerido if (lote.especie and lote.especie.precio_venta_sugerido) else 5000.0,
        'mostrar_precio': True,
        'mostrar_qr': True,
        'mostrar_barcode': True
    }] * cant

    return render_template(
        'etiquetas/imprimir.html',
        etiquetas=etiquetas,
        formato='rollo_50x30',
        empresa=empresa
    )


@etiquetas_bp.route('/insumo/<int:insumo_id>')
@login_required
def imprimir_insumo_directo(insumo_id):
    """Atajo para imprimir etiquetas directamente desde un insumo/mercancía."""
    insumo = get_or_404_empresa(Insumo, insumo_id)
    empresa = obtener_empresa_activa()
    cant = min(50, max(1, int(insumo.cantidad_actual or 5)))

    etiquetas = [{
        'titulo': insumo.nombre,
        'subtitulo': f"Ref: {insumo.codigo or 'General'}",
        'codigo_barcode': insumo.codigo or f"INS-{insumo.id:04d}",
        'precio': insumo.precio_venta or 0.0,
        'mostrar_precio': True,
        'mostrar_qr': False,
        'mostrar_barcode': True
    }] * cant

    return render_template(
        'etiquetas/imprimir.html',
        etiquetas=etiquetas,
        formato='rollo_50x30',
        empresa=empresa
    )
