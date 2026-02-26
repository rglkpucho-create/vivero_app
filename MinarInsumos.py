from app import create_app, db
from app.models import Insumo, UnidadMedida

# --- LISTA CURADA DE INSUMOS PARA VIVERO ---
insumos_data = [
    # 1. SUSTRATOS Y TIERRAS
    {
        "nombre": "Tierra Negra Abonada",
        "codigo": "SUS-001",
        "tipo": "Sustrato",
        "unidad": "Bto", # Bulto
        "stock_minimo": 10
    },
    {
        "nombre": "Cascarilla de Arroz (Cruda)",
        "codigo": "SUS-002",
        "tipo": "Sustrato",
        "unidad": "Bto",
        "stock_minimo": 5
    },
    {
        "nombre": "Cascarilla de Arroz (Quemada)",
        "codigo": "SUS-003",
        "tipo": "Sustrato",
        "unidad": "Bto",
        "stock_minimo": 5
    },
    {
        "nombre": "Turba Rubia (Peat Moss)",
        "codigo": "SUS-004",
        "tipo": "Sustrato",
        "unidad": "Kg",
        "stock_minimo": 20
    },
    {
        "nombre": "Humus de Lombriz Sólido",
        "codigo": "SUS-005",
        "tipo": "Sustrato",
        "unidad": "Kg",
        "stock_minimo": 15
    },
    {
        "nombre": "Perlita Agrícola",
        "codigo": "SUS-006",
        "tipo": "Sustrato",
        "unidad": "Kg",
        "stock_minimo": 5
    },
    {
        "nombre": "Fibra de Coco",
        "codigo": "SUS-007",
        "tipo": "Sustrato",
        "unidad": "Bto",
        "stock_minimo": 5
    },

    # 2. FERTILIZANTES
    {
        "nombre": "Triple 15 (15-15-15)",
        "codigo": "FER-001",
        "tipo": "Fertilizante",
        "unidad": "Kg",
        "stock_minimo": 50
    },
    {
        "nombre": "Urea Agrícola (46-0-0)",
        "codigo": "FER-002",
        "tipo": "Fertilizante",
        "unidad": "Kg",
        "stock_minimo": 25
    },
    {
        "nombre": "DAP (Fosfato Diamónico)",
        "codigo": "FER-003",
        "tipo": "Fertilizante",
        "unidad": "Kg",
        "stock_minimo": 25
    },
    {
        "nombre": "Osmocote 14-14-14 (Liberación Lenta)",
        "codigo": "FER-004",
        "tipo": "Fertilizante",
        "unidad": "Kg",
        "stock_minimo": 5
    },
    {
        "nombre": "Fertilizante Foliar Producción",
        "codigo": "FER-005",
        "tipo": "Fertilizante",
        "unidad": "L", # Litro
        "stock_minimo": 2
    },
    {
        "nombre": "Cal Agrícola (Dolomita)",
        "codigo": "FER-006",
        "tipo": "Enmienda",
        "unidad": "Kg",
        "stock_minimo": 20
    },

    # 3. CONTROL FITOSANITARIO (VENENOS/REMEDIOS)
    {
        "nombre": "Aceite de Neem (Orgánico)",
        "codigo": "FIT-001",
        "tipo": "Insecticida",
        "unidad": "L",
        "stock_minimo": 1
    },
    {
        "nombre": "Jabón Potásico",
        "codigo": "FIT-002",
        "tipo": "Insecticida",
        "unidad": "L",
        "stock_minimo": 2
    },
    {
        "nombre": "Fungicida a base de Cobre",
        "codigo": "FIT-003",
        "tipo": "Fungicida",
        "unidad": "L",
        "stock_minimo": 1
    },
    {
        "nombre": "Glifosato (Herbicida)",
        "codigo": "FIT-004",
        "tipo": "Herbicida",
        "unidad": "L",
        "stock_minimo": 5
    },

    # 4. MACETAS, BOLSAS Y CONTENEDORES
    {
        "nombre": "Bolsa Vivero 1Kg (12x15)",
        "codigo": "MAC-001",
        "tipo": "Insumo",
        "unidad": "Und",
        "stock_minimo": 1000
    },
    {
        "nombre": "Bolsa Vivero 2Kg (17x23)",
        "codigo": "MAC-002",
        "tipo": "Insumo",
        "unidad": "Und",
        "stock_minimo": 500
    },
    {
        "nombre": "Bolsa Vivero 5Kg (25x30)",
        "codigo": "MAC-003",
        "tipo": "Insumo",
        "unidad": "Und",
        "stock_minimo": 200
    },
    {
        "nombre": "Bandeja Germinación 128 cavidades",
        "codigo": "MAC-004",
        "tipo": "Herramienta",
        "unidad": "Und",
        "stock_minimo": 10
    },
    {
        "nombre": "Bandeja Germinación 200 cavidades",
        "codigo": "MAC-005",
        "tipo": "Herramienta",
        "unidad": "Und",
        "stock_minimo": 10
    },
    {
        "nombre": "Matera P7 (Semillero cuadrada)",
        "codigo": "MAC-006",
        "tipo": "Insumo",
        "unidad": "Und",
        "stock_minimo": 500
    },

    # 5. MERCANCÍA PARA LA VENTA (DECORACIÓN)
    {
        "nombre": "Matera Barro N12 Clásica",
        "codigo": "VTA-001",
        "tipo": "Matera",
        "unidad": "Und",
        "stock_minimo": 20
    },
    {
        "nombre": "Matera Barro N14 Clásica",
        "codigo": "VTA-002",
        "tipo": "Matera",
        "unidad": "Und",
        "stock_minimo": 20
    },
    {
        "nombre": "Matera Plástica Premium Blanca N14",
        "codigo": "VTA-003",
        "tipo": "Matera",
        "unidad": "Und",
        "stock_minimo": 15
    },
    {
        "nombre": "Sustrato Orquídeas Premium (Bolsa 1Kg)",
        "codigo": "VTA-004",
        "tipo": "Producto Comercial",
        "unidad": "Und",
        "stock_minimo": 10
    },

    # 6. HERRAMIENTAS
    {
        "nombre": "Tijera de Poda Mano",
        "codigo": "HER-001",
        "tipo": "Herramienta",
        "unidad": "Und",
        "stock_minimo": 2
    },
    {
        "nombre": "Guantes Jardinería (Par)",
        "codigo": "HER-002",
        "tipo": "Herramienta",
        "unidad": "Und",
        "stock_minimo": 5
    },
    {
        "nombre": "Palita de Mano Metálica",
        "codigo": "HER-003",
        "tipo": "Herramienta",
        "unidad": "Und",
        "stock_minimo": 3
    }
]

