import pytest
from datetime import datetime, timezone, timedelta, date
from app.extensions import db
from app.models import (
    Empresa, Usuario, Cliente, Rol, Venta, DetalleVenta,
    LoteProduccion, Especie, Insumo, UnidadMedida,
    Cotizacion, DetalleCotizacion, AbonoVenta, CajaTurno, MovimientoCaja
)
from app.services.pdf_generator import generar_pdf_cotizacion, generar_pdf_recibo_abono


@pytest.fixture
def test_setup(app):
    """Configura empresa, usuario, cliente e inventario de prueba."""
    with app.app_context():
        empresa = Empresa(
            nombre="EcoSistem Vivero SAS",
            nit_rut="901234567-1",
            telefono="3159998877",
            email="contacto@ecosistem.co",
            ciudad="Bucaramanga"
        )
        db.session.add(empresa)
        db.session.flush()

        rol_admin = Rol.query.filter_by(nombre='Administrador').first()
        if not rol_admin:
            rol_admin = Rol(nombre='Administrador')
            db.session.add(rol_admin)
            db.session.flush()

        usuario = Usuario(
            nombre_completo="Carlos Asesor",
            email="vendedor@ecosistem.co",
            empresa_id=empresa.id,
            rol_id=rol_admin.id,
            activo=True
        )
        usuario.set_password("pass123")
        db.session.add(usuario)

        cliente = Cliente(
            empresa_id=empresa.id,
            nombre="Constructora Paisajismo Verde",
            tipo_documento="NIT",
            documento="900888777-2",
            telefono="3104567890",
            email="compras@paisajismoverde.co",
            ciudad="Bucaramanga"
        )
        db.session.add(cliente)

        especie = Especie(
            empresa_id=empresa.id,
            nombre_comun="Palma Areca",
            nombre_cientifico="Dypsis lutescens",
            precio_venta_sugerido=45000.0
        )
        db.session.add(especie)
        db.session.flush()

        lote = LoteProduccion(
            empresa_id=empresa.id,
            especie_id=especie.id,
            codigo_lote="LOT-ARECA-01",
            cantidad_sembrada=100,
            cantidad_actual=80,
            costo_total=1600000.0,
            estado="Listo para Venta"
        )
        db.session.add(lote)

        um = UnidadMedida.query.filter_by(nombre='Bolsa').first()
        if not um:
            um = UnidadMedida(nombre='Bolsa', abreviatura='bls')
            db.session.add(um)
            db.session.flush()

        insumo = Insumo(
            empresa_id=empresa.id,
            nombre="Sustrato Especial Macetas",
            unidad_medida_id=um.id,
            tipo="Sustrato",
            cantidad_actual=50.0,
            costo_promedio=12000.0,
            precio_venta=25000.0
        )
        db.session.add(insumo)

        db.session.commit()

        return {
            'empresa_id': empresa.id,
            'usuario_id': usuario.id,
            'cliente_id': cliente.id,
            'lote_id': lote.id,
            'insumo_id': insumo.id
        }


def test_modulo_cotizaciones_completo(client, app, test_setup):
    """
    Prueba integral de Cotizaciones:
    1. Creación de cotización proforma.
    2. Adición de ítems (lote de plantas e insumos).
    3. Validación de recálculo de subtotal y descuentos.
    4. Generación y descarga del PDF de cotización.
    5. Conversión en 1 clic a Venta POS.
    """
    with app.app_context():
        usuario = db.session.get(Usuario, test_setup['usuario_id'])
        with client.session_transaction() as sess:
            sess['_user_id'] = str(usuario.id)
            sess['_fresh'] = True

        # 1. Crear Cotización
        resp_crear = client.post('/cotizaciones/nueva', data={
            'cliente_id': test_setup['cliente_id'],
            'validez_dias': 20,
            'observaciones': 'Oferta especial para proyecto de paisajismo corporativo.'
        }, follow_redirects=True)
        assert resp_crear.status_code == 200

        cot = Cotizacion.query.filter_by(empresa_id=test_setup['empresa_id']).first()
        assert cot is not None
        assert cot.numero_cotizacion.startswith('COT-')
        assert cot.estado == 'Borrador'

        # 2. Agregar Planta (Lote)
        resp_item1 = client.post(f'/cotizaciones/{cot.id}/agregar-item', data={
            'tipo_item': 'lote',
            'item_id': test_setup['lote_id'],
            'cantidad': '10',
            'precio_unitario': '45000',
            'descuento_pct': '10' # 10% descuento
        }, follow_redirects=True)
        assert resp_item1.status_code == 200

        # 3. Agregar Insumo
        resp_item2 = client.post(f'/cotizaciones/{cot.id}/agregar-item', data={
            'tipo_item': 'insumo',
            'item_id': test_setup['insumo_id'],
            'cantidad': '5',
            'precio_unitario': '25000',
            'descuento_pct': '0'
        }, follow_redirects=True)
        assert resp_item2.status_code == 200

        # Verificar recálculo
        # Item 1: 10 * 45000 * 0.9 = 405,000
        # Item 2: 5 * 25000 = 125,000
        # Total: 530,000
        db.session.refresh(cot)
        assert len(cot.detalles) == 2
        assert cot.total == 530000.0

        # 4. Generar y Descargar PDF Proforma
        resp_pdf = client.get(f'/cotizaciones/{cot.id}/pdf')
        assert resp_pdf.status_code == 200
        assert resp_pdf.mimetype == 'application/pdf'
        assert len(resp_pdf.data) > 1000

        # Probar función de generación directa
        pdf_bytes = generar_pdf_cotizacion(cot)
        assert pdf_bytes.startswith(b'%PDF')

        # 5. Generar Enlace de WhatsApp
        resp_wa = client.get(f'/cotizaciones/{cot.id}/whatsapp-url')
        assert resp_wa.status_code == 200
        data_wa = resp_wa.get_json()
        assert data_wa['success'] is True
        assert 'api.whatsapp.com' in data_wa['whatsapp_url']
        assert cot.numero_cotizacion in data_wa['whatsapp_url']

        # 6. Convertir Cotización en Venta POS (1 Clic)
        resp_convertir = client.post(f'/cotizaciones/{cot.id}/convertir-venta', follow_redirects=True)
        assert resp_convertir.status_code == 200

        db.session.refresh(cot)
        assert cot.estado == 'Convertida'
        assert cot.venta_id is not None

        venta_asoc = db.session.get(Venta, cot.venta_id)
        assert venta_asoc is not None
        assert venta_asoc.total == cot.total
        assert len(venta_asoc.detalles) == 2


