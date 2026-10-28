"""
Módulo de Tienda Web Pública — Catálogo E-Commerce, Carrito y Pedidos por WhatsApp
"""
import logging
from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, abort
from flask_login import login_required, current_user
from ..models import (
    Empresa, Insumo, LoteProduccion, Especie, Cliente, Venta, DetalleVenta, TestimonioWeb
)
from ..extensions import db
from .helpers import guardar_imagen, registrar_auditoria, obtener_empresa_activa, empresa_id_actual
import urllib.parse
import random
from app import csrf

logger = logging.getLogger(__name__)
tienda_bp = Blueprint('tienda', __name__)


# ==========================================================
# 0. PANEL DE CONTROL: CONFIGURAR SITIO WEB DEL VIVERO
# ==========================================================
@tienda_bp.route('/tienda/mi-sitio', methods=['GET'])
@login_required
def configurar_tienda():
    """
    Panel de configuración del sitio web y catálogo online del vivero.
    Permite personalizar portada/banner, logo, colores, textos, whatsapp y visibilidad.
    """
    empresa_id_param = request.args.get('empresa_id', type=int)
    if empresa_id_param and (getattr(current_user, 'es_superadmin', False) or current_user.empresa_id == empresa_id_param):
        empresa = db.session.get(Empresa, empresa_id_param)
    else:
        empresa = obtener_empresa_activa()

    if not empresa:
        flash('No se encontró ninguna empresa asociada.', 'warning')
        return redirect(url_for('dashboard.index'))

    # Estadísticas para el panel
    total_plantas = LoteProduccion.query.filter_by(
        empresa_id=empresa.id,
        estado='Disponible'
    ).filter(LoteProduccion.cantidad_actual > 0).count()

    total_insumos = Insumo.query.filter_by(
        empresa_id=empresa.id
    ).filter(Insumo.cantidad_actual > 0, Insumo.precio_venta > 0).count()

    url_publica = url_for('tienda.index', empresa_id=empresa.id, _external=True)
    url_catalogo = url_for('tienda.catalogo', empresa_id=empresa.id, _external=True)

    testimonios = TestimonioWeb.query.filter_by(
        empresa_id=empresa.id
    ).order_by(TestimonioWeb.fecha.desc()).all()

    return render_template(
        'tienda/configurar.html',
        empresa=empresa,
        total_plantas=total_plantas,
        total_insumos=total_insumos,
        url_publica=url_publica,
        url_catalogo=url_catalogo,
        testimonios=testimonios
    )


