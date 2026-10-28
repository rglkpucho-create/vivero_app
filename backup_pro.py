import os
import zipfile
import datetime
import subprocess
import shutil

from dotenv import load_dotenv

# Cargar variables de entorno si existen
load_dotenv()

# =================CONFIGURACIÓN=================
NOMBRE_BASE_ZIP = "Respaldo_EcoSistem_PRO"
DB_NAME = os.environ.get("DB_NAME", "ecosistem_v4")
DB_USER = os.environ.get("DB_USER", "root")
DB_PASS = os.environ.get("DB_PASS", "")
DB_HOST = os.environ.get("DB_HOST", "localhost")

# Carpetas donde suele esconderse mysqldump en Windows
RUTAS_POSIBLES_MYSQLDUMP = [
    r"C:\xampp\mysql\bin\mysqldump.exe",
    r"C:\wamp64\bin\mysql\mysql*\bin\mysqldump.exe",
    r"C:\laragon\bin\mysql\mysql*\bin\mysqldump.exe",
    r"C:\Program Files\MySQL\MySQL Server*\bin\mysqldump.exe",
    "mysqldump" # Por si está en el PATH del sistema
]
# ===============================================

def encontrar_mysqldump():
    """Busca el ejecutable mysqldump en rutas comunes."""
    import glob
    for ruta in RUTAS_POSIBLES_MYSQLDUMP:
        # Manejar comodines (*)
        for encontrada in glob.glob(ruta):
            if os.path.exists(encontrada):
                return encontrada
            
        # Revisar si es un comando directo
        if ruta == "mysqldump":
            if shutil.which("mysqldump"):
                return "mysqldump"
    return None

def crear_backup_completo():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    ahora = datetime.datetime.now()
    timestamp = ahora.strftime("%Y-%m-%d_%H-%M")
    
    # Archivos temporales y finales
    archivo_sql = os.path.join(root_dir, f"db_dump_{timestamp}.sql")
    nombre_zip = f"{NOMBRE_BASE_ZIP}_{timestamp}.zip"
    carpeta_backups = os.path.join(root_dir, "backups")
    ruta_zip_final = os.path.join(carpeta_backups, nombre_zip)

    if not os.path.exists(carpeta_backups):
        os.makedirs(carpeta_backups)

    print(f"\n--- [*] INICIANDO BACKUP PROFESIONAL: {timestamp} ---")

    # 1. INTENTAR EXPORTAR BASE DE DATOS (MySQL / SQLite)
    print("Step 1: Buscando base de datos...")
    mysqldump_exe = encontrar_mysqldump()
    db_exito = False

    if mysqldump_exe and DB_PASS:
        print(f"   [+] Herramienta encontrada: {mysqldump_exe}")
        print("   [*] Exportando datos MySQL...")
        cmd = [mysqldump_exe, "-u", DB_USER, "-h", DB_HOST, DB_NAME]
        cmd.insert(2, f"-p{DB_PASS}")
        try:
            with open(archivo_sql, "w", encoding="utf-8") as f:
                subprocess.check_call(cmd, stdout=f)
            print(f"   [+] Base de datos MySQL exportada: {os.path.basename(archivo_sql)}")
            db_exito = True
        except Exception as e:
            print(f"   [!] Error al exportar MySQL: {e}")
            if os.path.exists(archivo_sql): os.remove(archivo_sql)
    else:
        # Fallback o base de datos SQLite local
        sqlite_file = os.path.join(root_dir, f"{DB_NAME}.db")
        if os.path.exists(sqlite_file):
            print(f"   [*] Detectada base de datos SQLite local: {os.path.basename(sqlite_file)}")
            print("   [*] Generando volcado SQL nativo...")
            try:
                import sqlite3
                with sqlite3.connect(sqlite_file) as conn, open(archivo_sql, "w", encoding="utf-8") as f:
                    for line in conn.iterdump():
                        f.write(f"{line}\n")
                print(f"   [+] Base de datos SQLite exportada a SQL: {os.path.basename(archivo_sql)}")
                db_exito = True
            except Exception as e:
                print(f"   [!] Error exportando SQLite: {e}")
        else:
            print("   [!] AVISO: No se encontró mysqldump ni archivo SQLite .db.")

    # 2. COMPRIMIR TODO (CÓDIGO + SQL)
    print("\nStep 2: Comprimiendo archivos...")
    
    carpetas_ignorar = {'env', 'venv', '__pycache__', '.git', '.vscode', '.idea', 'backups', '.vs', 'node_modules'}
    extensiones_ignorar = {'.pyc', '.pyo', '.pyd'}
    count = 0

    try:
        with zipfile.ZipFile(ruta_zip_final, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Si se creó el SQL, agregarlo primero
            if db_exito and os.path.exists(archivo_sql):
                zipf.write(archivo_sql, os.path.basename(archivo_sql))
                count += 1

            for root, dirs, files in os.walk(root_dir):
                dirs[:] = [d for d in dirs if d not in carpetas_ignorar]
                
                for file in files:
                    # Ignorar temporales, backups y scripts
                    if file == os.path.basename(__file__) or file.endswith('.zip') or file.startswith("db_dump_"):
                        continue
                    if os.path.splitext(file)[1] in extensiones_ignorar:
                        continue
                    
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, start=root_dir)
                    
                    try:
                        zipf.write(file_path, arcname)
                        count += 1
                    except: pass

        # 3. LIMPIEZA
        if db_exito and os.path.exists(archivo_sql):
            os.remove(archivo_sql)
            print("\nStep 3: Limpieza completada.")

        print("-" * 50)
        print(f"[+] BACKUP FINALIZADO CON ÉXITO")
        if db_exito:
            print(f"[*] ESTADO: COMPLETO (CÓDIGO + BASE DE DATOS)")
        else:
            print(f"[!] ESTADO: PARCIAL (SOLO CÓDIGO)")
        print(f"[*] Archivo: {ruta_zip_final}")
        print("-" * 50)

    except Exception as e:
        print(f"[!] Error crítico: {e}")

if __name__ == "__main__":
    crear_backup_completo()