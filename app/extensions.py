from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

# Instancias vacías que luego conectaremos a la app
db = SQLAlchemy()
login_manager = LoginManager()