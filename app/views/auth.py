"""
Módulo de Autenticación — Login, Registro, Logout
"""
import logging
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from ..models import Usuario, Rol
from ..extensions import db
from .helpers import solo_admin, registrar_auditoria
from datetime import datetime, timezone

import time
logger = logging.getLogger(__name__)
auth_bp = Blueprint('auth', __name__)

login_attempts = {}
MAX_ATTEMPTS = 5
LOCK_TIME = 300  # 5 minutos


@auth_bp.route('/')
def home():
    if current_user.is_authenticated:
        if getattr(current_user, 'es_superadmin', False):
            return redirect(url_for('superadmin.lista_empresas'))
        return redirect(url_for('dashboard.dashboard'))
    from ..models import PLANES_SAAS
    return render_template('planes.html', planes=PLANES_SAAS, es_inicio=True)


@auth_bp.route('/planes')
def planes():
    from ..models import PLANES_SAAS
    return render_template('planes.html', planes=PLANES_SAAS, es_inicio=False)


@auth_bp.route('/registro')
@login_required
@solo_admin
def registro():
    return redirect(url_for('admin.nuevo_usuario'))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard'))
        
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ip and ',' in ip:
        ip = ip.split(',')[0].strip()

    if request.method == 'POST':
        now = time.time()
        attempts, lock_until = login_attempts.get(ip, (0, 0))
        # Verificar límite de intentos (omitir en modo TESTING)
        if not current_app.config.get('TESTING'):
            if lock_until > now:
                flash(f'Demasiados intentos. Intente nuevamente en {int((lock_until - now) / 60) + 1} minutos.', 'danger')
                return render_template('login.html')
            elif lock_until > 0 and lock_until <= now:
                attempts, lock_until = 0, 0  # reset
            
        email = request.form.get('email', '').strip().lower()
        u = Usuario.query.filter_by(email=email).first()
        if u and u.check_password(request.form.get('password')):
            if not u.activo:
                flash('Su cuenta está desactivada.', 'danger')
                return redirect(url_for('auth.login'))
            
            # Verificar licencia de la empresa (SuperAdmin no tiene restricción)
            if not getattr(u, 'es_superadmin', False) and getattr(u, 'empresa', None):
                if not u.empresa.licencia_activa:
                    return render_template('licencia_suspendida.html'), 403
                # Verificar vencimiento automático
                if u.empresa.fecha_vencimiento and u.empresa.fecha_vencimiento < datetime.now(timezone.utc).date():
                    u.empresa.licencia_activa = False
                    db.session.commit()
                    return render_template('licencia_suspendida.html'), 403
            
            # Limpiar intentos al entrar con éxito
            if ip in login_attempts:
                del login_attempts[ip]

            login_user(u)
            u.ultimo_login = datetime.now(timezone.utc)
            registrar_auditoria('LOGIN', 'Autenticación', "Inicio de sesión")
            db.session.commit()
            
            # SuperAdmin va a su panel, usuarios normales al dashboard
            if getattr(u, 'es_superadmin', False):
                return redirect(url_for('superadmin.lista_empresas'))
            return redirect(url_for('dashboard.dashboard'))
            
        attempts += 1
        if attempts >= MAX_ATTEMPTS:
            lock_until = now + LOCK_TIME
        login_attempts[ip] = (attempts, lock_until)
        flash('Credenciales incorrectas.', 'danger')
        
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    registrar_auditoria('LOGOUT', 'Autenticación', "Cierre de sesión")
    logout_user()
    return redirect(url_for('auth.home'))


@auth_bp.route('/recuperar-password', methods=['GET', 'POST'])
def recuperar_password():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard'))

    from itsdangerous import URLSafeTimedSerializer
    from flask import current_app

    link_generado = None
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        u = Usuario.query.filter_by(email=email).first()
        if u and u.activo:
            s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
            token = s.dumps(u.email, salt='password-reset-salt')
            reset_url = url_for('auth.reset_password', token=token, _external=True)
            link_generado = reset_url
            registrar_auditoria('SOLICITUD_RESET', 'Autenticación', f"Solicitud de reseteo para {email}")
            flash('Enlace de recuperación generado. Puedes restablecer tu contraseña a continuación.', 'info')
        else:
            flash('Si el correo ingresado está registrado y activo, recibirás las instrucciones para restablecer tu contraseña.', 'info')

    return render_template('recuperar_password.html', link_generado=link_generado)


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard'))

    from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
    from flask import current_app

    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        email = s.loads(token, salt='password-reset-salt', max_age=3600)
    except (SignatureExpired, BadSignature):
        flash('El enlace de recuperación es inválido o ha expirado. Por favor solicita uno nuevo.', 'danger')
        return redirect(url_for('auth.recuperar_password'))

    u = Usuario.query.filter_by(email=email).first_or_404()

    if request.method == 'POST':
        p1 = request.form.get('password', '').strip()
        p2 = request.form.get('password_confirm', '').strip()
        if not p1 or len(p1) < 6:
            flash('La contraseña debe tener al menos 6 caracteres.', 'danger')
            return render_template('reset_password.html', token=token, email=email)
        if p1 != p2:
            flash('Las contraseñas no coinciden.', 'danger')
            return render_template('reset_password.html', token=token, email=email)

        u.set_password(p1)
        db.session.commit()
        registrar_auditoria('RESET_PASSWORD', 'Autenticación', f"Contraseña restablecida para {email}")
        flash('¡Contraseña actualizada con éxito! Ya puedes iniciar sesión con tu nueva clave.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('reset_password.html', token=token, email=email)

