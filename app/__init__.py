from flask import Flask
from config import config
from .extensions import db, login_manager

def create_app(config_name='default'):
    app = Flask(__name__)
    
    # Cargar configuración desde config.py
    app.config.from_object(config[config_name])

    # Inicializar extensiones
    db.init_app(app)
    login_manager.init_app(app)
    
    # Configurar Login
    login_manager.login_view = 'main.login'
    login_manager.login_message = 'Por favor inicia sesión para acceder.'
    login_manager.login_message_category = 'info'

    # Importar Modelos (para que SQLAlchemy los reconozca al crear tablas)
    from . import models
    from .models import Usuario  # Importamos Usuario específicamente para el user_loader

    # Registrar Blueprints (Rutas)
    from .views import main_bp
    app.register_blueprint(main_bp)

    # --- ESTA ES LA PARTE QUE FALTABA (SOLUCIÓN DEL ERROR) ---
    @login_manager.user_loader
    def load_user(user_id):
        # Flask-Login usa esto para recargar el usuario desde la sesión
        return Usuario.query.get(int(user_id))
    # ---------------------------------------------------------
    
    # Función para crear tablas automáticamente al iniciar
    with app.app_context():
        db.create_all()
        print(f"Sistema EcoSistem: Base de datos conectada y tablas verificadas.")

    return app