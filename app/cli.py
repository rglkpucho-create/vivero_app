import click
from flask.cli import with_appcontext
from werkzeug.security import generate_password_hash
from app.extensions import db
from app.models import Rol, Usuario, Empresa, Especie, Insumo, UnidadMedida
import os
import zipfile
import datetime
import subprocess
import shutil

@click.command('seed-roles')
@with_appcontext
def seed_roles():
    """Inicializar la base de datos con Roles, Empresa HQ y el SuperAdmin."""
    # 1. CREAR ROLES (incluyendo SuperAdmin)
    roles_data = [
        {'nombre': 'SuperAdmin', 'nivel': 0, 'descripcion': 'Proveedor del software — Control total de todas las empresas'},
        {'nombre': 'Admin', 'nivel': 1, 'descripcion': 'Control total de su empresa'},
        {'nombre': 'Gerente', 'nivel': 2, 'descripcion': 'Gestión de reportes, compras, ventas y costos'},
        {'nombre': 'Operario', 'nivel': 3, 'descripcion': 'Registro de labores de campo, alimentación y producción'},
        {'nombre': 'Visor', 'nivel': 4, 'descripcion': 'Solo lectura (Dashboard y Listas)'}
    ]
    
    for r_data in roles_data:
        r = Rol.query.filter_by(nombre=r_data['nombre']).first()
        if not r:
            r = Rol(**r_data)
            db.session.add(r)
            click.echo(f"  [+] Rol '{r_data['nombre']}' creado.")
        else:
            r.nivel = r_data['nivel']
            r.descripcion = r_data['descripcion']
            click.echo(f"  [*] Rol '{r_data['nombre']}' actualizado.")
            
    db.session.commit()
    
    # 2. CREAR EMPRESA HQ (tu empresa como proveedor del software)
    hq = Empresa.query.filter_by(nombre='EcoSistem HQ').first()
    if not hq:
        hq = Empresa(
            nombre='EcoSistem HQ',
            razon_social='EcoSistem Software S.A.S.',
            email='admin@ecosistem.com',
            licencia_activa=True,
            notas_admin='Empresa interna del proveedor del software.'
        )
        db.session.add(hq)
        db.session.commit()
        click.echo("  [+] Empresa 'EcoSistem HQ' creada.")
    else:
        click.echo("  [*] Empresa 'EcoSistem HQ' ya existe.")
    
    # 3. CREAR SUPERADMIN (tú como proveedor del software)
    superadmin_email = "admin@ecosistem.com"
    superadmin_password = "Admin123!"
    
    u = Usuario.query.filter_by(email=superadmin_email).first()
    if u:
        u.es_superadmin = True
        u.empresa_id = hq.id
        u.activo = True
        u.set_password(superadmin_password)
        
        # Asignar rol SuperAdmin
        sa_rol = Rol.query.filter_by(nivel=0).first()
        if sa_rol:
            u.rol_id = sa_rol.id
        
        db.session.commit()
        click.echo(f"  [*] SuperAdmin '{superadmin_email}' actualizado.")
    else:
        sa_rol = Rol.query.filter_by(nivel=0).first()
        u = Usuario(
            nombre_completo="Administrador EcoSistem",
            email=superadmin_email,
            telefono="0000000000",
            rol_id=sa_rol.id if sa_rol else None,
            empresa_id=hq.id,
            activo=True,
            es_superadmin=True
        )
        u.set_password(superadmin_password)
        db.session.add(u)
        db.session.commit()
        click.echo(f"  [+] SuperAdmin '{superadmin_email}' creado.")

    click.echo("\n" + "="*50)
    click.echo("  SEED COMPLETADO EXITOSAMENTE")
    click.echo("="*50)

@click.command('seed-demo')
@with_appcontext
def seed_demo():
    """Cargar datos de demostración completos para pruebas (OJO: Resetea y carga datos premium)."""
    confirm = click.confirm('⚠️ Esto limpiará la base de datos y cargará datos de prueba completos de viveros, insumos, lotes y ventas. ¿Continuar?', abort=True)
    if confirm:
        try:
            from seed_data import generate_premium_seed_data
            generate_premium_seed_data()
            click.echo("✅ Seed de demostración completado con éxito.")
        except Exception as e:
            click.echo(f"❌ Error al ejecutar seed-demo: {e}")

