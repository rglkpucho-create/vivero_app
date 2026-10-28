"""
Pruebas automatizadas para Facturación Electrónica DIAN y Pasarelas de Pago.
"""
from app import db
from app.models import Venta, DetalleVenta, Empresa, Cliente, LoteProduccion
from app.services.facturacion_electronica import FacturacionElectronicaService
from app.services.pasarela_pagos import PasarelaPagosService
from app.services.pdf_generator import generar_pdf_factura
from tests.conftest import login_as


def test_calculo_cufe_y_cadena_qr(app, test_data):
    """Verifica que el algoritmo SHA-384 de CUFE y el formato QR cumplan el Anexo 1.9 DIAN."""
    with app.app_context():
        empresa = Empresa.query.get(test_data['empresa_a_id'])
        cliente = Cliente.query.get(test_data['cliente_a_id'])
        
        venta = Venta(
            empresa_id=empresa.id,
            cliente_id=cliente.id,
            numero_factura="SETP-000001",
            subtotal=100000.0,
            impuestos=19000.0,
            total=119000.0,
            estado='Finalizada'
        )
        db.session.add(venta)
        db.session.commit()

        cufe = FacturacionElectronicaService.calcular_cufe(venta, empresa)
        assert len(cufe) == 96  # SHA-384 genera 96 caracteres hexadecimales
        assert isinstance(cufe, str)

        qr_cadena = FacturacionElectronicaService.generar_cadena_qr(venta, empresa, cufe)
        assert "NumFac=SETP-000001" in qr_cadena
        assert f"CUFE={cufe}" in qr_cadena
        assert "ValTotal=119000.00" in qr_cadena
        assert "https://catalogo-vpfe.dian.gov.co" in qr_cadena


def test_emision_factura_electronica_sandbox_y_pdf(app, test_data, client):
    """Verifica la emisión en modo Sandbox DIAN y que el PDF incorpore el bloque CUFE."""
    login_as(client, 'admin_a@test.com', 'Secret123!')
    
    with app.app_context():
        empresa = Empresa.query.get(test_data['empresa_a_id'])
        cliente = Cliente.query.get(test_data['cliente_a_id'])
        lote = LoteProduccion.query.get(test_data['lote_cultivo_id'])

        venta = Venta(
            empresa_id=empresa.id,
            cliente_id=cliente.id,
            numero_factura="FAC-E-001",
            subtotal=50000.0,
            total=50000.0,
            estado='Finalizada'
        )
        db.session.add(venta)
        db.session.flush()

        detalle = DetalleVenta(
            venta_id=venta.id,
            lote_id=lote.id,
            cantidad=5.0,
            precio_venta_unitario=10000.0,
            costo_produccion_unitario=4000.0,
            subtotal=50000.0
        )
        db.session.add(detalle)
        db.session.commit()
        venta_id = venta.id

    # Emitir mediante la ruta web POST
    resp = client.post(f'/venta/{venta_id}/emitir-fe', follow_redirects=True)
    assert resp.status_code == 200
    assert b"Factura Electr" in resp.data

    with app.app_context():
        v = Venta.query.get(venta_id)
        assert v.es_electronica is True
        assert v.estado_dian == 'EXITOSA'
        assert v.cufe is not None
        assert len(v.cufe) == 96
        assert v.fecha_emision_dian is not None

        # Verificar renderizado en PDF
        pdf_bytes = generar_pdf_factura(v)
        assert len(pdf_bytes) > 1000
        assert pdf_bytes.startswith(b"%PDF-")


def test_pasarela_pagos_sandbox_sesion_y_aprobacion(app, test_data, client):
    """Verifica la creación de sesión de pago y la aprobación mediante el simulador sandbox."""
    login_as(client, 'admin_a@test.com', 'Secret123!')

    with app.app_context():
        empresa = Empresa.query.get(test_data['empresa_a_id'])
        cliente = Cliente.query.get(test_data['cliente_a_id'])

        venta = Venta(
            empresa_id=empresa.id,
            cliente_id=cliente.id,
            numero_factura="FAC-PAY-001",
            subtotal=75000.0,
            total=75000.0,
            estado='Finalizada',
            estado_pago='PENDIENTE'
        )
        db.session.add(venta)
        db.session.commit()
        venta_id = venta.id

    # Iniciar pago online (redirecciona a checkout simulado)
    resp = client.get(f'/venta/{venta_id}/iniciar-pago-online', follow_redirects=True)
    assert resp.status_code == 200
    assert b"Simulador Sandbox de Pagos" in resp.data
    assert b"75,000" in resp.data

    # Aprobar el pago en el simulador
    resp_post = client.post(
        f'/venta/{venta_id}/checkout-simulado',
        data={'accion': 'aprobar', 'metodo': 'Nequi'},
        follow_redirects=True
    )
    assert resp_post.status_code == 200
    assert b"Pago aprobado con" in resp_post.data

    with app.app_context():
        v = Venta.query.get(venta_id)
        assert v.estado_pago == 'APROBADO'
        assert v.abono == 75000.0
        assert v.saldo == 0.0
        assert "Nequi" in v.metodo_pago
