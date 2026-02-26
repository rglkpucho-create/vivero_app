from app import create_app
from app.extensions import db
from app.models import Especie
from sqlalchemy import or_  # Importamos or_ para validar duplicados

# Inicializamos la aplicación para tener contexto de base de datos
app = create_app()

# --- BASE DE DATOS DE CONOCIMIENTO AGRONÓMICO ---
ESPECIES_DATA = [
    {
        "nombre_comun": "Café",
        "nombre_cientifico": "Coffea arabica",
        "dias_ciclo": 240, # Fase de vivero aprox.
        "ficha": """🌱 **Fase de Vivero (Almácigo):**
- **Sustrato:** Mezcla 3:1 de tierra negra y materia orgánica (pulpa descompuesta). pH ideal 5.0 - 5.5.
- **Riego:** Mantener humedad constante sin encharcar. Riego diario en zonas secas.
- **Sombra:** Requiere 50-60% de sombra (sarán o polisombra) en los primeros 3 meses.
- **Fertilización:** Aplicar 2g de DAP por bolsa al mes 2 y mes 4.
- **Plagas:** Vigilar Minador de la hoja y Cercospora (Mancha de hierro)."""
    },
    {
        "nombre_comun": "Plátano",
        "nombre_cientifico": "Musa paradisiaca",
        "dias_ciclo": 365,
        "ficha": """🍌 **Manejo del Cultivo:**
- **Clima:** Tropical húmedo, temperatura promedio 26°C. Altitud 0-1200 msnm.
- **Suelo:** Franco-arenoso a franco-arcilloso, rico en materia orgánica. Buen drenaje es vital.
- **Riego:** Alta demanda hídrica. Déficit causa racimos pequeños.
- **Labores:** Deshije constante (dejar solo madre, hijo, nieto), deshoje sanitario semanal.
- **Fertilización:** Alta demanda de Potasio (K) para llenado de fruto."""
    },
    {
        "nombre_comun": "Aguacate Hass",
        "nombre_cientifico": "Persea americana",
        "dias_ciclo": 240, # Injertación y vivero
        "ficha": """🥑 **Vivero e Injertación:**
- **Patrón:** Usar patrones criollos resistentes a Phytophthora.
- **Injerto:** Realizar cuando el patrón tenga diámetro de lápiz (aprox. 4-6 meses).
- **Riego:** Sensible al exceso de humedad. Evitar a toda costa el encharcamiento (Asfixia radicular).
- **Sanidad:** Tratamientos preventivos con fungicidas para raíz antes del trasplante.
- **Luz:** Adaptación gradual a luz solar directa antes de llevar a campo."""
    },
    {
        "nombre_comun": "Cacao",
        "nombre_cientifico": "Theobroma cacao",
        "dias_ciclo": 180,
        "ficha": """🍫 **Etapa de Vivero:**
- **Sombra:** Requiere sombra densa (70%) en etapa inicial, reducir al 40% antes del trasplante.
- **Riego:** Diario. El estrés hídrico causa caída prematura de hojas.
- **Fertilización:** Foliar rica en Zinc y Boro a partir del tercer mes.
- **Plagas:** Monilia es la principal amenaza en fruto, pero en vivero cuidar de áfidos y trips en brotes tiernos."""
    },
    {
        "nombre_comun": "Maíz",
        "nombre_cientifico": "Zea mays",
        "dias_ciclo": 120,
        "ficha": """🌽 **Ciclo Corto:**
- **Siembra:** Directa. Distancia recomendada 20-25 cm entre plantas.
- **Requerimientos:** Altamente exigente en Nitrógeno (Urea) a los 15 y 45 días.
- **Riego:** Crítico durante la floración y llenado de grano (R1-R3).
- **Control:** Manejo agresivo de malezas en los primeros 40 días (período crítico de competencia).
- **Plagas:** Gusano cogollero (Spodoptera frugiperda) requiere monitoreo semanal."""
    },
    {
        "nombre_comun": "Tomate Chonto",
        "nombre_cientifico": "Solanum lycopersicum",
        "dias_ciclo": 90,
        "ficha": """🍅 **Manejo Intensivo:**
- **Tutorado:** Indispensable para evitar contacto con suelo y enfermedades.
- **Poda:** Eliminar chupones axilares semanalmente para dejar 1 o 2 tallos principales.
- **Riego:** Goteo recomendado. Evitar mojar el follaje para prevenir Gota (Phytophthora).
- **Nutrición:** Calcio es vital para evitar "Culo negro" (Podredumbre apical).
- **Cosecha:** Inicia a los 70-80 días según clima."""
    },
    {
        "nombre_comun": "Pimentón",
        "nombre_cientifico": "Capsicum annuum",
        "dias_ciclo": 100,
        "ficha": """🌶️ **Guía Técnica:**
- **Temperatura:** Óptima 20-25°C. Heladas causan muerte inmediata.
- **Suelo:** Suelos profundos, pH 6.0-7.0. Sensible a salinidad.
- **Riego:** Frecuente y ligero.
- **Plagas:** Ácaros y Mosca Blanca son los vectores virales más peligrosos.
- **Tutorado:** Requiere soporte (hilos o estacas) por el peso de los frutos."""
    },
    {
        "nombre_comun": "Limón Tahití",
        "nombre_cientifico": "Citrus latifolia",
        "dias_ciclo": 300, # Vivero
        "ficha": """🍋 **Etapa Vivero:**
- **Bolsa:** Usar bolsas de 40cm de profundidad para desarrollo radicular.
- **Injerto:** Sobre patrón Volkarameriana o Sunki (según zona).
- **Poda:** De formación para eliminar brotes bajos (chupadores) del patrón.
- **Sanidad:** Minador de los cítricos daña las hojas nuevas, aplicar control en brotación.
- **Riego:** Moderado."""
    },
    {
        "nombre_comun": "Fríjol Cargamanto",
        "nombre_cientifico": "Phaseolus vulgaris",
        "dias_ciclo": 110,
        "ficha": """🌿 **Leguminosa Voluble:**
- **Soporte:** Requiere tutorado o siembra asociada (ej. con Maíz).
- **Suelo:** No tolera suelos ácidos (< 5.5 pH). Encalar si es necesario.
- **Fijación N:** Aporta nitrógeno al suelo, ideal para rotación.
- **Enfermedades:** Antracnosis es común en climas fríos y húmedos.
- **Cosecha:** Vainas secas para grano o verdes para consumo fresco."""
    },
    {
        "nombre_comun": "Yuca",
        "nombre_cientifico": "Manihot esculenta",
        "dias_ciclo": 270,
        "ficha": """🥔 **Cultivo Rústico:**
- **Semilla:** Estacas (cangres) de 20cm de plantas sanas y vigorosas.
- **Suelo:** Tolera suelos pobres y ácidos, pero requiere suelo suelto para engrosar raíces.
- **Riego:** Muy resistente a sequía una vez establecida.
- **Malezas:** Control estricto los primeros 3 meses.
- **Cosecha:** Arrancar cuando las hojas inferiores amarillean (aprox. 9-10 meses)."""
    }
]

