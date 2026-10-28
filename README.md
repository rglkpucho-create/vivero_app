# 🌿 EcoSistem — Sistema Integrado de Gestión Agropecuaria

EcoSistem es un ERP multi-tenant (SaaS) desarrollado en Python y Flask para la administración centralizada de ecosistemas agrícolas (viveros, cultivos) y pecuarios. Diseñado bajo estrictos principios de seguridad, segregación de datos y alta trazabilidad.

## 🚀 Características Principales

* **Arquitectura Multi-Tenant:** Un solo despliegue sirve a múltiples fincas/viveros, cada uno con aislamiento de datos absoluto mediante `empresa_id` y middleware de validación cruzada.
* **Módulo de Inventario:** Control de insumos (sustratos, fertilizantes) y productos terminados con valoración FIFO automática.
* **Módulo de Producción Agrícola:** Gestión de lotes, siembras, labores de campo y registro de consumos.
* **Módulo Pecuario (Nivel Pro):** Trazabilidad individual o por lotes, historial médico (eventos sanitarios), y producción animal.
* **Módulo Comercial (POS):** Ventas directas, gestión de facturación, y compras (proveedores, órdenes de pedido).
* **Seguridad y Auditoría:** Protección contra IDOR en toda la capa de acceso, logs de auditoría para operaciones críticas, sanitización de inputs, subida controlada de archivos y limitación de peticiones (Rate Limiting).

## 🛠️ Stack Tecnológico

* **Backend:** Python 3.11, Flask 3.1.1
* **ORM & Base de Datos:** SQLAlchemy, MySQL 8.0 (vía Docker) o SQLite (fallback local).
* **Frontend:** Vanilla HTML/CSS/JS con Bootstrap 5.3, SweetAlert2 y Lucide Icons. (Sin frameworks pesados, assets optimizados).
* **Infraestructura:** Docker & Docker Compose con `waitress` como servidor WSGI de producción.

## ⚙️ Comandos CLI Disponibles

El proyecto integra comandos CLI nativos de Flask para simplificar las operaciones administrativas y de despliegue:

```bash
# Crear la estructura base de la aplicación (Roles, SuperAdmin y Empresa HQ)
flask seed-roles

# Cargar un catálogo predefinido de especies cultivables adaptadas al trópico
flask seed-especies

# Cargar un inventario base de insumos (abonos, sustratos, macetas)
flask seed-insumos

# (Atención: destructivo) Eliminar base de datos y generar data mock para pruebas
flask seed-demo

# Crear y restaurar respaldos locales (código + base de datos)
flask backup
flask restore
```

## 🐳 Despliegue Local con Docker (Recomendado)

El sistema está configurado para levantar una instancia productiva con MySQL de forma automática mediante Docker Compose.

```bash
# 1. Clonar el repositorio
git clone https://github.com/rglkpucho-create/vivero_app.git
cd vivero_app

# 2. Configurar variables de entorno (Opcional, si deseas cambiar credenciales por defecto)
cp .env.example .env

# 3. Levantar la aplicación web y la base de datos MySQL en segundo plano
docker-compose up -d --build

# 4. (Solo la primera vez) Crear la estructura inicial
docker exec -it vivero_web flask db upgrade  # (Si usas Flask-Migrate) o espera la autoconstrucción.
docker exec -it vivero_web flask seed-roles
```

Visita `http://localhost:5000` en tu navegador.
* **Usuario:** `admin@ecosistem.com`
* **Contraseña:** `Admin123!`

## 🧑‍💻 Desarrollo Local Sin Docker (Modo SQLite Fallback)

Si prefieres desarrollar directamente en tu sistema operativo:

```bash
python -m venv env
source env/Scripts/activate  # (En Windows: env\Scripts\activate)
pip install -r requirements.txt

# Inicializa los datos básicos
flask seed-roles

# Ejecuta el servidor de desarrollo
python run.py
```