@tienda_bp.route('/tienda/mi-sitio/guardar', methods=['POST'])
@login_required
def guardar_configuracion_tienda():
    """
    Guarda los cambios estéticos y de información pública del vivero.
    """
    empresa_id_form = request.form.get('empresa_id', type=int)
    if empresa_id_form and (getattr(current_user, 'es_superadmin', False) or current_user.empresa_id == empresa_id_form):
        empresa = db.session.get(Empresa, empresa_id_form)
    else:
        empresa = obtener_empresa_activa()

    if not empresa:
        flash('Empresa no encontrada.', 'danger')
        return redirect(url_for('dashboard.index'))

    try:
        if current_user.es_admin or current_user.es_superadmin:
            empresa.nombre = request.form.get('nombre', empresa.nombre).strip()
            empresa.razon_social = request.form.get('razon_social', empresa.razon_social).strip()

        empresa.slogan = request.form.get('slogan', '').strip()
        empresa.descripcion_web = request.form.get('descripcion_web', '').strip()
        empresa.sobre_nosotros_largo = request.form.get('sobre_nosotros_largo', '').strip()
        empresa.servicios_texto = request.form.get('servicios_texto', '').strip()
        empresa.color_tema = request.form.get('color_tema', '#10b981').strip()
        empresa.whatsapp_pedidos = request.form.get('whatsapp_pedidos', '').strip()
        empresa.telefono = request.form.get('telefono', empresa.telefono).strip()
        empresa.email = request.form.get('email', empresa.email).strip()
        empresa.direccion = request.form.get('direccion', empresa.direccion).strip()
        empresa.ciudad = request.form.get('ciudad', empresa.ciudad).strip()
        empresa.horario_atencion = request.form.get('horario_atencion', '').strip()

        # Redes Sociales
        empresa.instagram_url = request.form.get('instagram_url', '').strip()
        empresa.facebook_url = request.form.get('facebook_url', '').strip()
        empresa.tiktok_url = request.form.get('tiktok_url', '').strip()

        # Métricas de Impacto
        empresa.anios_experiencia = request.form.get('anios_experiencia', '10+ Años').strip()
        empresa.plantas_entregadas = request.form.get('plantas_entregadas', '50,000+').strip()
        empresa.hectareas_o_variedades = request.form.get('hectareas_o_variedades', '150+ Especies').strip()

        # Opciones de Publicación
        empresa.mostrar_precios_web = True if request.form.get('mostrar_precios_web') == 'on' else False
        empresa.mostrar_catalogo_web = True if request.form.get('mostrar_catalogo_web') == 'on' else False
        empresa.tienda_activa = True if request.form.get('tienda_activa') == 'on' else False

        # Imagen de Banner / Portada
        if 'banner' in request.files and request.files['banner'].filename:
            ruta_banner = guardar_imagen(request.files['banner'], 'banners')
            if ruta_banner:
                empresa.banner_url = ruta_banner

        # Imagen de Logo
        if 'logo' in request.files and request.files['logo'].filename:
            ruta_logo = guardar_imagen(request.files['logo'], 'logos')
            if ruta_logo:
                empresa.logo_url = ruta_logo

        db.session.commit()
        registrar_auditoria('ACTUALIZAR', 'TiendaWeb', f'Sitio web personalizado de {empresa.nombre}')
        flash('¡La configuración de tu página web y catálogo ha sido actualizada con éxito!', 'success')

    except Exception as e:
        db.session.rollback()
        logger.error(f'Error actualizando sitio web de empresa: {e}')
        flash(f'Error al guardar configuración: {e}', 'danger')

    return redirect(url_for('tienda.configurar_tienda'))


@tienda_bp.route('/tienda/ver')
@login_required
def ver_mi_tienda():
    """Redirige directamente al sitio público del vivero del usuario o empresa activa."""
    empresa_id_param = request.args.get('empresa_id', type=int)
    if empresa_id_param and (getattr(current_user, 'es_superadmin', False) or current_user.empresa_id == empresa_id_param):
        return redirect(url_for('tienda.index', empresa_id=empresa_id_param))

    empresa = obtener_empresa_activa()
    if not empresa:
        flash('No hay empresa configurada.', 'warning')
        return redirect(url_for('dashboard.index'))
    return redirect(url_for('tienda.index', empresa_id=empresa.id))


@tienda_bp.route('/tienda/mi-catalogo')
@login_required
def ver_mi_catalogo():
    """Redirige directamente al catálogo digital del vivero del usuario o empresa activa."""
    empresa_id_param = request.args.get('empresa_id', type=int)
    if empresa_id_param and (getattr(current_user, 'es_superadmin', False) or current_user.empresa_id == empresa_id_param):
        return redirect(url_for('tienda.catalogo', empresa_id=empresa_id_param))

    empresa = obtener_empresa_activa()
    if not empresa:
        flash('No hay empresa configurada.', 'warning')
        return redirect(url_for('dashboard.index'))
    return redirect(url_for('tienda.catalogo', empresa_id=empresa.id))


