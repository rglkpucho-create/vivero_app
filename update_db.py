import os
from app import create_app, db
from sqlalchemy import text

app = create_app()

def actualizar_base_datos():
    print("\n--- 🛠️  INICIANDO ACTUALIZACIÓN TOTAL DE BASE DE DATOS ---")
    
    with app.app_context():
        # PASO 1: Forzar la creación de tablas
        print("1. Intentando crear tablas desde los modelos...")
        try:
            # Importamos localmente para evitar que el script se detenga si falta una
            from app import models
            db.create_all()
            print("   ✅ Sincronización de modelos completada.")
        except Exception as e:
            print(f"   ⚠️  Aviso en create_all: {e}")

        # PASO 2: Modificación estructural con verificación de existencia
        print("2. Verificando tablas para modificaciones estructurales...")
        try:
            with db.engine.connect() as conn:
                # LISTA DE POSIBLES NOMBRES (Singular y Plural por tus archivos .ibd)
                # Según tus archivos, tienes 'lote_produccion' y 'lotes_produccion'
                tablas_a_revisar = ['lotes_produccion', 'lote_produccion']
                
                for nombre_tabla in tablas_a_revisar:
                    # Verificar si la tabla existe antes de hacer el ALTER
                    check_table = text(f"SHOW TABLES LIKE '{nombre_tabla}'")
                    if conn.execute(check_table).fetchone():
                        print(f"   ... Procesando tabla encontrada: '{nombre_tabla}'")
                        
                        # Verificar si ya tiene la columna sede_id
                        check_col = text(f"""
                            SELECT count(*) FROM information_schema.COLUMNS 
                            WHERE TABLE_SCHEMA = DATABASE() 
                            AND TABLE_NAME = '{nombre_tabla}' 
                            AND COLUMN_NAME = 'sede_id'
                        """)
                        
                        if conn.execute(check_col).scalar() == 0:
                            print(f"   ... Agregando 'sede_id' a '{nombre_tabla}'...")
                            conn.execute(text(f"ALTER TABLE {nombre_tabla} ADD COLUMN sede_id INT NULL"))
                            # Solo intentamos el constraint si la tabla sedes existe
                            if conn.execute(text("SHOW TABLES LIKE 'sedes'")).fetchone():
                                conn.execute(text(f"ALTER TABLE {nombre_tabla} ADD CONSTRAINT fk_{nombre_tabla}_sede FOREIGN KEY (sede_id) REFERENCES sedes(id)"))
                            conn.commit()
                            print(f"   ✅ Tabla '{nombre_tabla}' actualizada.")
                        else:
                            print(f"   ℹ️ La columna ya existe en '{nombre_tabla}'.")
                    else:
                        print(f"   ❌ La tabla '{nombre_tabla}' no existe aún en la DB.")

        except Exception as e:
            print(f"   ❌ Error en modificación estructural: {e}")

    print("\n--- 🏁 PROCESO FINALIZADO. REVISA PHPMYADMIN ---")

if __name__ == "__main__":
    actualizar_base_datos()