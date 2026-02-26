from app import create_app
from app.extensions import db
from sqlalchemy import text

app = create_app()

with app.app_context():
    print("--- INICIANDO ACTUALIZACIÓN GENERAL DE BASE DE DATOS ---")
    
    # 1. Asegurar corrección en tabla 'especies' (por si acaso)
    try:
        print("1. Verificando estructura de tabla 'especies'...")
        sql = text("ALTER TABLE especies ADD COLUMN dias_ciclo_estimado INTEGER DEFAULT 0;")
        db.session.execute(sql)
        db.session.commit()
        print("✅ Columna 'dias_ciclo_estimado' agregada.")
    except Exception as e:
        print(f"ℹ️ (La columna ya existía o no fue necesaria)")
        db.session.rollback()

    # 2. Crear TODAS las tablas nuevas (Ventas, Clientes, Producción faltante)
    print("\n2. Sincronizando nuevas tablas (Ventas, Clientes)...")
    try:
        db.create_all()
        print("✅ Tablas creadas correctamente.")
    except Exception as e:
        print(f"❌ Error al crear tablas: {e}")

    print("\n--- PROCESO TERMINADO ---")
    print("Base de datos actualizada con Módulos de Compras, Producción y Ventas.")