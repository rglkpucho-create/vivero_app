import io
import pytest
from datetime import datetime, timezone
from app.extensions import db
from app.models import (
    Empresa, Usuario, Rol, LoteProduccion, Especie, Insumo, UnidadMedida
)


@pytest.fixture
def setup_data(app):
    """Crea una empresa, usuario admin y productos para las pruebas."""
    with app.app_context():
        empresa = Empresa(
            nombre="AgroVivero San Rafael SAS",
            nit_rut="900555666-3",
            telefono="3124445566",
            email="gerencia@sanrafael.co",
            direccion="Km 5 Vía Santander",
            ciudad="Bucaramanga"
        )
        db.session.add(empresa)
        db.session.flush()

        rol_admin = Rol.query.filter_by(nombre='Administrador').first()
        if not rol_admin:
            rol_admin = Rol(nombre='Administrador', nivel=1)
            db.session.add(rol_admin)
            db.session.flush()

        usuario = Usuario(
            nombre_completo="Administrador San Rafael",
            email="admin@sanrafael.co",
            empresa_id=empresa.id,
            rol_id=rol_admin.id,
            activo=True
        )
        usuario.set_password("adminpass123")
        db.session.add(usuario)

        especie = Especie(
            empresa_id=empresa.id,
            nombre_comun="Guayacán Amarillo",
            nombre_cientifico="Handroanthus chrysanthus",
            precio_venta_sugerido=65000.0
        )
        db.session.add(especie)
        db.session.flush()

        lote = LoteProduccion(
            empresa_id=empresa.id,
            especie_id=especie.id,
            codigo_lote="LOT-GUAYACAN-01",
            cantidad_sembrada=50,
            cantidad_actual=40,
            costo_total=800000.0,
            estado="Listo para Venta"
        )
        db.session.add(lote)

        um = UnidadMedida.query.filter_by(nombre='Unidad').first()
        if not um:
            um = UnidadMedida(nombre='Unidad', abreviatura='und')
            db.session.add(um)
            db.session.flush()

        insumo = Insumo(
            empresa_id=empresa.id,
            nombre="Matera Cerámica 25cm",
            unidad_medida_id=um.id,
            tipo="Matera",
            codigo="MAT-CER-25",
            cantidad_actual=30.0,
            costo_promedio=15000.0,
            precio_venta=32000.0
        )
        db.session.add(insumo)

        db.session.commit()

        return {
            'empresa_id': empresa.id,
            'usuario_id': usuario.id,
            'lote_id': lote.id,
            'insumo_id': insumo.id
        }


def test_modulo_impresion_etiquetas(client, app, setup_data):
    """Prueba la generación de etiquetas en rollo térmico y hoja adhesiva."""
    with app.app_context():
        usuario = db.session.get(Usuario, setup_data['usuario_id'])
        with client.session_transaction() as sess:
            sess['_user_id'] = str(usuario.id)
            sess['_fresh'] = True

        # 1. Acceder al hub de etiquetas
        resp_hub = client.get('/etiquetas/')
        assert resp_hub.status_code == 200
        assert b"Impresi\xc3\xb3n de Etiquetas" in resp_hub.data

        # 2. Generar etiquetas para Lote en Rollo Térmico 50x30
        resp_rollo = client.post('/etiquetas/generar', data={
            'formato': 'rollo_50x30',
            'tipo_origen': 'lote',
            'item_id': setup_data['lote_id'],
            'cantidad_copias': '5',
            'mostrar_precio': '1',
            'mostrar_qr': '1',
            'mostrar_barcode': '1'
        })
        assert resp_rollo.status_code == 200
        assert b"Guayac\xc3\xa1n Amarillo" in resp_rollo.data
        assert b"LOT-GUAYACAN-01" in resp_rollo.data

        # 3. Generar etiquetas para Insumo en Hoja Carta (30)
        resp_carta = client.post('/etiquetas/generar', data={
            'formato': 'hoja_carta_30',
            'tipo_origen': 'insumo',
            'item_id': setup_data['insumo_id'],
            'cantidad_copias': '30',
            'mostrar_precio': '1',
            'mostrar_qr': '0',
            'mostrar_barcode': '1'
        })
        assert resp_carta.status_code == 200
        assert b"Matera Cer\xc3\xa1mica 25cm" in resp_carta.data

        # 4. Atajo directo desde un lote
        resp_directo = client.get(f'/etiquetas/lote/{setup_data["lote_id"]}')
        assert resp_directo.status_code == 200
        assert b"LOT-GUAYACAN-01" in resp_directo.data


