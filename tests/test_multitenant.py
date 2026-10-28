import pytest
from app.extensions import db
from app.models import Venta, Cliente, LoteProduccion, LoteAnimal
from tests.conftest import login_as


def test_aislamiento_multitenant_clientes(client, app, test_data):
    """Verifica que el filtrado de consultas aísle estrictamente los clientes por empresa."""
    # 1. Como Usuario A
    login_as(client, 'admin_a@test.com', 'Secret123!')
    res_a = client.get('/clientes')
    assert res_a.status_code == 200
    assert b'Juan Perez Comprador' in res_a.data
    assert b'Agro Inversiones Norte' not in res_a.data

    # 2. Como Usuario B
    client.get('/logout', follow_redirects=True)
    login_as(client, 'admin_b@test.com', 'Secret123!')
    res_b = client.get('/clientes')
    assert res_b.status_code == 200
    assert b'Agro Inversiones Norte' in res_b.data
    assert b'Juan Perez Comprador' not in res_b.data


def test_proteccion_idor_acceso_venta_otra_empresa(client, app, test_data):
    """
    Verifica protección contra Insecure Direct Object Reference (IDOR).
    Usuario B no debe poder ver ni facturar una venta de Empresa A (debe retornar 403 Forbidden).
    """
    # 1. Crear Venta para Empresa A
    login_as(client, 'admin_a@test.com', 'Secret123!')
    res_crear = client.post('/venta/nueva', follow_redirects=True)
    assert res_crear.status_code == 200
    
    with app.app_context():
        venta_a = Venta.query.filter_by(empresa_id=test_data['empresa_a_id']).first()
        assert venta_a is not None
        v_id = venta_a.id

    # 2. Intentar acceder a la venta como Usuario B
    client.get('/logout', follow_redirects=True)
    login_as(client, 'admin_b@test.com', 'Secret123!')

    res_acceso = client.get(f'/venta/{v_id}')
    assert res_acceso.status_code == 403

    # 3. Intentar agregar un item a la venta de Empresa A desde la sesión de Empresa B
    res_agregar = client.post(f'/venta/{v_id}/agregar', data={
        'cantidad': '1',
        'precio_unitario': '1000'
    })
    assert res_agregar.status_code == 403

    # 4. Intentar descargar factura PDF de Empresa A siendo Empresa B
    res_pdf = client.get(f'/venta/{v_id}/factura-pdf')
    assert res_pdf.status_code == 403


def test_superadmin_acceso_global_multitenant(client, app, test_data):
    """Verifica que el SuperAdmin pueda auditar y visualizar recursos globales."""
    login_as(client, 'superadmin@test.com', 'Master123!')
    
    # SuperAdmin accede a la lista de empresas del panel maestro
    res_empresas = client.get('/superadmin/empresas')
    assert res_empresas.status_code == 200
    assert b'Vivero El Paraiso' in res_empresas.data
    assert b'Finca Monteverde' in res_empresas.data
