import pytest
from app.extensions import db
from app.models import Venta, DetalleVenta, LoteProduccion, Insumo, LoteAnimal
from tests.conftest import login_as


def test_flujo_completo_pos_venta_mixta_con_animales_y_pdf(client, app, test_data):
    """
    Test End-to-End del Punto de Venta (POS):
    1. Iniciar venta Borrador para Cliente A
    2. Agregar Cosecha Propia (Plantas)
    3. Agregar Insumo / Mercancía
    4. Agregar Lote Animal (Pecuario)
    5. Finalizar Venta: verificar deducción de stock y transición de animal a 'Vendido'
    6. Descargar Factura Comercial en PDF (validar byte stream y HTTP 200)
    """
    login_as(client, 'admin_a@test.com', 'Secret123!')

    # 1. Crear Venta en Borrador
    res_crear = client.post('/venta/nueva', data={
        'cliente_id': test_data['cliente_a_id']
    }, follow_redirects=True)
    assert res_crear.status_code == 200

    with app.app_context():
        venta = Venta.query.filter_by(
            empresa_id=test_data['empresa_a_id'], 
            estado='Borrador'
        ).first()
        assert venta is not None
        venta_id = venta.id
        num_factura = venta.numero_factura

    # 2. Agregar Planta (Cosecha Propia)
    res_item_planta = client.post(f'/venta/{venta_id}/agregar', data={
        'lote_id': str(test_data['lote_cultivo_id']),
        'cantidad': '5',
        'precio_unitario': '12000'
    }, follow_redirects=True)
    assert res_item_planta.status_code == 200

    # 3. Agregar Insumo (Mercancía)
    res_item_insumo = client.post(f'/venta/{venta_id}/agregar', data={
        'insumo_id': str(test_data['insumo_id']),
        'cantidad': '2',
        'precio_unitario': '40000'
    }, follow_redirects=True)
    assert res_item_insumo.status_code == 200

    # 4. Agregar Lote Animal (Pecuario)
    res_item_animal = client.post(f'/venta/{venta_id}/agregar', data={
        'animal_id': str(test_data['lote_animal_id']),
        'cantidad': '1',
        'precio_unitario': '3800000'
    }, follow_redirects=True)
    assert res_item_animal.status_code == 200

    # Validar que los 3 items están en el detalle
    with app.app_context():
        v = db.session.get(Venta, venta_id)
        assert len(v.detalles) == 3
        # 5*12,000 + 2*40,000 + 1*3,800,000 = 60,000 + 80,000 + 3,800,000 = 3,940,000
        assert v.total == 3940000.0

    # 5. Finalizar Venta en el POS
    res_finalizar = client.post(f'/venta/{venta_id}/finalizar', data={
        'metodo_pago': 'Transferencia',
        'tipo_venta': 'Contado'
    }, follow_redirects=True)
    assert res_finalizar.status_code == 200

    with app.app_context():
        v_final = db.session.get(Venta, venta_id)
        assert v_final.estado == 'Finalizada'
        assert v_final.metodo_pago == 'Transferencia'

        # Verificar reducción de stock de la planta: 80 - 5 = 75
        lote_cult = db.session.get(LoteProduccion, test_data['lote_cultivo_id'])
        assert lote_cult.cantidad_actual == 75

        # Verificar reducción de stock del insumo: 30 - 2 = 28
        ins = db.session.get(Insumo, test_data['insumo_id'])
        assert ins.cantidad_actual == 28.0

        # Verificar animal: cantidad pasa a 0 y estado cambia a 'Vendido'
        animal = db.session.get(LoteAnimal, test_data['lote_animal_id'])
        assert animal.cantidad_actual == 0
        assert animal.estado == 'Vendido'

    # 6. Descarga y Generación de Factura Comercial PDF
    res_pdf = client.get(f'/venta/{venta_id}/factura-pdf')
    assert res_pdf.status_code == 200
    assert res_pdf.content_type == 'application/pdf'
    assert len(res_pdf.data) > 1000
    # Comprobar firma binaria estándar de un archivo PDF (%PDF)
    assert res_pdf.data.startswith(b'%PDF')