@tienda_bp.route('/tienda/<int:empresa_id>')
def index(empresa_id):
    # Cargar la empresa y validar que tenga su licencia activa
    empresa = Empresa.query.get_or_404(empresa_id)
    if not empresa.licencia_activa or not empresa.tienda_activa:
        return render_template('licencia_suspendida.html'), 403

    # Cargar conteo de plantas e insumos disponibles para mostrar en la web principal
    plantas = LoteProduccion.query.join(Especie).filter(
        LoteProduccion.empresa_id == empresa_id,
        LoteProduccion.estado == 'Disponible',
        LoteProduccion.proposito == 'Venta Plantula',
        LoteProduccion.cantidad_actual > 0
    ).order_by(Especie.nombre_comun).all()

    productos = Insumo.query.filter(
        Insumo.empresa_id == empresa_id,
        Insumo.cantidad_actual > 0,
        db.or_(Insumo.tipo != 'Insumo', Insumo.precio_venta > 0)
    ).order_by(Insumo.nombre).all()

    testimonios = TestimonioWeb.query.filter_by(
        empresa_id=empresa_id,
        aprobado=True
    ).order_by(TestimonioWeb.fecha.desc()).all()

    return render_template(
        'tienda/index.html',
        empresa=empresa,
        plantas=plantas,
        productos=productos,
        testimonios=testimonios
    )


@tienda_bp.route('/tienda/<int:empresa_id>/catalogo')
def catalogo(empresa_id):
    """Página dedicada y exclusiva del Catálogo Digital de plantas e insumos."""
    empresa = Empresa.query.get_or_404(empresa_id)
    if not empresa.licencia_activa or not empresa.tienda_activa:
        return render_template('licencia_suspendida.html'), 403

    # Si el vivero decidió desactivar la publicación del catálogo, redirigir a la web principal
    if not empresa.mostrar_catalogo_web:
        flash('El catálogo digital no se encuentra publicado en este momento.', 'info')
        return redirect(url_for('tienda.index', empresa_id=empresa.id))

    plantas = LoteProduccion.query.join(Especie).filter(
        LoteProduccion.empresa_id == empresa_id,
        LoteProduccion.estado == 'Disponible',
        LoteProduccion.proposito == 'Venta Plantula',
        LoteProduccion.cantidad_actual > 0
    ).order_by(Especie.nombre_comun).all()

    productos = Insumo.query.filter(
        Insumo.empresa_id == empresa_id,
        Insumo.cantidad_actual > 0,
        db.or_(Insumo.tipo != 'Insumo', Insumo.precio_venta > 0)
    ).order_by(Insumo.nombre).all()

    return render_template(
        'tienda/catalogo.html',
        empresa=empresa,
        plantas=plantas,
        productos=productos
    )



