"""
Módulo de Administración — Gestión de Usuarios y Roles
"""
import logging
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from ..models import Usuario, Rol, AuditoriaLog
from ..extensions import db
from .helpers import solo_admin, registrar_auditoria, filtrar_por_empresa, get_or_404_empresa

logger = logging.getLogger(__name__)
admin_bp = Blueprint('admin', __name__)

def obtener_roles_permitidos():
    """Retorna los roles que el usuario actual puede ver y asignar según su nivel jerárquico."""
    if current_user.es_superadmin:
        return Rol.query.order_by(Rol.nivel.asc()).all()
    nivel_actual = current_user.rol.nivel if current_user.rol else 1
    # Administradores regulares no pueden ver ni asignar el rol SuperAdmin (nivel 0)
    return Rol.query.filter(Rol.nivel > 0, Rol.nivel >= nivel_actual).order_by(Rol.nivel.asc()).all()


@admin_bp.route('/admin/usuarios')
@solo_admin
def lista_usuarios():
    if current_user.es_superadmin:
        usuarios = Usuario.query.all()
    else:
        usuarios = Usuario.query.filter_by(empresa_id=current_user.empresa_id).all()
    return render_template('admin/lista_usuarios.html', usuarios=usuarios)

@admin_bp.route('/admin/usuario/nuevo', methods=['GET', 'POST'])
@solo_admin
def nuevo_usuario():
    # Validación de límite de usuarios según el plan SaaS contratado
    if not current_user.es_superadmin and current_user.empresa:
        permite, mensaje, actual, limite = current_user.empresa.verificar_limite_usuarios()
        if not permite:
            flash(f"⚠️ {mensaje}", 'warning')
            return redirect(url_for('admin.lista_usuarios'))

    if request.method == 'POST':
        try:
            email = request.form.get('email', '').strip().lower()
            if Usuario.query.filter_by(email=email).first():
                flash('El correo ya está en uso.', 'danger')
                return redirect(url_for('admin.nuevo_usuario'))

            rol_id = int(request.form.get('rol_id', 0))
            rol_asignado = Rol.query.get(rol_id)
            if not rol_asignado:
                flash('Rol inválido.', 'danger')
                return redirect(url_for('admin.nuevo_usuario'))

            # Prevención de escalada de privilegios
            if not current_user.es_superadmin:
                nivel_actual = current_user.rol.nivel if current_user.rol else 1
                if rol_asignado.nivel == 0 or rol_asignado.nivel < nivel_actual:
                    flash('No tienes permisos para asignar este rol de mayor jerarquía.', 'danger')
                    return redirect(url_for('admin.nuevo_usuario'))

            u = Usuario(
                nombre_completo=request.form.get('nombre_completo'),
                email=email,
                telefono=request.form.get('telefono'),
                rol_id=rol_asignado.id,
                activo=True
            )
            u.set_password(request.form.get('password'))
            # Asignar empresa correspondiente
            if not current_user.es_superadmin:
                u.empresa_id = current_user.empresa_id
            else:
                from flask import session
                u.empresa_id = session.get('superadmin_empresa_id') or current_user.empresa_id

            db.session.add(u)
            db.session.commit()
            registrar_auditoria('CREAR', 'Administración', f"Usuario {u.email} creado")
            flash('Usuario creado exitosamente.', 'success')
            return redirect(url_for('admin.lista_usuarios'))
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error creando usuario: {e}')
            flash(f'Error al crear: {e}', 'danger')

    roles = obtener_roles_permitidos()
    return render_template('admin/form_usuario.html', roles=roles, usuario=None)

@admin_bp.route('/admin/usuario/editar/<int:id>', methods=['GET', 'POST'])
@solo_admin
def editar_usuario(id):
    u = get_or_404_empresa(Usuario, id)
    if request.method == 'POST':
        try:
            u.nombre_completo = request.form.get('nombre_completo')
            u.telefono = request.form.get('telefono')
            
            # Si se intenta cambiar rol
            nuevo_rol_id = int(request.form.get('rol_id', 0))
            if nuevo_rol_id and (not u.rol_id or u.rol_id != nuevo_rol_id):
                if u.id == current_user.id and not current_user.es_superadmin:
                    flash('No puedes modificar tu propio rol.', 'warning')
                else:
                    rol_asignado = Rol.query.get(nuevo_rol_id)
                    if not rol_asignado:
                        flash('Rol inválido.', 'danger')
                        return redirect(url_for('admin.lista_usuarios'))
                    if not current_user.es_superadmin:
                        nivel_actual = current_user.rol.nivel if current_user.rol else 1
                        if rol_asignado.nivel == 0 or rol_asignado.nivel < nivel_actual:
                            flash('No tienes permisos para asignar este nivel de rol.', 'danger')
                            return redirect(url_for('admin.lista_usuarios'))
                    u.rol_id = rol_asignado.id
            
            pwd = request.form.get('password')
            if pwd and pwd.strip():
                u.set_password(pwd.strip())
                
            db.session.commit()
            registrar_auditoria('EDITAR', 'Administración', f"Usuario {u.email} modificado")
            flash('Usuario actualizado exitosamente.', 'success')
            return redirect(url_for('admin.lista_usuarios'))
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error editando usuario: {e}')
            flash(f'Error al editar: {e}', 'danger')

    roles = obtener_roles_permitidos()
    return render_template('admin/form_usuario.html', roles=roles, usuario=u)

@admin_bp.route('/admin/usuario/toggle_estado/<int:id>', methods=['POST'])
@solo_admin
def toggle_estado_usuario(id):
    if current_user.id == id:
        flash('No puedes desactivar tu propia cuenta.', 'warning')
        return redirect(url_for('admin.lista_usuarios'))
        
    try:
        u = get_or_404_empresa(Usuario, id)
        u.activo = not u.activo
        db.session.commit()
        estado = "activado" if u.activo else "desactivado"
        registrar_auditoria('EDITAR', 'Administración', f"Usuario {u.email} {estado}")
        flash(f'Usuario {estado}.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {e}', 'danger')
        
    return redirect(url_for('admin.lista_usuarios'))

@admin_bp.route('/admin/roles')
@solo_admin
def lista_roles():
    roles = obtener_roles_permitidos()
    return render_template('admin/lista_roles.html', roles=roles)

@admin_bp.route('/admin/auditoria')
@solo_admin
def lista_auditoria():
    if current_user.es_superadmin:
        logs = AuditoriaLog.query.order_by(AuditoriaLog.fecha.desc()).limit(100).all()
    else:
        logs = AuditoriaLog.query.filter_by(empresa_id=current_user.empresa_id).order_by(AuditoriaLog.fecha.desc()).limit(100).all()
    return render_template('admin/auditoria.html', logs=logs)