@click.command('seed-especies')
@with_appcontext
def seed_especies():
    """Cargar el catálogo completo de especies botánicas curadas (MinarEspecies)."""
    try:
        from MinarEspecies import especies_data
    except ImportError:
        click.echo("❌ Error: No se pudo importar MinarEspecies.py")
        return

    conteo = 0
    for data in especies_data:
        existe = Especie.query.filter_by(nombre_comun=data['nombre_comun']).first()
        if not existe:
            nueva = Especie(
                nombre_comun=data['nombre_comun'],
                nombre_cientifico=data.get('nombre_cientifico'),
                dias_ciclo_estimado=data.get('dias_ciclo_estimado', 90),
                detalles_cuidado=data.get('detalles_cuidado'),
                precio_venta_sugerido=data.get('precio_venta_sugerido', 15000.0),
                imagen_url=None
            )
            db.session.add(nueva)
            conteo += 1
            click.echo(f"   + Agregada: {data['nombre_comun']}")
        else:
            click.echo(f"   . Saltada (ya existe): {data['nombre_comun']}")

    db.session.commit()
    click.echo(f"[*] Proceso finalizado. {conteo} nuevas especies botánicas registradas.")

@click.command('seed-insumos')
@with_appcontext
def seed_insumos():
    """Cargar el inventario base completo de insumos (sustratos, fertilizantes, macetas)."""
    try:
        from MinarInsumos import insumos_data
    except ImportError:
        click.echo("❌ Error: No se pudo importar MinarInsumos.py")
        return

    # 1. Asegurar Unidades de Medida
    unidades_base = [('Kg', 'Kilogramo'), ('L', 'Litro'), ('Und', 'Unidad'), ('Bto', 'Bulto'), ('M3', 'Metro Cúbico')]
    unidades_map = {}

    for abreviatura, nombre in unidades_base:
        unidad = UnidadMedida.query.filter_by(abreviatura=abreviatura).first()
        if not unidad:
            unidad = UnidadMedida(nombre=nombre, abreviatura=abreviatura)
            db.session.add(unidad)
        unidades_map[abreviatura] = unidad
    
    db.session.commit()
    for u in UnidadMedida.query.all():
        unidades_map[u.abreviatura] = u

    conteo = 0
    for data in insumos_data:
        existe = Insumo.query.filter_by(nombre=data['nombre']).first()
        if not existe:
            unidad_obj = unidades_map.get(data.get('unidad'), unidades_map.get('Und'))
            nuevo = Insumo(
                nombre=data['nombre'],
                codigo=data.get('codigo'),
                tipo=data.get('tipo', 'Insumo'),
                unidad_medida_id=unidad_obj.id if unidad_obj else None,
                stock_minimo=data.get('stock_minimo', 5.0),
                cantidad_actual=data.get('cantidad_actual', 0.0),
                costo_promedio=data.get('costo_promedio', 0.0),
                precio_venta=data.get('precio_venta', 0.0)
            )
            db.session.add(nuevo)
            conteo += 1
            click.echo(f"   + Insumo: {data['nombre']}")
        else:
            click.echo(f"   . Saltado (ya existe): {data['nombre']}")

    db.session.commit()
    click.echo(f"[*] Proceso finalizado. {conteo} nuevos insumos registrados.")

@click.command('backup')
@with_appcontext
def backup():
    """Crear un backup completo del proyecto (código + base de datos)."""
    from backup_pro import crear_backup_completo
    crear_backup_completo()

@click.command('restore')
@with_appcontext
def restore():
    """Restaurar un backup existente desde la carpeta backups/."""
    from restore import restaurar_copia
    restaurar_copia()

def register_cli_commands(app):
    app.cli.add_command(seed_roles)
    app.cli.add_command(seed_demo)
    app.cli.add_command(seed_especies)
    app.cli.add_command(seed_insumos)
    app.cli.add_command(backup)
    app.cli.add_command(restore)