@tienda_bp.route('/tienda/<int:empresa_id>/pedido', methods=['POST'])
@csrf.exempt
def crear_pedido_web(empresa_id):
    empresa = Empresa.query.get_or_404(empresa_id)
    if not empresa.licencia_activa:
        return jsonify({'success': False, 'error': 'La tienda del vivero se encuentra inactiva.'}), 403

    data = request.json
    if not data:
        return jsonify({'success': False, 'error': 'Datos inválidos.'}), 400

    nombre = data.get('nombre', '').strip()[:100]
    documento = data.get('documento', '').strip()[:30]
    telefono = data.get('telefono', '').strip()[:30]
    email = data.get('email', '').strip().lower()[:100]
    direccion = data.get('direccion', '').strip()[:300]
    items = data.get('items', [])

    if not nombre or not telefono or not items or not isinstance(items, list) or len(items) > 50:
        return jsonify({'success': False, 'error': 'Datos de contacto y lista válida de productos son obligatorios.'}), 400

    try:
        # 1. Crear o asociar Cliente
        cliente = None
        if email:
            cliente = Cliente.query.filter_by(empresa_id=empresa_id, email=email).first()
        if not cliente and telefono:
            cliente = Cliente.query.filter_by(empresa_id=empresa_id, telefono=telefono).first()
        
        if not cliente:
            cliente = Cliente(
                empresa_id=empresa_id,
                nombre=nombre,
                documento=documento or f"WEB-{int(datetime.now().timestamp())}",
                telefono=telefono,
                email=email,
                direccion=direccion
            )
            db.session.add(cliente)
            db.session.flush() # Para obtener cliente.id

        metodo_pago = data.get('metodo_pago', 'WhatsApp Express')
        # 2. Iniciar la Venta en estado 'Pedido Web' para gestión y posterior facturación en POS
        venta = Venta(
            empresa_id=empresa_id,
            numero_factura=f"WEB-{int(datetime.now().timestamp())}",
            cliente_id=cliente.id,
            usuario_id=None, # None indica que provino del canal web público
            estado='Pedido Web',
            observaciones=f"Pedido Catálogo Web | Pago: {metodo_pago} | Entrega: {direccion} | Tel: {telefono}" if direccion else f"Pedido Catálogo Web | Pago: {metodo_pago} | Tel: {telefono}",
            total=0.0
        )
        db.session.add(venta)
        db.session.flush() # Para obtener venta.id

        total_venta = 0.0
        items_resumen = []

        # 3. Procesar ítems del pedido y validar stocks
        for item in items:
            if not isinstance(item, dict):
                continue
            tipo = item.get('type') # 'lote' o 'insumo'
            try:
                item_id = int(item.get('id', 0))
                cantidad = float(item.get('cantidad', 1))
            except (ValueError, TypeError):
                continue

            if cantidad <= 0 or cantidad > 10000:
                continue

            if tipo == 'lote':
                lote = LoteProduccion.query.get(item_id)
                if not lote or lote.empresa_id != empresa_id or lote.estado != 'Disponible':
                    raise Exception(f"La planta seleccionada ya no está disponible.")
                
                if lote.cantidad_actual < cantidad:
                    raise Exception(f"Stock insuficiente para: {lote.especie.nombre_comun}. Disponible: {lote.cantidad_actual}")

                precio_venta = lote.especie.precio_venta_sugerido or 0.0
                costo_prod = lote.costo_total / lote.cantidad_actual if lote.cantidad_actual else 0.0
                subtotal = cantidad * precio_venta

                detalle = DetalleVenta(
                    venta_id=venta.id,
                    lote_id=lote.id,
                    insumo_id=None,
                    cantidad=cantidad,
                    precio_venta_unitario=precio_venta,
                    costo_produccion_unitario=costo_prod,
                    subtotal=subtotal,
                    ganancia=subtotal - (cantidad * costo_prod)
                )
                db.session.add(detalle)
                total_venta += subtotal
                items_resumen.append({
                    'nombre': lote.especie.nombre_comun,
                    'cantidad': cantidad,
                    'subtotal': subtotal
                })

            elif tipo == 'insumo':
                insumo = Insumo.query.get(item_id)
                if not insumo or insumo.empresa_id != empresa_id:
                    raise Exception(f"El artículo comercial seleccionado ya no existe.")
                
                if insumo.cantidad_actual < cantidad:
                    raise Exception(f"Stock insuficiente para: {insumo.nombre}. Disponible: {insumo.cantidad_actual}")

                precio_venta = insumo.precio_venta or 0.0
                costo_unit = insumo.costo_promedio or 0.0
                subtotal = cantidad * precio_venta

                detalle = DetalleVenta(
                    venta_id=venta.id,
                    lote_id=None,
                    insumo_id=insumo.id,
                    cantidad=cantidad,
                    precio_venta_unitario=precio_venta,
                    costo_produccion_unitario=costo_unit,
                    subtotal=subtotal,
                    ganancia=subtotal - (cantidad * costo_unit)
                )
                db.session.add(detalle)
                total_venta += subtotal
                items_resumen.append({
                    'nombre': insumo.nombre,
                    'cantidad': cantidad,
                    'subtotal': subtotal
                })

        if not items_resumen:
            raise Exception("No se procesaron productos válidos en el pedido.")

        # 4. Actualizar total de la venta
        venta.total = total_venta
        db.session.commit()

        # 5. Generar link de WhatsApp para coordinar pago y entrega
        # Mensaje formateado para el vivero
        empresa_telefono = empresa.whatsapp_pedidos or empresa.telefono or ""
        telefono_limpio = ''.join(c for c in empresa_telefono if c.isdigit())
        
        texto_pedido = f"🌱 *¡Hola {empresa.nombre}!* Acabo de realizar un pedido web:\n\n"
        texto_pedido += f"👤 *Cliente:* {nombre}\n"
        texto_pedido += f"📞 *Teléfono:* {telefono}\n"
        if direccion:
            texto_pedido += f"📍 *Dirección de Entrega:* {direccion}\n"
        texto_pedido += f"📄 *Código Pedido:* #{venta.numero_factura}\n\n"
        texto_pedido += "🛍️ *Detalle del Pedido:*\n"
        
        for item_r in items_resumen:
            texto_pedido += f"• {item_r['nombre']} x{item_r['cantidad']:g} - ${item_r['subtotal']:,.0f}\n"
            
        texto_pedido += f"\n💰 *Total Estimado:* ${total_venta:,.0f}\n\n"
        texto_pedido += "👉 Quedo atento/a para coordinar el método de pago y la entrega. ¡Muchas gracias!"
        
        mensaje_codificado = urllib.parse.quote(texto_pedido)
        whatsapp_url = f"https://api.whatsapp.com/send?phone={telefono_limpio}&text={mensaje_codificado}"

        return jsonify({
            'success': True,
            'venta_id': venta.id,
            'numero_factura': venta.numero_factura,
            'total': total_venta,
            'whatsapp_url': whatsapp_url
        })

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error procesando pedido web: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400


