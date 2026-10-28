import os
from dotenv import load_dotenv
from datetime import timedelta

# Cargar variables de entorno desde el archivo .env si existe
load_dotenv()
basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    """Configuración base común."""
    # Use un SECRET_KEY fijo desde .env en producción para no desloguear usuarios al reiniciar.
    # En desarrollo genera uno temporal automáticamente.
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.urandom(32).hex()
    
    # Manejo de sesión
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_COOKIE_SECURE = os.environ.get('FLASK_ENV') == 'production'
    SESSION_COOKIE_HTTPONLY = True
    WTF_CSRF_TIME_LIMIT = 3600
    
    # Base de Datos
    DB_USER = os.environ.get('DB_USER', 'root')
    DB_PASS = os.environ.get('DB_PASS', '')
    DB_HOST = os.environ.get('DB_HOST', 'localhost')
    DB_NAME = os.environ.get('DB_NAME', 'ecosistem_v4')
    
    # Determinar URI de base de datos:
    # Si hay contraseña de MySQL configurada, usar MySQL; sino, SQLite como fallback local.
    if DB_PASS:
        SQLALCHEMY_DATABASE_URI = f'mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}'
    elif os.environ.get('DB_PASS') is not None:
        # DB_PASS definido explícitamente como vacío en .env → MySQL sin password
        SQLALCHEMY_DATABASE_URI = f'mysql+pymysql://{DB_USER}@{DB_HOST}/{DB_NAME}'
    else:
        # Sin .env o sin DB_PASS → fallback seguro a SQLite local
        SQLALCHEMY_DATABASE_URI = f'sqlite:///{os.path.join(basedir, DB_NAME + ".db")}'
        
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(basedir, 'app', 'static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max-limit
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    RATELIMIT_DEFAULT = "200 per day; 50 per hour"

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True  # Solo HTTPS en producción

class TestingConfig(Config):
    TESTING = True
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    SERVER_NAME = 'localhost'

# Diccionario para seleccionar configuración fácilmente
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}