def test_modulo_cartera_y_abonos_credito(client, app, test_setup):
    """
    Prueba integral de Cartera y Ventas a Crédito:
    1. Venta a crédito con abono inicial y saldo pendiente.
    2. Apertura de turno de caja.
    3. Registro de abonos parciales con afectación contable.
    4. Generación y descarga de Recibo de Caja PDF.
    5. Liquidación total de la deuda (saldo = 0).
    """
    with app.app_context():
        usuario = db.session.get(Usuario, test_setup['usuario_id'])
        with client.session_transaction() as sess:
            sess['_user_id'] = str(usuario.id)
            sess['_fresh'] = True

        # 1. Crear y finalizar una venta a crédito
        ahora = datetime.now(timezone.utc)
        vence = (ahora + timedelta(days=30)).date()

        venta = Venta(
            empresa_id=test_setup['empresa_id'],
            numero_factura="FAC-CRED-001",
            cliente_id=test_setup['cliente_id'],
            usuario_id=usuario.id,
            fecha=ahora,
            fecha_vencimiento=vence,
            tipo_venta='Credito',
            estado='Finalizada',
            subtotal=1000000.0,
            descuento=0.0,
            impuestos=0.0,
            total=1000000.0,
            abono=200000.0,     # Abono inicial
            saldo=800000.0,     # Saldo pendiente
            metodo_pago='Crédito (Abono Inicial: $200,000)'
        )
        db.session.add(venta)
        db.session.commit()

        # 2. Abrir turno de caja
        caja = CajaTurno(
            empresa_id=test_setup['empresa_id'],
            usuario_apertura_id=usuario.id,
            monto_apertura=100000.0,
            fecha_apertura=ahora,
            estado='Abierta'
        )
        db.session.add(caja)
        db.session.commit()

        # 3. Registrar Abono Parcial #1 de $300,000 en Efectivo
        resp_abono1 = client.post('/cartera/abono', data={
            'venta_id': venta.id,
            'monto': '300000',
            'metodo_pago': 'Efectivo',
            'notas': 'Primer abono en efectivo por el contratista'
        }, follow_redirects=True)
        assert resp_abono1.status_code == 200

        db.session.refresh(venta)
        assert venta.abono == 500000.0 # 200k + 300k
        assert venta.saldo == 500000.0 # 800k - 300k

        # Verificar que se creó el AbonoVenta con número RC
        abono_reg = AbonoVenta.query.filter_by(venta_id=venta.id).first()
        assert abono_reg is not None
        assert abono_reg.numero_recibo.startswith('RC-')
        assert abono_reg.monto == 300000.0
        assert abono_reg.saldo_nuevo == 500000.0

        # Verificar que el pago en efectivo impactó la caja abierta
        mov_caja = MovimientoCaja.query.filter_by(caja_turno_id=caja.id).first()
        assert mov_caja is not None
        assert mov_caja.tipo == 'Ingreso'
        assert mov_caja.monto == 300000.0

        # 4. Descargar Recibo de Caja PDF
        resp_recibo_pdf = client.get(f'/cartera/recibo/{abono_reg.id}/pdf')
        assert resp_recibo_pdf.status_code == 200
        assert resp_recibo_pdf.mimetype == 'application/pdf'
        assert len(resp_recibo_pdf.data) > 1000

        # Test directo de generación
        pdf_recibo = generar_pdf_recibo_abono(abono_reg)
        assert pdf_recibo.startswith(b'%PDF')

        # 5. Consultar Estado de Cuenta del Cliente
        resp_estado = client.get(f'/cartera/cliente/{test_setup["cliente_id"]}')
        assert resp_estado.status_code == 200
        assert b"Constructora Paisajismo Verde" in resp_estado.data

        # 6. Registrar Abono Final de $500,000 para Saldo Cero
        resp_abono2 = client.post('/cartera/abono', data={
            'venta_id': venta.id,
            'monto': '500000',
            'metodo_pago': 'Transferencia',
            'notas': 'Liquidación total saldo pendiente'
        }, follow_redirects=True)
        assert resp_abono2.status_code == 200

        db.session.refresh(venta)
        assert venta.saldo == 0.0
        assert venta.abono == 1000000.0
