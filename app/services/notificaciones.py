"""
Servicio de Notificaciones Automáticas por WhatsApp y Correo Electrónico — EcoSistem
Genera enlaces enriquecidos de WhatsApp y envía facturas en PDF por correo electrónico vía SMTP.
"""
import os
import smtplib
import logging
import urllib.parse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from datetime import datetime

from .pdf_generator import generar_pdf_factura

logger = logging.getLogger(__name__)


class NotificacionesService:

    @staticmethod
    def limpiar_telefono(telefono):
        """Limpia el número de celular dejándolo en formato estándar WhatsApp (ej: 573104567890)."""
        if not telefono:
            return ""
        # Quitar espacios, guiones, paréntesis y signos
        tel = ''.join(ch for ch in str(telefono) if ch.isdigit())
        if len(tel) == 10 and tel.startswith('3'):
            tel = '57' + tel
        return tel

    @classmethod
    def generar_url_whatsapp_factura(cls, venta, base_url=None):
        """
        Genera el enlace directo para enviar la factura comercial / DIAN al cliente por WhatsApp.
        """
        tel = cls.limpiar_telefono(venta.cliente.telefono if venta.cliente else None)
        empresa_nombre = venta.empresa.nombre if venta.empresa else "Vivero El Edén Forestal"
        cliente_nombre = venta.cliente.nombre if venta.cliente else "Estimado/a Cliente"

        lineas_items = []
        for d in (venta.detalles or []):
            if d.lote_origen:
                desc = d.lote_origen.especie.nombre_comun
            elif d.animal:
                desc = d.animal.nombre or d.animal.codigo
            elif d.insumo:
                desc = d.insumo.nombre
            else:
                desc = "Artículo"
            lineas_items.append(f"  • {desc} x{d.cantidad:g} (${d.subtotal:,.0f})")

        items_str = "\n".join(lineas_items) if lineas_items else "  • Compra en mostrador"

        mensaje = (
            f"🌱 *{empresa_nombre.upper()}*\n"
            f"¡Hola *{cliente_nombre}*! 🌿\n\n"
            f"Te compartimos el comprobante de tu compra con la Factura *#{venta.numero_factura}*:\n\n"
            f"📦 *Productos adquiridos:*\n{items_str}\n\n"
            f"💰 *Total Pagado:* ${venta.total:,.0f} COP\n"
            f"💳 *Método de Pago:* {venta.metodo_pago or 'Efectivo'}\n"
            f"📅 *Fecha:* {venta.fecha.strftime('%d/%m/%Y %I:%M %p') if venta.fecha else 'Hoy'}\n"
        )

        if venta.es_electronica and venta.cufe:
            mensaje += f"\n🏛️ *Factura Electrónica DIAN Validada*\nCUFE: `{venta.cufe[:20]}...`\n"

        mensaje += (
            f"\n¡Muchas gracias por cultivar el futuro con nosotros! 🍃\n"
            f"_{empresa_nombre}_"
        )

        codificado = urllib.parse.quote(mensaje)
        if tel:
            return f"https://api.whatsapp.com/send?phone={tel}&text={codificado}"
        return f"https://api.whatsapp.com/send?text={codificado}"

    @classmethod
    def generar_url_whatsapp_pedido(cls, pedido, nuevo_estado=None):
        """
        Genera enlace de WhatsApp para notificar cambios de estado en un Pedido Web.
        """
        tel = cls.limpiar_telefono(pedido.cliente.telefono if pedido.cliente else None)
        empresa_nombre = pedido.empresa.nombre if pedido.empresa else "Vivero El Edén Forestal"
        cliente_nombre = pedido.cliente.nombre if pedido.cliente else "Cliente"
        estado = nuevo_estado or pedido.estado or "En proceso"

        mensaje = (
            f"🌱 *{empresa_nombre.upper()}*\n"
            f"¡Hola *{cliente_nombre}*! 📦\n\n"
            f"Te informamos que tu solicitud de pedido *#{pedido.numero_factura}* se encuentra en estado: *{estado.upper()}*.\n\n"
            f"💰 *Total Pedido:* ${pedido.total:,.0f} COP\n"
            f"📍 *Entrega en:* {pedido.cliente.ciudad or pedido.cliente.direccion or 'Mostrador'}\n\n"
            f"Estamos preparando todo con el mayor cuidado para que tus plantas lleguen en perfecto estado. 🌿\n"
            f"Cualquier inquietud, estamos atentos por este mismo medio.\n\n"
            f"¡Gracias por tu preferencia!\n"
            f"_{empresa_nombre}_"
        )
        codificado = urllib.parse.quote(mensaje)
        if tel:
            return f"https://api.whatsapp.com/send?phone={tel}&text={codificado}"
        return f"https://api.whatsapp.com/send?text={codificado}"

    @classmethod
    def enviar_factura_email(cls, venta, email_destino=None, asunto=None, mensaje_extra=None):
        """
        Genera la factura en PDF y la envía como adjunto al correo del cliente vía SMTP.
        Si SMTP no está configurado, opera en modo Sandbox/Simulado registrando el evento.
        """
        destinatario = (email_destino or (venta.cliente.email if venta.cliente else None) or '').strip()
        if not destinatario or '@' not in destinatario:
            return {
                'success': False,
                'message': 'El cliente no tiene un correo electrónico válido registrado.'
            }

        empresa = venta.empresa
        empresa_nombre = empresa.nombre if empresa else "Vivero El Edén Forestal"
        asunto_email = asunto or f"Factura #{venta.numero_factura} — {empresa_nombre}"

        # 1. Generar PDF de la Factura en memoria
        try:
            pdf_bytes = generar_pdf_factura(venta)
        except Exception as e:
            logger.error(f"Error generando PDF para email: {e}")
            return {
                'success': False,
                'message': f'Error generando archivo PDF de la factura: {e}'
            }

        # 2. Configurar Mensaje MIME
        msg = MIMEMultipart('mixed')
        msg['Subject'] = asunto_email
        msg['To'] = destinatario
        
        remitente_nombre = empresa_nombre
        mail_sender = os.getenv('MAIL_DEFAULT_SENDER') or os.getenv('MAIL_USERNAME') or f"facturas@{urllib.parse.quote(empresa_nombre.lower().replace(' ', ''))}.com"
        msg['From'] = f"{remitente_nombre} <{mail_sender}>"

        # Cuerpo en HTML con diseño profesional
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f8fafc; color: #1e293b; margin: 0; padding: 20px; }}
                .container {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.08); border: 1px solid #e2e8f0; }}
                .header {{ background: linear-gradient(135deg, #064e3b 0%, #059669 100%); padding: 30px 25px; text-align: center; color: #ffffff; }}
                .header h1 {{ margin: 0; font-size: 22px; font-weight: 800; letter-spacing: -0.5px; }}
                .header p {{ margin: 6px 0 0 0; font-size: 13px; opacity: 0.9; }}
                .content {{ padding: 30px 25px; }}
                .badge-invoice {{ display: inline-block; background: #ecfdf5; color: #059669; border: 1px solid #a7f3d0; border-radius: 20px; padding: 4px 12px; font-weight: bold; font-size: 13px; margin-bottom: 15px; }}
                .summary-card {{ background: #f8fafc; border-radius: 8px; padding: 20px; border: 1px solid #e2e8f0; margin: 20px 0; }}
                .total-row {{ display: flex; justify-content: space-between; font-size: 20px; font-weight: 800; color: #064e3b; margin-top: 10px; padding-top: 10px; border-top: 2px dashed #cbd5e1; }}
                .footer {{ background: #f1f5f9; padding: 20px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{empresa_nombre.upper()}</h1>
                    <p>Comprobante Oficial de Compra • Factura #{venta.numero_factura}</p>
                </div>
                <div class="content">
                    <p>Apreciado/a <strong>{venta.cliente.nombre if venta.cliente else 'Cliente'}</strong>,</p>
                    <p>Adjunto a este correo encontrarás la factura digital correspondiente a tu compra realizada el <strong>{venta.fecha.strftime('%d/%m/%Y a las %I:%M %p') if venta.fecha else 'día de hoy'}</strong>.</p>
                    
                    <div class="summary-card">
                        <table style="width: 100%; font-size: 14px; line-height: 1.8;">
                            <tr><td><strong>Factura N°:</strong></td><td style="text-align: right;">#{venta.numero_factura}</td></tr>
                            <tr><td><strong>Método de Pago:</strong></td><td style="text-align: right;">{venta.metodo_pago or 'Efectivo'}</td></tr>
                            <tr><td><strong>Tipo de Operación:</strong></td><td style="text-align: right;">{venta.tipo_venta or 'Contado'}</td></tr>
                            <tr><td colspan="2"><div style="border-top: 1px dashed #cbd5e1; margin: 8px 0;"></div></td></tr>
                            <tr style="font-size: 18px; font-weight: bold; color: #064e3b;">
                                <td>TOTAL LIQUIDADO:</td>
                                <td style="text-align: right;">${venta.total:,.0f} COP</td>
                            </tr>
                        </table>
                    </div>

                    {f'<p style="background: #ecfdf5; border-left: 4px solid #059669; padding: 10px 15px; border-radius: 4px; font-size: 13px;"><em>{mensaje_extra}</em></p>' if mensaje_extra else ''}

                    <p style="font-size: 13px; color: #475569;">
                        El archivo PDF adjunto contiene el detalle completo de tus productos e información fiscal.
                    </p>
                </div>
                <div class="footer">
                    <p style="margin: 0;">{empresa_nombre} • Sistema de Gestión EcoSistem</p>
                    <p style="margin: 4px 0 0 0;">Si tienes alguna pregunta, puedes comunicarte al teléfono: {empresa.telefono if empresa else '3104567890'}.</p>
                </div>
            </div>
        </body>
        </html>
        """

        msg.attach(MIMEText(html_body, 'html'))

        # Adjuntar PDF
        adjunto = MIMEApplication(pdf_bytes, _subtype="pdf")
        adjunto.add_header('Content-Disposition', 'attachment', filename=f"Factura_{venta.numero_factura}.pdf")
        msg.attach(adjunto)

        # 3. Envío SMTP real o Simulado
        mail_server = os.getenv('MAIL_SERVER')
        mail_port = int(os.getenv('MAIL_PORT', 587))
        mail_user = os.getenv('MAIL_USERNAME')
        mail_password = os.getenv('MAIL_PASSWORD')
        mail_use_tls = os.getenv('MAIL_USE_TLS', 'true').lower() in ('true', '1', 'yes')

        if mail_server and mail_user and mail_password:
            try:
                server = smtplib.SMTP(mail_server, mail_port, timeout=10)
                if mail_use_tls:
                    server.starttls()
                server.login(mail_user, mail_password)
                server.send_message(msg)
                server.quit()
                logger.info(f"Factura #{venta.numero_factura} enviada por correo a {destinatario} vía SMTP.")
                return {
                    'success': True,
                    'modo': 'SMTP',
                    'destinatario': destinatario,
                    'message': f'Factura enviada exitosamente a {destinatario}.'
                }
            except Exception as e:
                logger.error(f"Fallo al enviar correo vía SMTP ({mail_server}:{mail_port}): {e}")
                return {
                    'success': False,
                    'message': f'Error en el servidor de correo SMTP: {e}'
                }
        else:
            # Modo Simulado / Sandbox (Desarrollo local sin servidor SMTP externo configurado)
            logger.info(f"[SIMULACIÓN EMAIL] Factura #{venta.numero_factura} lista para {destinatario}. PDF generado ({len(pdf_bytes)} bytes).")
            return {
                'success': True,
                'modo': 'SANDBOX_SIMULADO',
                'destinatario': destinatario,
                'message': f'Correo generado exitosamente para {destinatario} (Modo Simulado / Sandbox).'
            }