def test_configuracion_empresa_logo_y_bancos(client, app, setup_data):
    """Prueba el guardado de configuración corporativa, cuentas bancarias y logo."""
    with app.app_context():
        usuario = db.session.get(Usuario, setup_data['usuario_id'])
        with client.session_transaction() as sess:
            sess['_user_id'] = str(usuario.id)
            sess['_fresh'] = True

        # 1. Ver vista de configuración
        resp_get = client.get('/admin/empresa/configuracion')
        assert resp_get.status_code == 200

        # 2. Guardar datos fiscales, cuentas y pies de página
        resp_post = client.post('/admin/empresa/configuracion', data={
            'nombre': 'Vivero Agro San Rafael S.A.S.',
            'nit_rut': '900555666-9',
            'razon_social': 'Agro San Rafael Forestal S.A.S.',
            'telefono': '3129998877',
            'whatsapp_pedidos': '573129998877',
            'email': 'ventas@sanrafael.co',
            'direccion': 'Km 12 Vía Floridablanca',
            'ciudad': 'Bucaramanga',
            'slogan': 'Expertos en árboles nativos y paisajismo',
            'cuentas_bancarias': 'Bancolombia Ahorros #987-654321-00 a nombre de San Rafael SAS\nNequi: 3129998877',
            'pie_factura_legal': 'Régimen Simple. Garantía fitosanitaria: 15 días con factura.',
            'pie_ticket_pos': '¡Gracias por apoyar el agro colombiano!',
            'prefijo_factura_pos': 'VIV-'
        }, follow_redirects=True)
        assert resp_post.status_code == 200

        # 3. Validar persistencia en modelo Empresa
        empresa = db.session.get(Empresa, setup_data['empresa_id'])
        assert empresa.nombre == 'Vivero Agro San Rafael S.A.S.'
        assert empresa.prefijo_factura_pos == 'VIV-'
        assert 'Bancolombia' in empresa.cuentas_bancarias
        assert 'Garantía fitosanitaria' in empresa.pie_factura_legal


def test_copias_de_seguridad_respaldos(client, app, setup_data):
    """Prueba el panel de respaldos y la descarga de copias de seguridad de la base de datos."""
    with app.app_context():
        usuario = db.session.get(Usuario, setup_data['usuario_id'])
        with client.session_transaction() as sess:
            sess['_user_id'] = str(usuario.id)
            sess['_fresh'] = True

        # 1. Panel de respaldos
        resp_panel = client.get('/admin/respaldos')
        assert resp_panel.status_code == 200
        assert b"Copias de Seguridad" in resp_panel.data

        # 2. Descargar respaldo .sql / .db
        resp_db = client.get('/admin/respaldo/descargar-db')
        # En ambiente SQLite local debe retornar 200 con archivo SQL/DB
        if resp_db.status_code == 200:
            assert 'sql' in resp_db.mimetype or 'sqlite' in resp_db.mimetype or 'octet-stream' in resp_db.mimetype

        # 3. Descargar respaldo completo .zip
        resp_zip = client.get('/admin/respaldo/descargar-completo')
        if resp_zip.status_code == 200:
            assert 'zip' in resp_zip.mimetype
            assert resp_zip.data.startswith(b'PK') # ZIP magic header

        # 4. Validar que se actualizó el timestamp de último backup
        empresa = db.session.get(Empresa, setup_data['empresa_id'])
        assert empresa.ultimo_backup_fecha is not None