def actualizar_base_de_datos():
    with app.app_context():
        print("\n🌱 INICIANDO ACTUALIZACIÓN DE ESPECIES Y FICHAS TÉCNICAS 🌱")
        print("="*60)
        
        creados = 0
        actualizados = 0
        
        for data in ESPECIES_DATA:
            # CORRECCIÓN: Buscamos por nombre común O científico para evitar el error de duplicidad
            especie = Especie.query.filter(
                or_(
                    Especie.nombre_comun.ilike(data["nombre_comun"]),
                    Especie.nombre_cientifico.ilike(data["nombre_cientifico"])
                )
            ).first()
            
            if especie:
                # Si existe (ya sea como "Cafe" o "Coffea arabica"), actualizamos todo para estandarizar
                especie.nombre_comun = data["nombre_comun"] 
                especie.nombre_cientifico = data["nombre_cientifico"]
                especie.dias_ciclo_estimado = data["dias_ciclo"]
                especie.detalles_cuidado = data["ficha"]
                actualizados += 1
                print(f"🔄 Actualizado: {data['nombre_comun']}")
            else:
                # Si no existe, la creamos
                nueva_especie = Especie(
                    nombre_comun=data["nombre_comun"],
                    nombre_cientifico=data["nombre_cientifico"],
                    dias_ciclo_estimado=data["dias_ciclo"],
                    detalles_cuidado=data["ficha"]
                )
                db.session.add(nueva_especie)
                creados += 1
                print(f"✅ Creado: {data['nombre_comun']}")
        
        try:
            db.session.commit()
            print("="*60)
            print(f"🚀 PROCESO COMPLETADO EXITOSAMENTE")
            print(f"📊 Resumen: {creados} especies nuevas, {actualizados} fichas actualizadas.")
        except Exception as e:
            db.session.rollback()
            print(f"❌ ERROR CRÍTICO AL GUARDAR EN BASE DE DATOS: {str(e)}")

if __name__ == "__main__":
    actualizar_base_de_datos()