@tienda_bp.route('/tienda/pedido/exito/<int:venta_id>')
def pedido_exito(venta_id):
    venta = Venta.query.get_or_404(venta_id)
    empresa = Empresa.query.get_or_404(venta.empresa_id)
    
    # Re-generar link de WhatsApp por si el cliente desea re-intentar el clic
    empresa_telefono = empresa.whatsapp_pedidos or empresa.telefono or ""
    telefono_limpio = ''.join(c for c in empresa_telefono if c.isdigit())
    
    texto_pedido = f"🌱 *¡Hola {empresa.nombre}!* Acabo de realizar un pedido web:\n\n"
    texto_pedido += f"👤 *Cliente:* {venta.cliente.nombre}\n"
    texto_pedido += f"📞 *Teléfono:* {venta.cliente.telefono}\n"
    if venta.cliente.direccion:
        texto_pedido += f"📍 *Dirección de Entrega:* {venta.cliente.direccion}\n"
    texto_pedido += f"📄 *Código Pedido:* #{venta.numero_factura}\n\n"
    texto_pedido += "🛍️ *Detalle del Pedido:*\n"
    
    for d in venta.detalles:
        nombre_item = d.lote_origen.especie.nombre_comun if d.lote_id else d.insumo.nombre
        texto_pedido += f"• {nombre_item} x{int(d.cantidad)} - ${d.subtotal:,.0f}\n"
        
    texto_pedido += f"\n💰 *Total Estimado:* ${venta.total:,.0f}\n\n"
    texto_pedido += "👉 Quedo atento/a para coordinar el método de pago y la entrega. ¡Muchas gracias!"
    
    mensaje_codificado = urllib.parse.quote(texto_pedido)
    whatsapp_url = f"https://api.whatsapp.com/send?phone={telefono_limpio}&text={mensaje_codificado}"

    return render_template(
        'tienda/exito.html',
        venta=venta,
        empresa=empresa,
        whatsapp_url=whatsapp_url
    )


@tienda_bp.route('/tienda/pedidos')
@login_required
def ver_pedidos_tienda():
    """Redirecciona a la sección oficial de Pedidos Web del sistema POS."""
    return redirect(url_for('ventas.lista_pedidos_web'))


# ==========================================================
# 5. GESTIÓN DE TESTIMONIOS Y CALIFICACIONES DE CLIENTES
# ==========================================================

