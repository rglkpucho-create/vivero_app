# Sistema Integrado de Gestión Agrícola (ERP Vivero)

Arquitectura backend modular desarrollada en Python para la administración centralizada de un ecosistema agrícola y pecuario. Diseñado bajo principios de seguridad y persistencia de datos.

## 🚀 Características Principales

* **Módulo de Inventario:** Control estricto de insumos y especies frutales.
* **Módulo de Ventas y Clientes:** Trazabilidad financiera con implementación de *Soft Delete* (Borrado Lógico) para proteger la integridad de los registros contables.
* **Seguridad (Zero Trust):** Validación estricta de tipos de datos en la capa de entrada para prevenir inyecciones.
* **Módulo Pecuario:** Registro y control de biomasa animal.

## 🛠️ Stack Tecnológico

* **Backend:** Python 3.11, Flask
* **ORM & Base de Datos:** SQLAlchemy, SQLite (Migrable a PostgreSQL)
* **Arquitectura:** Monolito Modular, Principios SOLID

## 📸 Demo Visual del Sistema

*(Nota: Agrega aquí 3 o 4 pantallazos de tu aplicación corriendo localmente. Ej: El Dashboard principal, la lista de ventas, y el registro de un lote).*

* [Pantallazo 1: Dashboard]
* [Pantallazo 2: Gestión de Ventas]

## ⚙️ Despliegue Local (Para revisión técnica)

Si un Líder Técnico desea auditar el código localmente:

```bash
# Clonar el repositorio
git clone [https://github.com/rglkpucho-create/vivero_app.git](https://github.com/rglkpucho-create/vivero_app.git)

# Entrar a la carpeta
cd vivero_app

# Crear y activar entorno virtual
python -m venv env
source env/Scripts/activate

# Instalar dependencias
pip install -r requirements.txt

# Ejecutar el servidor
python run.py