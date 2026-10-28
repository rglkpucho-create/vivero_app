import pytest
from app.extensions import db
from app.models import Usuario


def test_login_exitoso(client, test_data):
    """Verifica que un usuario con credenciales correctas inicia sesión."""
    response = client.post('/login', data={
        'email': 'admin_a@test.com',
        'password': 'Secret123!'
    }, follow_redirects=True)
    
    assert response.status_code == 200
    # Comprobar que ingresa al sistema y se visualiza su perfil en navbar
    assert b'Carlos' in response.data or b'logout' in response.data or b'Dashboard' in response.data


def test_login_password_incorrecto(client, test_data):
    """Verifica que contraseñas erróneas son rechazadas."""
    client.get('/logout')
    response = client.post('/login', data={
        'email': 'admin_a@test.com',
        'password': 'ClaveTotalmenteErronea!'
    }, follow_redirects=True)
    
    assert response.status_code == 200
    assert b'Credenciales incorrectas' in response.data or b'incorrectas' in response.data


def test_recuperacion_contrasena_flujo_completo(client, app, test_data):
    """Verifica generación de token seguro y actualización de contraseña."""
    client.get('/logout')
    with app.app_context():
        user = db.session.get(Usuario, test_data['user_a_id'])
        token = user.generar_token_recuperacion()
        assert token is not None

    # 1. Acceder al formulario de restablecimiento con token válido (fuera del context block)
    res_form = client.get(f'/reset-password/{token}')
    assert res_form.status_code == 200
    assert b'reset_password' in res_form.data or b'password' in res_form.data.lower()

    # 2. Enviar nueva contraseña
    res_post = client.post(f'/reset-password/{token}', data={
        'password': 'NuevaSuperPassword2026!',
        'password_confirm': 'NuevaSuperPassword2026!'
    }, follow_redirects=True)
    assert res_post.status_code == 200
    assert b'actualizada con' in res_post.data or b'iniciar' in res_post.data.lower()

    # 3. Comprobar que la contraseña se actualizó en la BD
    with app.app_context():
        u_updated = db.session.get(Usuario, test_data['user_a_id'])
        assert u_updated.check_password('NuevaSuperPassword2026!')
        assert not u_updated.check_password('Secret123!')


def test_token_recuperacion_invalido(client, test_data):
    """Verifica que un token manipulado sea rechazado de inmediato."""
    client.get('/logout')
    response = client.get('/reset-password/token_completamente_falso_y_manipulado', follow_redirects=True)
    assert response.status_code == 200
    assert b'expirado' in response.data or b'recuperar' in response.data.lower()