@tienda_bp.route('/tienda/<int:empresa_id>/testimonio', methods=['POST'])
@csrf.exempt
def nuevo_testimonio(empresa_id):
    """
    Permite a los visitantes o clientes dejar una calificación (1-5 estrellas) y opinión
    sobre las plantas y el servicio recibido del vivero.
    """
    empresa = Empresa.query.get_or_404(empresa_id)
    if not empresa.licencia_activa or not empresa.tienda_activa:
        return jsonify({'success': False, 'message': 'Tienda inactiva'}), 403

    nombre = request.form.get('nombre_cliente', '').strip()
    proyecto = request.form.get('proyecto_o_ciudad', '').strip() or 'Cliente Verificado'
    comentario = request.form.get('comentario', '').strip()
    
    try:
        calificacion = int(request.form.get('calificacion', 5))
        if calificacion < 1 or calificacion > 5:
            calificacion = 5
    except (ValueError, TypeError):
        calificacion = 5

    if not nombre or not comentario:
        flash('Por favor escribe tu nombre y tu comentario para publicar tu calificación.', 'warning')
        return redirect(url_for('tienda.index', empresa_id=empresa_id) + '#testimonios')

    colores = ['#10b981', '#3b82f6', '#f59e0b', '#8b5cf6', '#ec4899', '#06b6d4', '#14b8a6']
    avatar_color = random.choice(colores)

    testimonio = TestimonioWeb(
        empresa_id=empresa_id,
        nombre_cliente=nombre[:100],
        proyecto_o_ciudad=proyecto[:150],
        calificacion=calificacion,
        comentario=comentario,
        aprobado=True,
        avatar_color=avatar_color
    )
    db.session.add(testimonio)
    db.session.commit()

    flash('¡Muchas gracias por tu calificación! Tu opinión ha sido publicada exitosamente en nuestro sitio web.', 'success')
    return redirect(url_for('tienda.index', empresa_id=empresa_id) + '#testimonios')


@tienda_bp.route('/tienda/mi-sitio/testimonio/manual', methods=['POST'])
@login_required
def crear_testimonio_manual():
    """
    Permite al vivero registrar una reseña que recibió por WhatsApp, correo o en persona.
    """
    empresa = obtener_empresa_activa()
    if not empresa:
        flash('No se encontró empresa.', 'danger')
        return redirect(url_for('tienda.configurar_tienda'))

    nombre = request.form.get('nombre_cliente', '').strip()
    proyecto = request.form.get('proyecto_o_ciudad', '').strip() or 'Cliente Verificado'
    comentario = request.form.get('comentario', '').strip()
    try:
        calificacion = int(request.form.get('calificacion', 5))
        if calificacion < 1 or calificacion > 5:
            calificacion = 5
    except (ValueError, TypeError):
        calificacion = 5

    if not nombre or not comentario:
        flash('El nombre y comentario son obligatorios.', 'warning')
        return redirect(url_for('tienda.configurar_tienda') + '#testimonios-admin')

    colores = ['#10b981', '#3b82f6', '#f59e0b', '#8b5cf6', '#ec4899']
    nuevo = TestimonioWeb(
        empresa_id=empresa.id,
        nombre_cliente=nombre,
        proyecto_o_ciudad=proyecto,
        calificacion=calificacion,
        comentario=comentario,
        aprobado=True,
        avatar_color=random.choice(colores)
    )
    db.session.add(nuevo)
    db.session.commit()
    flash('Testimonio agregado correctamente al sitio web.', 'success')
    return redirect(url_for('tienda.configurar_tienda') + '#testimonios-admin')


@tienda_bp.route('/tienda/testimonio/<int:testimonio_id>/eliminar', methods=['POST'])
@login_required
def eliminar_testimonio(testimonio_id):
    """Elimina una reseña."""
    testimonio = db.session.get(TestimonioWeb, testimonio_id)
    if not testimonio:
        flash('Testimonio no encontrado.', 'warning')
        return redirect(url_for('tienda.configurar_tienda'))

    if not (getattr(current_user, 'es_superadmin', False) or current_user.empresa_id == testimonio.empresa_id):
        abort(403)

    db.session.delete(testimonio)
    db.session.commit()
    flash('La reseña ha sido eliminada del sitio web.', 'info')
    return redirect(url_for('tienda.configurar_tienda') + '#testimonios-admin')