# --- SCRIPT DE CARGA ---
app = create_app()

with app.app_context():
    print("🚜 Iniciando carga de Insumos y Unidades...")

    # 1. Asegurar Unidades de Medida
    unidades_base = [
        ('Kg', 'Kilogramo'),
        ('L', 'Litro'),
        ('Und', 'Unidad'),
        ('Bto', 'Bulto'),
        ('m3', 'Metro Cúbico'),
        ('g', 'Gramo'),
        ('ml', 'Mililitro'),
        ('Rollo', 'Rollo')
    ]

    unidades_map = {} # Diccionario para acceso rápido id por abreviatura

    print("   > Verificando Unidades de Medida...")
    for abreviatura, nombre in unidades_base:
        unidad = UnidadMedida.query.filter_by(abreviatura=abreviatura).first()
        if not unidad:
            unidad = UnidadMedida(nombre=nombre, abreviatura=abreviatura)
            db.session.add(unidad)
            print(f"     + Creada unidad: {nombre}")
        unidades_map[abreviatura] = unidad
    
    db.session.commit() # Guardar unidades para tener IDs
    
    # Recargar mapa con objetos persistidos
    for u in UnidadMedida.query.all():
        unidades_map[u.abreviatura] = u

    # 2. Cargar Insumos
    print("\n   > Sembrando Insumos en la Base de Datos...")
    conteo = 0
    for data in insumos_data:
        # Verificar si ya existe por nombre
        existe = Insumo.query.filter_by(nombre=data['nombre']).first()
        
        if not existe:
            # Buscar el ID de la unidad
            unidad_obj = unidades_map.get(data['unidad'])
            if not unidad_obj:
                print(f"     ! ALERTA: Unidad '{data['unidad']}' no encontrada para {data['nombre']}. Usando 'Und'.")
                unidad_obj = unidades_map.get('Und')

            nuevo = Insumo(
                nombre=data['nombre'],
                codigo=data['codigo'],
                tipo=data['tipo'],
                unidad_medida_id=unidad_obj.id,
                stock_minimo=data['stock_minimo'],
                cantidad_actual=0.0, # Inician en 0
                costo_promedio=0.0
            )
            db.session.add(nuevo)
            conteo += 1
            print(f"     + Agregado: {data['nombre']}")
        else:
            print(f"     . Saltado (ya existe): {data['nombre']}")

    db.session.commit()
    print(f"\n✨ Proceso finalizado. {conteo} nuevos insumos registrados en el sistema.")