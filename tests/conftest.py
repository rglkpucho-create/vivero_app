import os
import pytest
from datetime import datetime, date, timezone
from app import create_app
from app.extensions import db
from app.models import (
    Rol, Empresa, Usuario, Cliente, Especie, LoteProduccion,
    Insumo, LoteInsumo, UnidadMedida, RazaAnimal, LoteAnimal, Venta, DetalleVenta
)


@pytest.fixture(scope='session')
def app():
    """Crea la aplicación Flask configurada para testing en memoria."""
    flask_app = create_app('testing')
    flask_app.config.update({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': False,
        'SERVER_NAME': 'localhost'
    })

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture(autouse=True)
def clean_database(app):
    """Limpia y asegura un estado fresco para cada test."""
    with app.app_context():
        db.session.rollback()
        # Eliminar registros en orden de dependencias
        for table in reversed(db.metadata.sorted_tables):
            db.session.execute(table.delete())
        db.session.commit()
        from app.views.auth import login_attempts
        login_attempts.clear()
    yield


@pytest.fixture
def client(app):
    """Cliente de pruebas HTTP fresco para cada test."""
    with app.test_client() as c:
        yield c


@pytest.fixture
def test_data(app):
    """Crea datos base multi-tenant (Empresa 1, Empresa 2, Usuarios, Roles, Productos)."""
    with app.app_context():
        # Roles
        rol_super = Rol(nombre='SuperAdmin', nivel=0, descripcion='Controlador Maestro')
        rol_admin = Rol(nombre='Administrador', nivel=1, descripcion='Admin de Empresa')
        rol_oper = Rol(nombre='Operador', nivel=2, descripcion='Operario de Campo')
        db.session.add_all([rol_super, rol_admin, rol_oper])
        db.session.flush()

        # Empresas (Multi-Tenant)
        empresa_a = Empresa(
            nombre='Vivero El Paraiso',
            nit_rut='900.111.222-1',
            email='info@elparaiso.co',
            ciudad='Cali',
            direccion='Km 5 Via Jamundi',
            telefono='3151234567',
            licencia_activa=True
        )
        empresa_b = Empresa(
            nombre='Finca Monteverde',
            nit_rut='900.333.444-2',
            email='contacto@monteverde.co',
            ciudad='Medellin',
            direccion='Vereda El Salado',
            telefono='3109876543',
            licencia_activa=True
        )
        db.session.add_all([empresa_a, empresa_b])
        db.session.flush()

        # Usuarios
        user_a = Usuario(
            nombre_completo='Carlos Administrador A',
            email='admin_a@test.com',
            telefono='3001112233',
            rol_id=rol_admin.id,
            empresa_id=empresa_a.id,
            activo=True,
            es_superadmin=False
        )
        user_a.set_password('Secret123!')

        user_b = Usuario(
            nombre_completo='Diana Administradora B',
            email='admin_b@test.com',
            telefono='3004445566',
            rol_id=rol_admin.id,
            empresa_id=empresa_b.id,
            activo=True,
            es_superadmin=False
        )
        user_b.set_password('Secret123!')

        user_super = Usuario(
            nombre_completo='Master SuperAdmin',
            email='superadmin@test.com',
            telefono='3009999999',
            rol_id=rol_super.id,
            empresa_id=empresa_a.id,
            activo=True,
            es_superadmin=True
        )
        user_super.set_password('Master123!')

        db.session.add_all([user_a, user_b, user_super])
        db.session.flush()

        # Clientes
        cliente_a = Cliente(
            nombre='Juan Perez Comprador',
            documento='111222333',
            tipo_documento='CC',
            telefono='3115551234',
            email='juan@comprador.com',
            direccion='Calle 10 # 5-20',
            ciudad='Cali',
            empresa_id=empresa_a.id
        )
        cliente_b = Cliente(
            nombre='Agro Inversiones Norte',
            documento='900999888',
            tipo_documento='NIT',
            telefono='3208889900',
            email='compras@agronorte.com',
            direccion='Cra 43 # 12-30',
            ciudad='Medellin',
            empresa_id=empresa_b.id
        )
        db.session.add_all([cliente_a, cliente_b])
        db.session.flush()

        # 1. Especie y Lote de Cultivo (Empresa A)
        especie_guayacan = Especie(
            nombre_comun='Guayacan Amarillo',
            nombre_cientifico='Handroanthus chrysanthus',
            dias_ciclo_estimado=180,
            precio_venta_sugerido=12000.0,
            empresa_id=empresa_a.id
        )
        db.session.add(especie_guayacan)
        db.session.flush()

        lote_cultivo = LoteProduccion(
            codigo_lote='GY-001',
            especie_id=especie_guayacan.id,
            empresa_id=empresa_a.id,
            fecha_siembra=date(2026, 1, 10),
            cantidad_sembrada=100,
            cantidad_actual=80,
            costo_total=160000.0,
            estado='Disponible'
        )
        db.session.add(lote_cultivo)

        # 2. Insumo con stock FIFO (Empresa A)
        unidad_bto = UnidadMedida(nombre='Bulto', abreviatura='Bto')
        db.session.add(unidad_bto)
        db.session.flush()

        insumo_sustrato = Insumo(
            codigo='INS-001',
            nombre='Sustrato Organico Premium',
            tipo='Comercial',
            unidad_medida_id=unidad_bto.id,
            cantidad_actual=30.0,
            costo_promedio=25000.0,
            precio_venta=40000.0,
            empresa_id=empresa_a.id
        )
        db.session.add(insumo_sustrato)
        db.session.flush()

        lote_insumo_1 = LoteInsumo(
            insumo_id=insumo_sustrato.id,
            fecha_compra=date(2026, 1, 5),
            cantidad_inicial=10.0,
            cantidad_actual=10.0,
            costo_unitario=20000.0
        )
        lote_insumo_2 = LoteInsumo(
            insumo_id=insumo_sustrato.id,
            fecha_compra=date(2026, 2, 10),
            cantidad_inicial=20.0,
            cantidad_actual=20.0,
            costo_unitario=27500.0
        )
        db.session.add_all([lote_insumo_1, lote_insumo_2])

        # 3. Pecuario: Raza y Lote Animal (Empresa A)
        raza_bovino = RazaAnimal(
            nombre='Brahman Blanco',
            especie='Bovino',
            proposito_ideal='Carne',
            valor_mercado_estimado=3800000.0,
            empresa_id=empresa_a.id
        )
        db.session.add(raza_bovino)
        db.session.flush()

        lote_animal = LoteAnimal(
            codigo='NOV-2026-01',
            nombre='Novillo Brahman #01',
            raza_id=raza_bovino.id,
            empresa_id=empresa_a.id,
            tipo='Individual',
            especie='Bovino',
            raza='Brahman Blanco',
            cantidad_actual=1,
            cantidad_inicial=1,
            peso_actual=420.0,
            costo_acumulado=2500000.0,
            estado='Activo',
            genero='Macho',
            fecha_ingreso=date(2026, 1, 15)
        )
        db.session.add(lote_animal)

        db.session.commit()

        return {
            'empresa_a_id': empresa_a.id,
            'empresa_b_id': empresa_b.id,
            'user_a_id': user_a.id,
            'user_b_id': user_b.id,
            'user_super_id': user_super.id,
            'cliente_a_id': cliente_a.id,
            'cliente_b_id': cliente_b.id,
            'lote_cultivo_id': lote_cultivo.id,
            'insumo_id': insumo_sustrato.id,
            'lote_animal_id': lote_animal.id
        }


def login_user(client, user_id):
    """Simula una sesión autenticada en el cliente Flask de pruebas."""
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True


def login_as(client, email, password='Secret123!'):
    """Inicia sesión formalmente a través de la ruta /login, cerrando cualquier sesión previa."""
    client.get('/logout', follow_redirects=True)
    return client.post('/login', data={'email': email, 'password': password}, follow_redirects=True)