@tienda_bp.route('/tienda/testimonio/<int:testimonio_id>/toggle-aprobado', methods=['POST'])
@login_required
def toggle_aprobado_testimonio(testimonio_id):
    """Muestra u oculta una reseña en la web."""
    testimonio = db.session.get(TestimonioWeb, testimonio_id)
    if not testimonio:
        flash('Testimonio no encontrado.', 'warning')
        return redirect(url_for('tienda.configurar_tienda'))

    if not (getattr(current_user, 'es_superadmin', False) or current_user.empresa_id == testimonio.empresa_id):
        abort(403)

    testimonio.aprobado = not testimonio.aprobado
    db.session.commit()
    estado = "visible" if testimonio.aprobado else "oculto"
    flash(f'El testimonio ahora está {estado} en tu sitio web.', 'success')
    return redirect(url_for('tienda.configurar_tienda') + '#testimonios-admin')


# ==========================================================
# 6. ASISTENTE DE IA AGRÓNOMO VIRTUAL (BIOASESOR AI v3.0)
# ==========================================================

@tienda_bp.route('/tienda/<int:empresa_id>/ia-asesor', methods=['POST'])
@csrf.exempt
def ia_asesor_agronomo(empresa_id):
    """
    Motor inteligente de IA Agrónoma para la web pública y catálogo (BioAsesor AI v3.0).
    Soporta LLM Gemini con fallback a Motor Cognitivo Agronómico Local.
    Responde consultas de fitopatología, cálculo de terreno/densidad, climas colombianos,
    protocolos de siembra y vincula productos en tiempo real con stock real.
    """
    empresa = Empresa.query.get_or_404(empresa_id)
    if not empresa.licencia_activa or not empresa.tienda_activa:
        return jsonify({'success': False, 'respuesta': 'El servicio de IA no está disponible en este momento.'}), 403

    data = request.json or {}
    pregunta = data.get('mensaje', '').strip()

    if not pregunta:
        return jsonify({
            'success': True,
            'respuesta': f'🌱 ¡Hola! Soy **BioAsesor AI v3.0**, el especialista agronómico virtual de **{empresa.nombre}**. ¿En qué proyecto, cultivo o terreno te puedo orientar hoy? (Ej: árboles para cerca viva, frutales, cálculo de plantas por hectárea, hojas amarillas o cuidados de siembra).',
            'items_sugeridos': [],
            'chips_sugeridos': [
                '🌲 Cercas vivas y linderos',
                '🍊 Frutales injertados',
                '📐 Calcular plantas para mi terreno',
                '🩺 Hojas amarillas o plagas'
            ]
        })

    # Consultar inventario real disponible de la empresa
    plantas_disp = LoteProduccion.query.join(Especie).filter(
        LoteProduccion.empresa_id == empresa_id,
        LoteProduccion.estado == 'Disponible',
        LoteProduccion.proposito == 'Venta Plantula',
        LoteProduccion.cantidad_actual > 0
    ).all()

    insumos_disp = Insumo.query.filter(
        Insumo.empresa_id == empresa_id,
        Insumo.cantidad_actual > 0,
        db.or_(Insumo.tipo != 'Insumo', Insumo.precio_venta > 0)
    ).all()

    from app.services.ia_asesor import responder_consulta_agronomica
    respuesta_texto, sugeridos, chips = responder_consulta_agronomica(
        pregunta, empresa, plantas_disp, insumos_disp
    )

    return jsonify({
        'success': True,
        'respuesta': respuesta_texto,
        'items_sugeridos': sugeridos,
        'chips_sugeridos': chips
    })


