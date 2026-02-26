from app import create_app, db
from app.models import Especie

# Lista de Especies Curada (Datos reales aproximados para Colombia/Trópico)
especies_data = [
    # --- HORTALIZAS Y VERDURAS ---
    {
        "nombre_comun": "Tomate Chonto",
        "nombre_cientifico": "Solanum lycopersicum",
        "dias_ciclo_estimado": 90,
        "detalles_cuidado": "Clima templado a cálido (18-25°C). Requiere tutorado (soporte). Riego frecuente pero sin encharcar. Susceptible a hongos si hay mucha humedad en hojas."
    },
    {
        "nombre_comun": "Lechuga Batavia",
        "nombre_cientifico": "Lactuca sativa",
        "dias_ciclo_estimado": 60,
        "detalles_cuidado": "Clima frío a templado. Riego constante para evitar sabor amargo. Cosecha rápida. Ideal para sistemas hidropónicos o suelo suelto."
    },
    {
        "nombre_comun": "Zanahoria",
        "nombre_cientifico": "Daucus carota",
        "dias_ciclo_estimado": 100,
        "detalles_cuidado": "Suelo profundo y suelto (arenoso) es vital para que no salga deforme. Riego regular. Clima fresco."
    },
    {
        "nombre_comun": "Cebolla de Rama (Junca)",
        "nombre_cientifico": "Allium fistulosum",
        "dias_ciclo_estimado": 120,
        "detalles_cuidado": "Muy resistente. Prefiere clima frío o templado. Requiere aporque (cubrir base con tierra) para blanquear el tallo. Riego moderado."
    },
    {
        "nombre_comun": "Pimentón",
        "nombre_cientifico": "Capsicum annuum",
        "dias_ciclo_estimado": 110,
        "detalles_cuidado": "Clima cálido. Necesita mucho sol. Riego moderado. Tutorado recomendado para soportar peso de frutos."
    },
    {
        "nombre_comun": "Cilantro",
        "nombre_cientifico": "Coriandrum sativum",
        "dias_ciclo_estimado": 45,
        "detalles_cuidado": "Ciclo muy corto. Clima templado. Riego ligero diario. Se puede resernbrar cada 2 semanas para tener siempre fresco."
    },
    {
        "nombre_comun": "Maíz Dulce",
        "nombre_cientifico": "Zea mays",
        "dias_ciclo_estimado": 120,
        "detalles_cuidado": "Requiere mucho sol y agua, especialmente en floración. Suelo rico en nitrógeno. Sembrar en bloques para mejorar polinización."
    },
    
    # --- FRUTALES ---
    {
        "nombre_comun": "Lulo",
        "nombre_cientifico": "Solanum quitoense",
        "dias_ciclo_estimado": 240,
        "detalles_cuidado": "Clima fresco y húmedo (bosque niebla). Sombra parcial. Suelo rico en materia orgánica. Cuidado con nematodos en la raíz."
    },
    {
        "nombre_comun": "Mora de Castilla",
        "nombre_cientifico": "Rubus glaucus",
        "dias_ciclo_estimado": 270,
        "detalles_cuidado": "Clima frío. Requiere tutorado (espardera). Poda constante de ramas viejas para estimular producción. Riego frecuente."
    },
    {
        "nombre_comun": "Maracuyá",
        "nombre_cientifico": "Passiflora edulis",
        "dias_ciclo_estimado": 180,
        "detalles_cuidado": "Clima cálido. Trepadora vigorosa, requiere espaldera o glorieta. Mucho sol. Polinización manual ayuda a cuajar frutos."
    },
    {
        "nombre_comun": "Aguacate Hass",
        "nombre_cientifico": "Persea americana",
        "dias_ciclo_estimado": 730, # 2 años para iniciar producción estable
        "detalles_cuidado": "Suelo MUY bien drenado (no tolera encharcamiento). Clima templado a frío moderado. Poda de formación necesaria."
    },
    {
        "nombre_comun": "Limón Tahití",
        "nombre_cientifico": "Citrus latifolia",
        "dias_ciclo_estimado": 540, # 1.5 años
        "detalles_cuidado": "Clima cálido a templado. Riego abundante. Fertilización rica en microelementos (Zinc, Magnesio). Poda de limpieza."
    },

    # --- AROMÁTICAS Y MEDICINALES ---
    {
        "nombre_comun": "Albahaca",
        "nombre_cientifico": "Ocimum basilicum",
        "dias_ciclo_estimado": 60,
        "detalles_cuidado": "Clima templado/cálido. Mucha luz pero no sol directo intenso todo el día. Riego en la base, no mojar hojas. Podar flores para alargar vida."
    },
    {
        "nombre_comun": "Menta / Hierbabuena",
        "nombre_cientifico": "Mentha spicata",
        "dias_ciclo_estimado": 90,
        "detalles_cuidado": "Muy invasiva (mejor en maceta o controlada). Clima templado. Riego frecuente, le gusta la humedad. Sombra parcial tolerada."
    },
    {
        "nombre_comun": "Romero",
        "nombre_cientifico": "Salvia rosmarinus",
        "dias_ciclo_estimado": 150,
        "detalles_cuidado": "Planta leñosa resistente. Poco riego (tolera sequía). Mucho sol. Suelo arenoso/drenado. Cosecha continua podando ramas."
    }
]

# --- SCRIPT DE CARGA ---
app = create_app()

with app.app_context():
    print("🌱 Iniciando siembra de datos...")
    
    conteo = 0
    for data in especies_data:
        # Verificar si ya existe para no duplicar
        existe = Especie.query.filter_by(nombre_comun=data['nombre_comun']).first()
        
        if not existe:
            nueva = Especie(
                nombre_comun=data['nombre_comun'],
                nombre_cientifico=data['nombre_cientifico'],
                dias_ciclo_estimado=data['dias_ciclo_estimado'],
                detalles_cuidado=data['detalles_cuidado'],
                imagen_url=None # Se pueden subir fotos luego
            )
            db.session.add(nueva)
            conteo += 1
            print(f"   + Agregada: {data['nombre_comun']}")
        else:
            print(f"   . Saltada (ya existe): {data['nombre_comun']}")

    db.session.commit()
    print(f"✨ Proceso finalizado. {conteo} nuevas especies registradas en EcoSistem.")