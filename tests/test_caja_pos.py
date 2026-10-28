import pytest
from app.extensions import db
from app.models import Venta, CajaTurno, MovimientoCaja
from tests.conftest import login_as


def test_flujo_completo_caja_pos_apertura_movimientos_cierre_y_comprobante(client, app, test_data):
    """
    Test End-to-End del Módulo de Caja POS (Turnos, Arqueo X y Cierre Z):
    1. Verificar que /caja muestre la vista de Apertura cuando no hay turno activo.
    2. Abrir turno de caja con base inicial en efectivo ($150,000).
    3. Realizar una venta en el POS y verificar vinculación automática al turno activo.
    4. Registrar un egreso menor de efectivo ($20,000 para flete/limpieza).
    5. Registrar un ingreso menor de efectivo ($30,000 de sencillo adicional).
    6. Verificar cálculo en vivo de Arqueo X (Efectivo Esperado).
    7. Realizar Cierre Z con conteo físico ($210,000) y calcular sobrante/faltante.
    8. Consultar comprobante térmico de cierre Z y el historial de turnos.
    """
    login_as(client, 'admin_a@test.com', 'Secret123!')

    # 1. Sin turno abierto: debe mostrar pantalla de apertura
    res_get_caja = client.get('/caja')
    assert res_get_caja.status_code == 200
    assert b"Apertura de Turno de Caja" in res_get_caja.data

    # 2. Abrir turno de caja con base de $150,000
    res_abrir = client.post('/caja/abrir', data={
        'monto_apertura': '150000',
        'observaciones_apertura': 'Turno de prueba automatizado'
    }, follow_redirects=True)
    assert res_abrir.status_code == 200
    assert b"Panel de Control de Caja" in res_abrir.data

    with app.app_context():
        turno = CajaTurno.query.filter_by(
            empresa_id=test_data['empresa_a_id'], 
            estado='Abierta'
        ).first()
        assert turno is not None
        assert turno.monto_apertura == 150000.0
        turno_id = turno.id

    # 3. Crear y finalizar una venta en efectivo en el POS
    res_crear_v = client.post('/venta/nueva', data={
        'cliente_id': test_data['cliente_a_id']
    }, follow_redirects=True)
    assert res_crear_v.status_code == 200

    with app.app_context():
        venta = Venta.query.filter_by(
            empresa_id=test_data['empresa_a_id'], 
            estado='Borrador'
        ).first()
        venta_id = venta.id

    # Agregar producto (Insumo)
    res_add = client.post(f'/venta/{venta_id}/agregar', data={
        'insumo_id': str(test_data['insumo_id']),
        'cantidad': '1',
        'precio_unitario': '50000'
    }, follow_redirects=True)
    assert res_add.status_code == 200

    # Finalizar venta en efectivo
    res_fin = client.post(f'/venta/{venta_id}/finalizar', data={
        'metodo_pago': 'Efectivo',
        'tipo_venta': 'Contado'
    }, follow_redirects=True)
    assert res_fin.status_code == 200

    with app.app_context():
        v = db.session.get(Venta, venta_id)
        assert v.estado == 'Finalizada'
        assert v.caja_turno_id == turno_id
        assert v.total == 50000.0

    # 4. Registrar Egreso menor ($20,000)
    res_egreso = client.post('/caja/movimiento', data={
        'tipo': 'Egreso',
        'monto': '20000',
        'concepto': 'Compra de bolsas y cinta de embalaje',
        'categoria': 'Gasto menor'
    }, follow_redirects=True)
    assert res_egreso.status_code == 200

    # 5. Registrar Ingreso menor ($30,000)
    res_ingreso = client.post('/caja/movimiento', data={
        'tipo': 'Ingreso',
        'monto': '30000',
        'concepto': 'Ingreso de monedas para sencillo',
        'categoria': 'Base adicional'
    }, follow_redirects=True)
    assert res_ingreso.status_code == 200

    # 6. Validar cálculo de Arqueo X:
    # Base (150,000) + Venta Efectivo (50,000) + Ingreso (30,000) - Egreso (20,000) = $210,000 esperado
    with app.app_context():
        t_activo = db.session.get(CajaTurno, turno_id)
        totales = t_activo.calcular_totales_actuales()
        assert totales['base'] == 150000.0
        assert totales['ventas']['efectivo'] == 50000.0
        assert totales['total_ingresos'] == 30000.0
        assert totales['total_egresos'] == 20000.0
        assert totales['efectivo_esperado'] == 210000.0

    # 7. Realizar Cierre de Turno Z:
    # Digitar conteo físico exacto de $210,000 (Caja Cuadrada, diff = 0)
    res_cierre = client.post('/caja/cerrar', data={
        'monto_cierre_efectivo': '210000',
        'observaciones_cierre': 'Cierre de turno cuadrado a satisfacción'
    }, follow_redirects=True)
    assert res_cierre.status_code == 200
    assert b"CIERRE-Z-" in res_cierre.data

    with app.app_context():
        t_cerrado = db.session.get(CajaTurno, turno_id)
        assert t_cerrado.estado == 'Cerrada'
        assert t_cerrado.fecha_cierre is not None
        assert t_cerrado.total_ventas_efectivo == 50000.0
        assert t_cerrado.efectivo_esperado == 210000.0
        assert t_cerrado.monto_cierre_efectivo == 210000.0
        assert t_cerrado.diferencia_efectivo == 0.0
        assert t_cerrado.comprobante_numero.startswith('CIERRE-Z-')

    # 8. Consultar Comprobante Térmico de Cierre Z
    res_comp = client.get(f'/caja/turno/{turno_id}/comprobante')
    assert res_comp.status_code == 200
    assert b"COMPROBANTE DE CIERRE DE CAJA (CORTE Z)" in res_comp.data
    assert b"CAJA CUADRADA" in res_comp.data

    # 9. Consultar Historial de Turnos
    res_hist = client.get('/caja/historial')
    assert res_hist.status_code == 200
    assert b"Historial de Turnos y Cierres Z" in res_hist.data
    assert str(turno_id).encode() in res_hist.data
