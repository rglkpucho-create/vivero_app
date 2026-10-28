"""
Servicio de Pasarelas de Pago Online para EcoSistem ERP.
Soporta:
1. Modo SANDBOX / SIMULADOR DE COBRO: Cobro interactivo con Nequi, Daviplata, PSE y Tarjeta de Crédito sin costo ni contratos.
2. Wompi (Bancolombia): Generación de firmas criptográficas de integridad SHA-256 y Webhooks automáticos.
3. Mercado Pago: Creación de preferencias de pago y webhooks IPN.
"""

import hashlib
import logging
from datetime import datetime, timezone
import requests
from flask import url_for
from app import db

logger = logging.getLogger(__name__)

class PasarelaPagosService:
    """Gestor unificado de cobros electrónicos y pasarelas de pago."""

    @staticmethod
    def generar_referencia(venta):
        """Genera una referencia única de transacción para la pasarela."""
        timestamp = int(datetime.now(timezone.utc).timestamp())
        return f"ECO-{venta.empresa_id or 1}-{venta.id}-{timestamp}"

    @classmethod
    def crear_sesion_pago(cls, venta):
        """
        Inicia una sesión de pago online para la venta.
        Retorna (exito: bool, url_pago: str, referencia: str)
        """
        empresa = venta.empresa
        if not empresa:
            return False, "", "Sin empresa asignada"

        referencia = venta.referencia_pago or cls.generar_referencia(venta)
        venta.referencia_pago = referencia
        venta.pasarela_pago = (empresa.pasarela_predeterminada or "SANDBOX").upper()
        db.session.commit()

        # 1. Modo SANDBOX (Simulador local autónomo)
        if venta.pasarela_pago == "SANDBOX" or not (empresa.wompi_public_key or empresa.mercadopago_access_token):
            url_checkout = url_for("ventas.checkout_simulado", venta_id=venta.id)
            return True, url_checkout, referencia

        # 2. Conector Wompi (Bancolombia)
        elif venta.pasarela_pago == "WOMPI":
            return cls._crear_sesion_wompi(venta, empresa, referencia)

        # 3. Conector Mercado Pago
        elif venta.pasarela_pago == "MERCADOPAGO":
            return cls._crear_sesion_mercadopago(venta, empresa, referencia)

        else:
            url_checkout = url_for("ventas.checkout_simulado", venta_id=venta.id)
            return True, url_checkout, referencia

    @classmethod
    def _crear_sesion_wompi(cls, venta, empresa, referencia):
        """Genera el enlace de checkout con firma de integridad para Wompi."""
        monto_centavos = int(round(float(venta.total or 0.0) * 100))
        moneda = "COP"

        # Cálculo de la firma de integridad SHA-256 (Anexo Wompi)
        # Cadena: referencia + monto_en_centavos + moneda + integrity_secret
        cadena_firma = f"{referencia}{monto_centavos}{moneda}{empresa.wompi_integrity_secret or ''}"
        firma_integridad = hashlib.sha256(cadena_firma.encode("utf-8")).hexdigest()

        url_retorno = url_for("ventas.ver_venta", venta_id=venta.id, _external=True)

        url_wompi = (
            f"https://checkout.wompi.co/p/?public-key={empresa.wompi_public_key}&"
            f"currency={moneda}&amount-in-cents={monto_centavos}&reference={referencia}&"
            f"signature:integrity={firma_integridad}&redirect-url={url_retorno}"
        )
        return True, url_wompi, referencia

    @classmethod
    def _crear_sesion_mercadopago(cls, venta, empresa, referencia):
        """Genera una preferencia de pago en Mercado Pago."""
        if not empresa.mercadopago_access_token:
            # Fallback a sandbox
            return True, url_for("ventas.checkout_simulado", venta_id=venta.id), referencia

        url_api = "https://api.mercadopago.com/checkout/preferences"
        headers = {
            "Authorization": f"Bearer {empresa.mercadopago_access_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "items": [
                {
                    "title": f"Venta #{venta.numero_factura or venta.id} - {empresa.nombre}",
                    "quantity": 1,
                    "currency_id": "COP",
                    "unit_price": float(venta.total)
                }
            ],
            "external_reference": referencia,
            "back_urls": {
                "success": url_for("ventas.ver_venta", venta_id=venta.id, _external=True),
                "failure": url_for("ventas.ver_venta", venta_id=venta.id, _external=True),
                "pending": url_for("ventas.ver_venta", venta_id=venta.id, _external=True)
            },
            "auto_return": "approved"
        }
        try:
            resp = requests.post(url_api, headers=headers, json=payload, timeout=10)
            if resp.status_code in (200, 201):
                data = resp.json()
                init_point = data.get("init_point") or data.get("sandbox_init_point")
                return True, init_point, referencia
            else:
                logger.warning(f"Error creando preferencia Mercado Pago: {resp.text}")
                return True, url_for("ventas.checkout_simulado", venta_id=venta.id), referencia
        except Exception as e:
            logger.error(f"Fallo conexión Mercado Pago: {e}")
            return True, url_for("ventas.checkout_simulado", venta_id=venta.id), referencia

    @staticmethod
    def aprobar_pago(venta, pasarela="SANDBOX", id_transaccion=None, metodo="Online"):
        """Registra la aprobación exitosa de un pago y actualiza la venta."""
        venta.estado_pago = "APROBADO"
        venta.pasarela_pago = pasarela
        venta.id_transaccion_pasarela = id_transaccion or f"TRANS-{int(datetime.now(timezone.utc).timestamp())}"
        venta.metodo_pago = f"Pago Online ({metodo})"
        venta.abono = venta.total
        venta.saldo = 0.0
        db.session.commit()
        return True
