import os
import zipfile
import datetime

def crear_backup():
    # 1. Configuración
    nombre_base = "Respaldo_Vivero"
    
    # Obtener la ruta del directorio donde está este script (Raíz del proyecto)
    root_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Carpetas a ignorar completamente
    carpetas_ignorar = {'env', 'venv', '__pycache__', '.git', '.vscode', '.idea', 'backups', '.vs'}
    
    # ATENCIÓN: Eliminé 'instance' de arriba para manejarla con cuidado abajo
    # Extensiones a ignorar
    extensiones_ignorar = {'.pyc', '.pyo', '.pyd'}
    
    # 2. Generar nombre
    ahora = datetime.datetime.now()
    timestamp = ahora.strftime("%Y-%m-%d_%H-%M")
    nombre_zip = f"{nombre_base}_{timestamp}.zip"
    
    # 3. Crear carpeta 'backups'
    carpeta_destino = os.path.join(root_dir, "backups")
    if not os.path.exists(carpeta_destino):
        os.makedirs(carpeta_destino)
        
    ruta_zip = os.path.join(carpeta_destino, nombre_zip)
    
    print(f"--- 📦 Iniciando copia de seguridad: {nombre_zip} ---")
    
    count_archivos = 0
    archivos_saltados = 0

    try:
        with zipfile.ZipFile(ruta_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
            
            for root, dirs, files in os.walk(root_dir):
                # A. Filtro de carpetas
                # Modificamos la lista dirs in-place para que os.walk no entre en las ignoradas
                dirs[:] = [d for d in dirs if d not in carpetas_ignorar]
                
                # Caso especial: Si estamos dentro de 'instance', asegurarnos de guardar la DB
                es_carpeta_instance = os.path.basename(root) == 'instance'

                for file in files:
                    file_path = os.path.join(root, file)
                    
                    # B. Validaciones de seguridad
                    # 1. No copiarnos a nosotros mismos ni a otros zips de respaldo
                    if file == os.path.basename(__file__) or file.endswith('.zip'):
                        continue
                        
                    # 2. Verificar extensiones ignoradas
                    _, ext = os.path.splitext(file)
                    if ext in extensiones_ignorar:
                        continue

                    # 3. Verificar permisos de lectura (Evita crash por archivos bloqueados)
                    if not os.access(file_path, os.R_OK):
                        print(f"⚠️  Permiso denegado/Bloqueado: {file}")
                        archivos_saltados += 1
                        continue

                    # C. Guardar el archivo
                    try:
                        # Calcular ruta relativa para que el ZIP tenga la estructura correcta
                        arcname = os.path.relpath(file_path, start=root_dir)
                        zipf.write(file_path, arcname)
                        count_archivos += 1
                        
                        # Feedback visual simple cada 100 archivos
                        if count_archivos % 100 == 0:
                            print(f"   ... procesados {count_archivos} archivos ...")
                            
                    except PermissionError:
                        print(f"⚠️  Error de Permiso al escribir: {file}")
                        archivos_saltados += 1
                    except Exception as e_file:
                        print(f"⚠️  Error inesperado en {file}: {e_file}")
                        archivos_saltados += 1
                        
        print("-" * 40)
        print(f"✅ ¡Copia de seguridad EXITOSA!")
        print(f"📊 Total archivos: {count_archivos}")
        if archivos_saltados > 0:
            print(f"⚠️  Archivos no copiados: {archivos_saltados}")
        print(f"💾 Guardado en: {ruta_zip}")
        print("-" * 40)
        
    except Exception as e:
        print(f"❌ Error CRÍTICO al crear el backup: {e}")

if __name__ == "__main__":
    crear_backup()