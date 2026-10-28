"""
Script para inicializar la base de datos con Roles, Empresa HQ y el SuperAdmin.
Ejecutar una sola vez: python seed_roles.py
"""
import os
from werkzeug.security import generate_password_hash
from app import create_app
from app.extensions import db
from app.models import Rol, Usuario, Empresa

app = create_app()

def seed():
    with app.app_context():
        # =============================================
        # 1. CREAR ROLES (incluyendo SuperAdmin)
        # =============================================
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
                print(f"  ✅ Rol '{r_data['nombre']}' creado.")
            else:
                r.nivel = r_data['nivel']
                r.descripcion = r_data['descripcion']
                print(f"  🔄 Rol '{r_data['nombre']}' actualizado.")
                
        db.session.commit()
        
        # =============================================
        # 2. CREAR EMPRESA HQ (tu empresa como proveedor del software)
        # =============================================
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
            print("  ✅ Empresa 'EcoSistem HQ' creada.")
        else:
            print("  🔄 Empresa 'EcoSistem HQ' ya existe.")
        
        # =============================================
        # 3. CREAR SUPERADMIN (tú como proveedor del software)
        # =============================================
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
            print(f"  🔄 SuperAdmin '{superadmin_email}' actualizado.")
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
            print(f"  ✅ SuperAdmin '{superadmin_email}' creado.")

        print("\n" + "="*50)
        print("  SEED COMPLETADO EXITOSAMENTE")
        print("="*50)
        print(f"\n  📧 Email:      {superadmin_email}")
        print(f"  🔑 Contraseña: {superadmin_password}")
        print(f"  🏢 Empresa:    {hq.nombre}")
        print(f"  👑 Rol:        SuperAdmin")
        print(f"\n  Inicia sesión y ve a SuperAdmin > Empresas para")
        print(f"  registrar tus clientes (viveros/fincas).")
        print("="*50)

if __name__ == "__main__":
    seed()
