import os

class Config:
    """Configuración base común."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'clave_maestra_super_segura_2025'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Configuración de base de datos MySQL (XAMPP por defecto)
    DB_USER = 'root'
    DB_PASS = '' 
    DB_HOST = 'localhost'
    DB_NAME = 'ecosistem_v4' # ¡OJO! Usaremos un nombre nuevo para evitar conflictos

    SQLALCHEMY_DATABASE_URI = f'mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}'

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

# Diccionario para seleccionar configuración fácilmente
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}