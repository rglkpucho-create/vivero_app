"""
Módulo de Administración — Gestión de Usuarios y Roles
"""
import os
import io
import zipfile
import sqlite3
import logging
from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file, current_app, Response
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
from ..models import Usuario, Rol, AuditoriaLog, Empresa
from ..extensions import db
from .helpers import solo_admin, registrar_auditoria, filtrar_por_empresa, get_or_404_empresa, obtener_empresa_activa

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


# ==============================================================
# CONFIGURACIÓN GENERAL DE LA EMPRESA (LOGO, BANCOS, FACTURACIÓN)
# ==============================================================

@admin_bp.route('/admin/empresa/configuracion', methods=['GET', 'POST'])
@solo_admin
def configuracion_empresa():
    """Configuración general de datos corporativos, logo, cuentas bancarias y pies de factura."""
    empresa = obtener_empresa_activa()
    if not empresa:
        flash("No hay una empresa activa para configurar.", "danger")
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        try:
            empresa.nombre = request.form.get('nombre', '').strip() or empresa.nombre
            empresa.nit_rut = request.form.get('nit_rut', '').strip()
            empresa.razon_social = request.form.get('razon_social', '').strip()
            empresa.telefono = request.form.get('telefono', '').strip()
            empresa.whatsapp_pedidos = request.form.get('whatsapp_pedidos', '').strip()
            empresa.email = request.form.get('email', '').strip()
            empresa.direccion = request.form.get('direccion', '').strip()
            empresa.ciudad = request.form.get('ciudad', '').strip()
            empresa.slogan = request.form.get('slogan', '').strip()
            
            # Datos bancarios y comerciales
            empresa.cuentas_bancarias = request.form.get('cuentas_bancarias', '').strip()
            empresa.pie_factura_legal = request.form.get('pie_factura_legal', '').strip()
            empresa.pie_ticket_pos = request.form.get('pie_ticket_pos', '').strip()
            empresa.prefijo_factura_pos = request.form.get('prefijo_factura_pos', 'POS-').strip()

            # Subida de logo corporativo
            logo_file = request.files.get('logo_file')
            if logo_file and logo_file.filename:
                ext = logo_file.filename.rsplit('.', 1)[-1].lower()
                if ext in {'png', 'jpg', 'jpeg', 'webp'}:
                    nombre_archivo = f"logo_empresa_{empresa.id}_{int(datetime.now().timestamp())}.{ext}"
                    folder_logos = os.path.join(current_app.root_path, 'static', 'uploads', 'logos')
                    os.makedirs(folder_logos, exist_ok=True)
                    ruta_guardar = os.path.join(folder_logos, secure_filename(nombre_archivo))
                    logo_file.save(ruta_guardar)
                    empresa.logo_url = f"/static/uploads/logos/{nombre_archivo}"

            db.session.commit()
            registrar_auditoria('EDITAR', 'Administración', f"Configuración de empresa {empresa.nombre} actualizada")
            flash("¡Configuración de la empresa y logotipo actualizados con éxito!", "success")
            return redirect(url_for('admin.configuracion_empresa'))

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error guardando configuración de empresa: {e}")
            flash(f"Error al guardar los cambios: {str(e)}", "danger")

    return render_template('admin/configuracion_empresa.html', empresa=empresa)


# ==============================================================
# RESPALDOS DE BASE DE DATOS Y SEGURIDAD (BACKUP 1-CLIC)
# ==============================================================

@admin_bp.route('/admin/respaldos')
@solo_admin
def panel_respaldos():
    """Panel de copias de seguridad con métricas de salud y descarga con un clic."""
    empresa = obtener_empresa_activa()
    db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
    
    tamano_db_str = "Desconocido"
    es_sqlite = 'sqlite' in db_uri
    db_path = None

    if es_sqlite and '///' in db_uri:
        db_path = db_uri.split('///')[-1]
        if os.path.exists(db_path):
            tamano_bytes = os.path.getsize(db_path)
            if tamano_bytes < 1024 * 1024:
                tamano_db_str = f"{tamano_bytes / 1024:.1f} KB"
            else:
                tamano_db_str = f"{tamano_bytes / (1024 * 1024):.2f} MB"

    return render_template(
        'admin/respaldos.html',
        empresa=empresa,
        es_sqlite=es_sqlite,
        tamano_db_str=tamano_db_str,
        ahora=datetime.now(timezone.utc)
    )


@admin_bp.route('/admin/respaldo/descargar-db')
@solo_admin
def descargar_respaldo_db():
    """Genera una copia en caliente de la base de datos y la envía como descarga directa."""
    empresa = obtener_empresa_activa()
    db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
    timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    try:
        if 'sqlite' in db_uri and '///' in db_uri:
            db_path = db_uri.split('///')[-1]
            if not os.path.exists(db_path):
                flash("No se encontró el archivo de base de datos local.", "danger")
                return redirect(url_for('admin.panel_respaldos'))

            # Backup en caliente mediante sqlite3 para evitar corrupciones de concurrencia
            mem_backup = io.BytesIO()
            src_conn = sqlite3.connect(db_path)
            dest_conn = sqlite3.connect(':memory:')
            src_conn.backup(dest_conn)
            src_conn.close()

            # Volcar a buffer
            for line in dest_conn.iterdump():
                mem_backup.write(f"{line}\n".encode('utf-8'))
            dest_conn.close()
            mem_backup.seek(0)

            # Actualizar timestamp de último respaldo
            if empresa:
                empresa.ultimo_backup_fecha = datetime.now(timezone.utc)
                db.session.commit()

            filename = f"Backup_EcoSistem_{timestamp_str}.sql"
            return send_file(
                mem_backup,
                as_attachment=True,
                download_name=filename,
                mimetype='application/sql'
            )
        else:
            flash("El sistema actual está configurado en un servidor externo (MySQL/PostgreSQL).", "info")
            return redirect(url_for('admin.panel_respaldos'))

    except Exception as e:
        logger.error(f"Error generando respaldo de base de datos: {e}")
        flash(f"Error generando copia de seguridad: {str(e)}", "danger")
        return redirect(url_for('admin.panel_respaldos'))


@admin_bp.route('/admin/respaldo/descargar-completo')
@solo_admin
def descargar_respaldo_completo():
    """Genera un archivo comprimido .zip con la base de datos y la carpeta de uploads."""
    empresa = obtener_empresa_activa()
    db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
    timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')

    try:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # 1. Base de datos
            if 'sqlite' in db_uri and '///' in db_uri:
                db_path = db_uri.split('///')[-1]
                if os.path.exists(db_path):
                    zip_file.write(db_path, arcname=f"database/ecosistem_{timestamp_str}.db")

            # 2. Archivos multimedia y logos (uploads)
            uploads_dir = os.path.join(current_app.root_path, 'static', 'uploads')
            if os.path.exists(uploads_dir):
                for root, _, files in os.walk(uploads_dir):
                    for file in files:
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(full_path, uploads_dir)
                        zip_file.write(full_path, arcname=os.path.join('uploads', rel_path))

        zip_buffer.seek(0)

        if empresa:
            empresa.ultimo_backup_fecha = datetime.now(timezone.utc)
            db.session.commit()

        filename = f"Respaldo_Completo_EcoSistem_{timestamp_str}.zip"
        return send_file(
            zip_buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/zip'
        )

    except Exception as e:
        logger.error(f"Error generando respaldo completo .zip: {e}")
        flash(f"Error al generar paquete de respaldo: {str(e)}", "danger")
        return redirect(url_for('admin.panel_respaldos'))

