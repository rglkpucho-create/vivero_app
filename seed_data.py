"""
Script de Carga de Datos (Seeder Premium) para EcoSistem.
Genera exactamente 10 registros altamente realistas y detallados
de cada entidad (Viveros/Empresas, Sedes, Proveedores, Insumos,
Especies, Lotes de Producción, Clientes, Ventas POS, Razas y Lotes de Animales).
Utiliza perfiles en español con datos reales de la geografía y agricultura de Colombia.
"""
import os
import random
from datetime import datetime, timedelta, timezone
from app import create_app
from app.extensions import db
from app.models import (
    Empresa, Usuario, Rol, Sede, UnidadMedida, Insumo, LoteInsumo, MovimientoInventario,
    PedidoCompra, DetallePedidoCompra, Especie, LoteProduccion, LaborCampo, ConsumoInsumo,
    Cliente, Venta, DetalleVenta, RazaAnimal, LoteAnimal, ProduccionAnimal, ConsumoAnimal, EventoSanitario,
    Proveedor
)

def generate_premium_seed_data():
    app = create_app('default')
    with app.app_context():
        print("====== INICIANDO RESET Y CARGA DE DATOS PREMIUM ======")
        
        # 1. Resetear base de datos (Database-agnostic Drop & Create)
        print("1. Limpiando tablas de base de datos...")
        db.drop_all()
        db.create_all()
        print(" -> Tablas creadas con éxito.")

        # 2. Crear Roles del Sistema
        print("2. Creando Roles...")
        roles_data = [
            Rol(id=1, nombre='SuperAdmin', descripcion='Proveedor del software — Control total de todas las empresas', nivel=0),
            Rol(id=2, nombre='Administrador', descripcion='Acceso completo administrativo de la empresa', nivel=1),
            Rol(id=3, nombre='Gerente', descripcion='Gestión operativa y reportes', nivel=2),
            Rol(id=4, nombre='Operario', descripcion='Registro de labores de campo y consumos', nivel=3),
            Rol(id=5, nombre='Visor', descripcion='Solo lectura para auditoría y visualización', nivel=4)
        ]
        db.session.add_all(roles_data)
        db.session.commit()
        print(" -> 5 Roles del sistema creados.")

        # 3. Crear Empresa HQ y 10 Viveros/Empresas Reales de Colombia
        print("3. Creando Empresas...")
        hq = Empresa(
            nombre='EcoSistem HQ',
            razon_social='EcoSistem Software S.A.S.',
            email='admin@ecosistem.com',
            licencia_activa=True,
            plan_nombre='Plan Agro-Hacienda',
            notas_admin='Empresa interna del proveedor del software.'
        )
        db.session.add(hq)
        db.session.commit()

        empresas_detalles = [
            ("Vivero El Edén Forestal", "901.234.567-1", "Vivero El Edén Forestal S.A.S.", "3104567890", "contacto@edenforestal.com", "Calle 10 # 43-21", "Medellín", "uploads/logos/logo_eden.png", "www.edenforestal.com"),
            ("Jardín Botánico del Norte", "901.234.567-2", "Inversiones Botánicas Bogotá Ltda.", "3208765432", "info@botaniconorte.com", "Carrera 7 # 156-80", "Bogotá", None, "www.botaniconorte.com"),
            ("Vivero Valle Verde", "901.234.567-3", "Agrícola Valle Verde S.A.S.", "3159876543", "ventas@valleverde.com", "Km 4 Vía Palmira", "Palmira", None, "www.valleverde.com"),
            ("Finca La Pradera & Vivero", "901.234.567-4", "Finca Agroecológica La Pradera", "3113456789", "contacto@lapradera.com", "Vereda Mensulí Km 2", "Piedecuesta", None, "www.lapradera.com"),
            ("EcoJardines de la Costa", "901.234.567-5", "Jardinería y Paisajismo del Caribe SAS", "3007654321", "soporte@ecojardines.com", "Vía al Mar Km 11", "Barranquilla", None, "www.ecojardines.com"),
            ("Vivero Los Andes", "901.234.567-6", "Cultivos Los Andes Manizales Ltda.", "3128904321", "contacto@viverolosandes.com", "Km 7 Vía al Nevado", "Manizales", None, "www.viverolosandes.com"),
            ("Paraíso de las Orquídeas", "901.234.567-7", "Comercializadora de Flores de Risaralda", "3145671234", "flores@paraisoorquideas.com", "Variante Condina Km 3", "Pereira", None, "www.paraisoorquideas.com"),
            ("Vivero Semillas del Futuro", "901.234.567-8", "Semillas del Futuro Huila SAS", "3182345678", "semillas@futuro.com", "Carrera 5 # 22-10", "Neiva", None, "www.semillasdelfuturo.com"),
            ("Finca Bella Vista & Vivero", "901.234.567-9", "Sociedad Agropecuaria Bella Vista", "3134567890", "administracion@bellavista.com", "Km 12 Vía al Totumo", "Ibagué", None, "www.fincabellavista.com"),
            ("Vivero Amazonía Verde", "901.234.567-0", "Vivero Exótico del Meta SAS", "3216540987", "ventas@amazoniaverde.com", "Km 3 Vía Acacías", "Villavicencio", None, "www.amazoniaverde.com")
        ]
        
        empresas = []
        for index, emp in enumerate(empresas_detalles):
            nombre, nit, razon, tel, email, dir_fisica, ciudad, logo, web = emp
            # Licencias activas por defecto, algunas vencen el próximo año
            e = Empresa(
                nombre=nombre,
                nit_rut=nit,
                razon_social=razon,
                telefono=tel,
                email=email,
                direccion=dir_fisica,
                ciudad=ciudad,
                logo_url=logo,
                sitio_web=web,
                licencia_activa=True,
                plan_nombre='Plan Cosecha Pro' if index % 2 == 0 else 'Plan Agro-Hacienda',
                fecha_vencimiento=datetime.now(timezone.utc).date() + timedelta(days=365)
            )
            db.session.add(e)
            empresas.append(e)
        db.session.commit()
        print(" -> Empresa HQ y 10 Viveros registrados con éxito.")

        # 4. Crear Usuarios
        print("4. Creando Usuarios...")
        # SuperAdmin General del Software
        super_rol = Rol.query.filter_by(nivel=0).first()
        admin_rol = Rol.query.filter_by(nivel=1).first()
        
        super_user = Usuario(
            nombre_completo='Administrador EcoSistem',
            email='admin@ecosistem.com',
            telefono='3000000000',
            activo=True,
            rol_id=super_rol.id if super_rol else 1,
            empresa_id=hq.id,
            es_superadmin=True
        )
        super_user.set_password('Admin123!')
        db.session.add(super_user)

        # 10 Administradores distribuidos en las empresas cliente
        usuarios = []
        for i in range(len(empresas)):
            emp_obj = empresas[i]
            admin_user = Usuario(
                nombre_completo=f"Admin {emp_obj.nombre.split()[-1]}",
                email=f"admin@{emp_obj.nombre.lower().replace(' ', '').replace('&', '').replace('í', 'i').replace('é', 'e').replace('á', 'a').replace('ó', 'o').replace('ú', 'u')}.com",
                telefono=f"300123456{i}",
                rol_id=admin_rol.id if admin_rol else 2,
                empresa_id=emp_obj.id,
                activo=True
            )
            admin_user.set_password('Admin123!')
            db.session.add(admin_user)
            usuarios.append(admin_user)
        db.session.commit()
        print(" -> Usuarios creados (SuperAdmin HQ y Admins de Viveros).")

        # 5. Crear 10 Sedes reales de producción
        print("5. Creando 10 Sedes...")
        nombres_sedes = [
            ("Lote Invernadero Clima Templado", "Vivero"),
            ("Invernadero Clima Frío Orquídeas", "Vivero"),
            ("Finca Lote Enraizamiento", "Finca"),
            ("Bodega Climatizada de Despachos", "Bodega"),
            ("Invernadero de Propagación Rápida", "Vivero"),
            ("Parcela de Aclimatación Sombrío", "Finca"),
            ("Bodega Central de Sustratos", "Bodega"),
            ("Lote Plantulación Cítricos", "Vivero"),
            ("Finca Crecimiento Forestales", "Finca"),
            ("Invernadero Automatizado Hidroponía", "Vivero")
        ]
        
        sedes = []
        for i in range(10):
            emp_obj = empresas[i % 9] # Distribuidos entre las empresas
            nombre_sede, tipo_sede = nombres_sedes[i]
            s = Sede(
                empresa_id=emp_obj.id,
                nombre=nombre_sede,
                tipo=tipo_sede,
                ubicacion_geo=f"Coordenadas: Lat 6.2{i}12, Lon -75.5{i}43"
            )
            db.session.add(s)
            sedes.append(s)
        db.session.commit()
        print(" -> 10 Sedes registradas.")

        # 6. Crear Unidades de Medida Básicas
        print("6. Creando Unidades de Medida...")
        unidades = [
            UnidadMedida(id=1, nombre='Unidad', abreviatura='Und'),
            UnidadMedida(id=2, nombre='Kilogramo', abreviatura='Kg'),
            UnidadMedida(id=3, nombre='Litro', abreviatura='L'),
            UnidadMedida(id=4, nombre='Bulto 50Kg', abreviatura='Bto')
        ]
        db.session.add_all(unidades)
        db.session.commit()
        print(" -> 4 Unidades de medida listas.")

        # 7. Crear 10 Proveedores de Suministros Agrícolas
        print("7. Creando 10 Proveedores...")
        proveedores_nombres = [
            "Distribuidora NutriCampo S.A.", "Plásticos y Riego Tecnificado SAS",
            "Semillas de los Andes Ltda.", "Abonos Orgánicos del Cauca",
            "Herramientas Hércules Colombia", "Materas de Barro Pitalito",
            "Fertilizantes y Químicos del Caribe", "Sustratos y Turbas de Importación",
            "AgroLínea de Occidente", "Equipamiento Agropecuario del Tolima"
        ]
        
        proveedores = []
        for i in range(10):
            emp_obj = empresas[i % 9]
            p = Proveedor(
                empresa_id=emp_obj.id,
                razon_social=proveedores_nombres[i],
                nit_rut=f"800.{i+1}42.98{i}-{i}",
                contacto_nombre=f"Contacto {proveedores_nombres[i].split()[0]}",
                telefono=f"315{i}765432",
                email=f"ventas@{proveedores_nombres[i].lower().replace(' ', '').replace('.', '')}.com",
                direccion=f"Zona Industrial # {i+1}0 - {i*5}"
            )
            db.session.add(p)
            proveedores.append(p)
        db.session.commit()
        print(" -> 10 Proveedores agrícolas distribuidos creados.")

        # 8. Crear 10 Clientes de Consumo
        print("8. Creando 10 Clientes...")
        clientes_nombres = [
            "Juan Carlos Restrepo", "María Camila Ortiz", "Andrés Felipe Gómez",
            "Diana Marcela Duarte", "Carlos Mario Zuluaga", "Sandra Patricia Beltrán",
            "Jorge Iván Bedoya", "Gloria Estela Rincón", "Mauricio Alejandro Valencia",
            "Liliana María Hoyos"
        ]
        
        clientes = []
        for i in range(10):
            emp_obj = empresas[i % 9]
            c = Cliente(
                empresa_id=emp_obj.id,
                nombre=clientes_nombres[i],
                documento=f"1.0{i}7.543.21{i}",
                telefono=f"321765432{i}",
                email=f"{clientes_nombres[i].lower().replace(' ', '')}@gmail.com",
                direccion=f"Calle {i*3} # {i+1}2 - {i+4} de la ciudad"
            )
            db.session.add(c)
            clientes.append(c)
        db.session.commit()
        print(" -> 10 Clientes registrados.")

        # 9. Crear 10 Insumos/Mercancías del Inventario (Con precio_venta!)
        print("9. Creando 10 Insumos/Productos Comerciales...")
        insumos_datos = [
            ("Maceta de Barro Cocido Nº 12", "Matera", 1, 150.0, 3200.0, 7500.0),
            ("Sustrato Nutritivo Profesional 10Kg", "Producto Comercial", 2, 80.0, 11500.0, 22000.0),
            ("Humus de Lombriz Líquido 1L", "Producto Comercial", 3, 120.0, 8000.0, 18000.0),
            ("Tijeras de Poda Heavy Duty", "Herramienta", 1, 25.0, 21000.0, 45000.0),
            ("Regadera Plástica Premium 5L", "Herramienta", 1, 40.0, 13000.0, 28000.0),
            ("Fertilizante Triple 15 Soluble 1Kg", "Producto Comercial", 2, 200.0, 7900.0, 16500.0),
            ("Sustrato de Fibra de Coco Block", "Producto Comercial", 4, 60.0, 5500.0, 12000.0),
            ("Insecticida Orgánico Neem 250ml", "Producto Comercial", 3, 90.0, 11000.0, 24000.0),
            ("Maceta de Cerámica Esmaltada G", "Matera", 1, 35.0, 25000.0, 55000.0),
            ("Hormona Enraizadora en Polvo 100g", "Producto Comercial", 2, 70.0, 9200.0, 19500.0)
        ]
        
        insumos = []
        for i in range(10):
            emp_obj = empresas[i % 9]
            nombre, tipo, unidad_id, stock, costo, precio = insumos_datos[i]
            
            ins = Insumo(
                empresa_id=emp_obj.id,
                codigo=f"SKU-COM-100{i}",
                nombre=nombre,
                tipo=tipo,
                unidad_medida_id=unidad_id,
                stock_minimo=10.0,
                cantidad_actual=stock,
                costo_promedio=costo,
                precio_venta=precio
            )
            db.session.add(ins)
            db.session.flush() # para id
            
            # Cargar lote de inventario inicial para FIFO
            lote_i = LoteInsumo(
                insumo_id=ins.id,
                fecha_compra=datetime.now(timezone.utc).date() - timedelta(days=20),
                cantidad_inicial=stock,
                cantidad_actual=stock,
                costo_unitario=costo
            )
            db.session.add(lote_i)
            
            # Movimiento Kardex inicial
            kard = MovimientoInventario(
                tipo_movimiento='Inventario Inicial',
                cantidad=stock,
                costo_unitario=costo,
                referencia="Carga inicial del sistema",
                insumo_id=ins.id,
                fecha=datetime.now(timezone.utc) - timedelta(days=20)
            )
            db.session.add(kard)
            insumos.append(ins)
        db.session.commit()
        print(" -> 10 Insumos y mercancías con costo y precio cargados en Kardex.")

        # 10. Crear 10 Especies Hortícolas/Ornamentales Reales con precio sugerido
        print("10. Creando 10 Especies Botánicas...")
        especies_detalles = [
            ("Orquídea Phalaenopsis Blanca", "Phalaenopsis amabilis", 120, "Humedad alta, luz indirecta, regar solo cuando las raíces estén grises. Sustrato de pino.", 75000.0),
            ("Bonsái Higo Ficus", "Ficus microcarpa", 240, "Sol directo de mañana, poda constante de mantenimiento y control estricto de humedad del sustrato.", 120000.0),
            ("Palma de Cera del Quindío", "Ceroxylon quindiuense", 360, "Especie nacional de crecimiento lento. Clima templado a frío, riego constante y sombreado inicial.", 45000.0),
            ("Anturio Rojo Premium", "Anthurium andraeanum", 90, "Follaje brillante, requiere riego moderado, abono rico en fósforo cada 30 días para forzar floración.", 35000.0),
            ("Suculenta Echeveria Rosa", "Echeveria elegans", 45, "Muy bajo riego. Exposición solar directa de mínimo 6 horas. Sustrato poroso y arenoso drenable.", 8000.0),
            ("Jazmín del Cabo", "Gardenia jasminoides", 75, "Flores blancas muy fragantes. Suelo ácido, riego frecuente con agua libre de cal y abono de hierro.", 28000.0),
            ("Hortensia Azul Silvestre", "Hydrangea macrophylla", 80, "Sombra parcial, riego diario abundante. Color azul depende de la acidez del suelo (pH bajo con sulfato).", 32000.0),
            ("Lavanda Francesa Aromática", "Lavandula dentata", 50, "Aromática excelente. Sol pleno, riego escaso, suelo calcáreo con excelente drenaje para evitar hongos.", 12000.0),
            ("Menta Piperita Orgánica", "Mentha piperita", 30, "Crecimiento invasivo rápido. Riego abundante y sombreado parcial. Excelente repelente de insectos.", 6000.0),
            ("Romero Medicinal", "Salvia rosmarinus", 40, "Arbusto leñoso. Clima cálido a templado, sol directo, resiste sequía, riego mínimo y suelo suelto.", 9500.0)
        ]
        
        especies = []
        for i in range(10):
            emp_obj = empresas[i % 9]
            nombre, cientifico, ciclo, cuidados, precio_sug = especies_detalles[i]
            
            # Asociar el producto cosecha al primer insumo de su empresa para trazabilidad
            prod_cosecha = insumos[i]
            
            e = Especie(
                empresa_id=emp_obj.id,
                nombre_comun=nombre,
                nombre_cientifico=cientifico,
                dias_ciclo_estimado=ciclo,
                detalles_cuidado=cuidados,
                precio_venta_sugerido=precio_sug,
                producto_cosecha_id=prod_cosecha.id
            )
            db.session.add(e)
            especies.append(e)
        db.session.commit()
        print(" -> 10 Especies botánicas dadas de alta con su ficha técnica y precio.")

        # 11. Crear 10 Lotes de Cultivo Sembrados (Operación activa)
        print("11. Sembrando e inicializando 10 Lotes de Producción...")
        lotes_detalles = [
            ("LT-ORQ-001", 150, 150, "Estante Invernadero A", "Venta Plantula", "Disponible", -95),
            ("LT-FIC-002", 50, 48, "Área de Bonsáis B", "Venta Plantula", "En Crecimiento", -10),
            ("LT-PLM-003", 500, 490, "Lote Exterior Colina", "Venta Plantula", "En Crecimiento", -180),
            ("LT-ANT-004", 200, 195, "Invernadero Floración", "Venta Plantula", "Disponible", -80),
            ("LT-SUC-005", 1000, 990, "Mesa de Enraizamiento 3", "Venta Plantula", "Disponible", -42),
            ("LT-JAZ-006", 120, 115, "Invernadero Sombrío Norte", "Venta Plantula", "En Crecimiento", -20),
            ("LT-HOR-007", 300, 280, "Lote Exterior Sombrilla", "Venta Plantula", "En Crecimiento", -15),
            ("LT-LAV-008", 400, 395, "Invernadero Aromáticas", "Venta Plantula", "Disponible", -45),
            ("LT-MEN-009", 800, 780, "Mesa de Cultivo Rápido", "Venta Plantula", "Finalizado", -35),
            ("LT-ROM-010", 600, 595, "Lote Exterior Romero", "Venta Plantula", "En Crecimiento", -5)
        ]
        
        lotes = []
        for i in range(10):
            emp_obj = empresas[i % 9]
            sede_obj = sedes[i]
            esp_obj = especies[i]
            codigo, sembrada, actual, ubicacion, proposito, estado, dias_atras = lotes_detalles[i]
            
            l = LoteProduccion(
                empresa_id=emp_obj.id,
                codigo_lote=codigo,
                especie_id=esp_obj.id,
                sede_id=sede_obj.id,
                fecha_siembra=datetime.now(timezone.utc).date() + timedelta(days=dias_atras),
                fecha_cosecha_est=datetime.now(timezone.utc).date() + timedelta(days=dias_atras + esp_obj.dias_ciclo_estimado),
                cantidad_sembrada=sembrada,
                cantidad_actual=actual,
                ubicacion=ubicacion,
                proposito=proposito,
                estado=estado,
                costo_total=float(sembrada * 1500) # Costo base acumulado inicial de mano de obra/semilla
            )
            db.session.add(l)
            db.session.flush()
            
            # Registrar labor inicial de siembra en el lote
            lab = LaborCampo(
                lote_id=l.id,
                usuario_id=usuarios[i % 9].id,
                fecha=l.fecha_siembra,
                tipo_labor='Siembra',
                descripcion=f"Establecimiento y siembra de {sembrada} plántulas en {ubicacion}."
            )
            db.session.add(lab)
            lotes.append(l)
        db.session.commit()
        print(" -> 10 Lotes de Producción activos y sembrados.")

        # 12. Crear 10 Razas de Animales (Fichas Técnicas)
        print("12. Creando 10 Fichas de Razas de Animales...")
        razas_datos = [
            ("Vaca Holstein", "Bovino", "Doble Propósito (Leche/Cría)", "25 Litros/día", "305 días lactancia", "Requiere control de mastitis y alimentación con silaje de maíz y pastoreo.", 4500000.0),
            ("Brahman Gris", "Bovino", "Producción de Carne (Engorde)", "0.95 Kg/día", "24 meses engorde", "Excelente adaptabilidad al trópico bajo, requiere desparasitación cada 4 meses.", 5200000.0),
            ("Vaca Jersey", "Bovino", "Producción Especial de Leche (Sólidos)", "18 Litros/día", "290 días lactancia", "Leche de alta grasa para quesos. Requiere suplemento mineral especial.", 4200000.0),
            ("Rhode Island Red", "Avícola", "Producción de Huevo comercial", "280 huevos/año", "80 semanas ciclo", "Gallina ponedora pesada. Requiere ponedero techado y concentrado 16% proteína.", 25000.0),
            ("Cerdo Landrace Americano", "Porcino", "Producción de Carne magra", "1.1 Kg/día", "160 días finalización", "Excelente conformación cárnica. Requiere control estricto de temperatura en parideras.", 650000.0),
            ("Oveja Romney Marsh", "Ovino", "Doble Propósito (Lana/Carne)", "4.5 Kg lana/año", "12 meses ciclo lana", "Excelente resistencia a la humedad del suelo. Requiere corte de pezuñas y esquila anual.", 350000.0),
            ("Caballo Criollo Colombiano", "Equino", "Trabajo y Exhibición", "N/A", "Desarrollo 36 meses", "Paso fino y trote. Requiere herrado mensual y alimentación con heno y estabulación.", 8500000.0),
            ("Cabra Alpina Francesa", "Caprino", "Producción de Leche de alta digestión", "4.5 Litros/día", "270 días lactancia", "Muy dócil. Requiere tarimas de madera para dormir evitando pododermatitis.", 480000.0),
            ("Pollo Cobb 500", "Avícola", "Producción de Carne rápida", "2.6 Kg a los 42 días", "42 días engorde", "Pollo de engorde blanco. Requiere galpón con ambiente controlado y calefacción inicial.", 12000.0),
            ("Pato Pekín", "Avícola", "Producción de Carne/Huevo exótico", "3.2 Kg a las 8 semanas", "60 días ciclo", "Excelente crecimiento en estanques. Requiere control de depredadores terrestres.", 30000.0)
        ]
        
        razas = []
        for i in range(10):
            emp_obj = empresas[i % 9]
            nombre, especie, proposito, rend, ciclo, cuidados, valor = razas_datos[i]
            r = RazaAnimal(
                empresa_id=emp_obj.id,
                nombre=nombre,
                especie=especie,
                proposito_ideal=proposito,
                rendimiento_est=rend,
                ciclo_tecnico=ciclo,
                cuidados_tecnicos=cuidados,
                valor_mercado_estimado=valor
            )
            db.session.add(r)
            razas.append(r)
        db.session.commit()
        print(" -> 10 Razas de animales registradas en catálogo.")

        # 13. Crear 10 Lotes de Animales (Inventario Vivo)
        print("13. Cargando 10 Lotes de Animales en los establos...")
        animales_detalles = [
            ("Holstein-01", "La Lola", "Individual", "Potrero Central 1", "Hembra", -730, 480.0, "Holstein"),
            ("Brahman-Eng-10", "Grupo Engorde Brahman", "Grupal", "Corral de Engorde A", "Macho", -500, 380.0, "Brahman Gris"),
            ("Jersey-04", "Clarabella", "Individual", "Pesebrera Lechería", "Hembra", -365, 320.0, "Jersey"),
            ("Ponedoras-Lote12", "Galpón Ponedoras 12", "Grupal", "Galpón Ponedoras", "Hembra", -180, 2.1, "Rhode Island Red"),
            ("Cerdos-Ceba-08", "Marranera Lote 08", "Grupal", "Cocheras de Engorde", "Macho", -90, 85.0, "Cerdo Landrace Americano"),
            ("Ovejas-Romney", "Rebaño Romney Marsh", "Grupal", "Potrero Loma Alta", "Hembra", -200, 45.0, "Oveja Romney Marsh"),
            ("Caballo-Criollo", "Relámpago", "Individual", "Pesebrera Caballos 1", "Macho", -1460, 420.0, "Caballo Criollo Colombiano"),
            ("Cabras-Leche", "Grupo Cabras Alpina", "Grupal", "Corral Caprino 2", "Hembra", -150, 35.0, "Cabra Alpina Francesa"),
            ("Pollos-Cobb-04", "Galpón Ceba Cobb 04", "Grupal", "Galpón de Engorde 4", "Macho", -30, 1.8, "Pollo Cobb 500"),
            ("Patos-Lote01", "Lote Patos Pekín", "Grupal", "Estanque Patos", "Hembra", -45, 2.5, "Pato Pekín")
        ]
        
        lotes_animales = []
        for i in range(10):
            emp_obj = empresas[i % 9]
            sede_obj = sedes[i]
            raza_obj = razas[i]
            codigo, nombre, tipo, ubicacion, genero, dias_nac, peso, raza_nombre = animales_detalles[i]
            
            # Cantidad según tipo
            cant = 1 if tipo == "Individual" else random.choice([50, 100, 200, 500])
            
            anm = LoteAnimal(
                empresa_id=emp_obj.id,
                codigo=f"LOTE-{codigo.upper()}",
                nombre=nombre,
                tipo=tipo,
                especie=raza_obj.especie,
                raza=raza_nombre,
                raza_id=raza_obj.id,
                genero=genero,
                ubicacion=ubicacion,
                fecha_nacimiento=datetime.now(timezone.utc).date() + timedelta(days=dias_nac),
                fecha_ingreso=datetime.now(timezone.utc).date() + timedelta(days=dias_nac + 10),
                cantidad_inicial=cant,
                cantidad_actual=cant,
                peso_actual=peso,
                sede_id=sede_obj.id,
                proposito=raza_obj.proposito_ideal,
                estado='Activo',
                costo_acumulado=float(cant * raza_obj.valor_mercado_estimado * 0.3) # Costo acumulado del 30% del valor
            )
            db.session.add(anm)
            db.session.flush()
            
            # Registrar un evento de salud por animal/lote para trazabilidad médica
            evt = EventoSanitario(
                lote_animal_id=anm.id,
                fecha=datetime.now(timezone.utc).date() - timedelta(days=15),
                tipo='Vacunación',
                descripcion="Esquema de vacunación oficial verificado. Dosis triple aplicada por veterinario.",
                costo_servicio=50000.0
            )
            db.session.add(evt)
            lotes_animales.append(anm)
        db.session.commit()
        print(" -> 10 Lotes de animales activos cargados con su historial sanitario.")

        # 14. Generar Ventas e Historial Financiero (Últimos 6 meses para Gráficos del Dashboard!)
        print("14. Generando historial de 10 Ventas POS del Semestre...")
        for i in range(10):
            emp_obj = empresas[i % 9]
            cliente_obj = clientes[i]
            
            # Calcular fecha escalonada hacia atrás en los últimos 5 meses
            dias_atras = i * 15 + 2
            fecha_venta = datetime.now(timezone.utc) - timedelta(days=dias_atras)
            
            venta = Venta(
                empresa_id=emp_obj.id,
                numero_factura=f"FAC-POS-100{i}",
                cliente_id=cliente_obj.id,
                usuario_id=usuarios[i % 9].id,
                fecha=fecha_venta,
                estado='Finalizada',
                total=0.0
            )
            db.session.add(venta)
            db.session.flush()
            
            # Detalle de la venta (Una planta o un insumo comercial)
            # Para hacer las ganancias realistas, calculamos costo vs precio
            item_insumo = insumos[i]
            cant_venta = random.randint(1, 5)
            precio_v = item_insumo.precio_venta
            costo_c = item_insumo.costo_promedio
            subt = cant_venta * precio_v
            
            det = DetalleVenta(
                venta_id=venta.id,
                lote_id=None,
                insumo_id=item_insumo.id,
                cantidad=cant_venta,
                precio_venta_unitario=precio_v,
                costo_produccion_unitario=costo_c,
                subtotal=subt,
                ganancia=subt - (cant_venta * costo_c)
            )
            venta.total = subt
            db.session.add(det)
        db.session.commit()
        print(" -> 10 Facturas finalizadas del semestre registradas para análisis gráficos.")

        print("====== CARGA DE DATOS PREMIUM COMPLETADA CON ÉXITO ======")
        print(" -> Admin principal: admin@edenforestal.com / admin123")
        print(" -> Viveros disponibles: 10")
        print(" -> Lotes sembrados listos para ver en Tienda Web: /tienda/1")

if __name__ == '__main__':
    generate_premium_seed_data()
