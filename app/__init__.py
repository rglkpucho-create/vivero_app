from flask import Flask, render_template
from config import config
from .extensions import db, login_manager
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate
import logging
import os
from logging.handlers import RotatingFileHandler

csrf = CSRFProtect()
migrate = Migrate()

def create_app(config_name='default'):
    app = Flask(__name__)
    
    # Cargar configuración desde config.py
    app.config.from_object(config[config_name])

    # Inicializar extensiones
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db)
    
    # Configurar Login
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Por favor inicia sesión para acceder.'
    login_manager.login_message_category = 'info'

    # Importar Modelos (para que SQLAlchemy los reconozca al crear tablas)
    from . import models
    from .models import Usuario

    # Registrar Blueprints Modulares
    from .views import register_blueprints
    register_blueprints(app)

    # Configurar Logging en archivo para Producción
    if not os.path.exists('logs'):
        os.mkdir('logs')
    file_handler = RotatingFileHandler('logs/ecosistem.log', maxBytes=10240000, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('EcoSistem startup')

    # Cabeceras HTTP de Seguridad
    @app.after_request
    def set_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        return response

    # Manejo Global de Errores
    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template('error.html', code=403, msg="Acceso denegado. No tienes permisos para esta área."), 403

    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('error.html', code=404, msg="Página no encontrada."), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('error.html', code=500, msg="Error interno del servidor."), 500

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(Usuario, int(user_id))
    
    # Asegurar conexión y estructura base de datos
    with app.app_context():
        import time
        from sqlalchemy.exc import OperationalError
        retries = 10
        while retries > 0:
            try:
                db.create_all()
                
                # Verificación segura de columnas dinámicas en SQLite / Postgres
                try:
                    from sqlalchemy import inspect, text
                    inspector = inspect(db.engine)
                    if 'venta' in inspector.get_table_names():
                        cols = [c['name'] for c in inspector.get_columns('venta')]
                        if 'caja_turno_id' not in cols:
                            with db.engine.connect() as conn:
                                conn.execute(text("ALTER TABLE venta ADD COLUMN caja_turno_id INTEGER REFERENCES caja_turno(id)"))
                                conn.commit()
                except Exception as ex_col:
                    app.logger.warning(f"Aviso verificando columnas dinámicas de caja: {ex_col}")

                app.logger.info("Sistema EcoSistem: Base de datos conectada y esquema verificado.")
                break
            except OperationalError as e:
                app.logger.warning(f"Base de datos no lista. Reintentando en 3s... ({retries} intentos restantes)")
                retries -= 1
                time.sleep(3)
        else:
            app.logger.error("No se pudo conectar a la base de datos tras múltiples intentos.")
    from .cli import register_cli_commands
    register_cli_commands(app)

    return app