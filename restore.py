import os
import zipfile
import glob

def restaurar_copia():
    # 1. Configuración
    carpeta_backups = "backups"
    
    # 2. Buscar backups existentes
    if not os.path.exists(carpeta_backups):
        print("❌ No existe la carpeta de copias de seguridad ('backups').")
        return

    # Obtener lista de archivos .zip y ordenarlos por fecha (el más nuevo al final)
    archivos_zip = glob.glob(os.path.join(carpeta_backups, "*.zip"))
    archivos_zip.sort(key=os.path.getmtime)

    if not archivos_zip:
        print("❌ No hay copias de seguridad disponibles para restaurar.")
        return

    # 3. Mostrar menú interactivo
    print("\n--- 🔄 RESTAURAR COPIA DE SEGURIDAD ---")
    print("⚠️  ADVERTENCIA: Esto sobrescribirá tus archivos de código actuales.")
    print("    Los archivos nuevos que hayas creado después del backup NO se borrarán,")
    print("    pero los modificados volverán a su estado anterior.\n")
    
    print("Copias disponibles:")
    for i, archivo in enumerate(archivos_zip):
        nombre_archivo = os.path.basename(archivo)
        # Mostrar fecha legible si es posible, o solo el nombre
        print(f"  [{i+1}] {nombre_archivo}")

    # 4. Solicitar selección al usuario
    try:
        seleccion = input("\nElige el número del archivo a restaurar (o 'x' para salir): ")
        if seleccion.lower() == 'x':
            print("Operación cancelada.")
            return
            
        indice = int(seleccion) - 1
        if indice < 0 or indice >= len(archivos_zip):
            print("❌ Número inválido.")
            return
            
        archivo_elegido = archivos_zip[indice]
        
    except ValueError:
        print("❌ Entrada inválida.")
        return

    # 5. Confirmación final
    print(f"\nVas a restaurar: {os.path.basename(archivo_elegido)}")
    confirmacion = input("¿Estás 100% seguro? (escribe 'si' para continuar): ")
    
    if confirmacion.lower() != 'si':
        print("Cancelado por seguridad.")
        return

    # 6. Ejecutar restauración
    try:
        print("\n⏳ Extrayendo archivos...")
        with zipfile.ZipFile(archivo_elegido, 'r') as zipf:
            # Extraer en el directorio actual (sobreescribiendo)
            zipf.extractall(os.getcwd())
            
        print("✅ ¡Restauración completada con éxito!")
        print("🔄 Reinicia tu servidor Flask para ver los cambios.")
        
    except Exception as e:
        print(f"❌ Error crítico al restaurar: {e}")
        print("Intenta hacerlo manualmente descomprimiendo el ZIP.")

if __name__ == "__main__":
    restaurar_copia()
    input("\nPresiona Enter para salir...")