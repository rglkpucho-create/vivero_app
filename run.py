import os
from app import create_app

# Default to development if not set
env = os.environ.get('FLASK_ENV', 'development')
app = create_app(env)

if __name__ == '__main__':
    if env == 'production':
        try:
            from waitress import serve
            print("🚀 Iniciando EcoSistem en modo PRODUCCIÓN (Waitress) en el puerto 5000...")
            serve(app, host='0.0.0.0', port=5000)
        except ImportError:
            print("❌ Error: Waitress no está instalado. Ejecute: pip install waitress")
    else:
        print("[i] Iniciando EcoSistem en modo DESARROLLO (Werkzeug).")
        app.run(debug=True, port=5000)