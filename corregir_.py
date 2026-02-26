from app import create_app, db
from sqlalchemy import text, inspect

app = create_app()

def actualizar_base_datos():
    print("\n--- 🛠️  INICIANDO ACTUALIZACIÓN DE BASE DE DATOS ---")
    
    with app.app_context():
        # Usamos el inspector para ver qué columnas existen realmente
        inspector = inspect(db.engine)
        
        # Verificamos si la tabla existe primero
        if 'lote_animal' not in inspector.get_table_names():
            print("❌ Error: La tabla 'lote_animal' no existe. Ejecuta primero db.create_all()")
            return

        # Obtenemos las columnas actuales
        columnas_existentes = [col['name'] for col in inspector.get_columns('lote_animal')]
        print(f"📋 Columnas actuales: {columnas_existentes}")

        with db.engine.connect() as conn:
            transaccion = conn.begin()
            try:
                # 1. VERIFICAR Y AGREGAR 'GENERO'
                if 'genero' not in columnas_existentes:
                    print("   ➕ Agregando columna 'genero'...")
                    conn.execute(text("ALTER TABLE lote_animal ADD COLUMN genero VARCHAR(20)"))
                else:
                    print("   ✅ Columna 'genero' ya existe.")

                # 2. VERIFICAR Y AGREGAR 'UBICACION'
                if 'ubicacion' not in columnas_existentes:
                    print("   ➕ Agregando columna 'ubicacion'...")
                    conn.execute(text("ALTER TABLE lote_animal ADD COLUMN ubicacion VARCHAR(100)"))
                else:
                    print("   ✅ Columna 'ubicacion' ya existe.")

                # 3. VERIFICAR Y AGREGAR 'IMAGEN_URL' (Por seguridad)
                if 'imagen_url' not in columnas_existentes:
                    print("   ➕ Agregando columna 'imagen_url'...")
                    conn.execute(text("ALTER TABLE lote_animal ADD COLUMN imagen_url VARCHAR(255)"))
                else:
                    print("   ✅ Columna 'imagen_url' ya existe.")

                transaccion.commit()
                print("\n🎉 ¡ACTUALIZACIÓN COMPLETADA CON ÉXITO!")
                print("   Ahora puedes registrar animales con género y ubicación.")

            except Exception as e:
                transaccion.rollback()
                print(f"\n❌ Ocurrió un error: {e}")

if __name__ == "__main__":
    actualizar_base_datos()