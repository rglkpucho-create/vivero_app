import os
from sqlalchemy import text
from app import create_app, db
from app.models import Especie  # Importamos el modelo para insertar datos

app = create_app()

with app.app_context():
    print("--- 🛠️ GESTOR DE BASE DE DATOS Y SEMILLAS (AMPLIADO) ---")
    
    # ==========================================
    # PASO 1: REPARACIÓN DE ESTRUCTURA
    # ==========================================
    print("\n[1/2] Verificando estructura de tablas...")
    
    # Agregar columna detalles_cuidado a Especies
    try:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE especies ADD COLUMN detalles_cuidado TEXT;"))
            conn.commit()
        print("   ✅ Columna 'detalles_cuidado' agregada a tabla 'especies'.")
    except Exception as e:
        if "Duplicate column" in str(e) or "exists" in str(e):
            print("   ℹ️ La tabla 'especies' ya está actualizada.")
        else:
            print(f"   ⚠️ Nota sobre Especies: {e}")

    # Limpiar columna vieja de Lotes
    try:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE lotes_produccion DROP COLUMN detalles_cuidado;"))
            conn.commit()
        print("   ✅ Columna obsoleta eliminada de 'lotes_produccion'.")
    except Exception:
        print("   ℹ️ La tabla 'lotes_produccion' ya estaba limpia.")

    # ==========================================
    # PASO 2: POBLAR DATOS MAESTROS (SEMILLAS)
    # ==========================================
    print("\n[2/2] Sembrando especies y fichas técnicas iniciales...")

    especies_data = [
        # --- CULTIVOS COMERCIALES ---
        {
            "nombre_comun": "Plátano Dominico Hartón",
            "nombre_cientifico": "Musa AAB Simmonds",
            "dias_ciclo": 365,
            "detalles_cuidado": """CULTIVO DE PLÁTANO (Musa AAB)

1. CLIMA Y SUELO
- Altura: 0 - 1.200 msnm.
- Temp: 26°C - 30°C.
- Suelo: Franco-arenoso, rico en materia orgánica.

2. MANEJO CULTURAL
- Deshije: Seleccionar un solo sucesor ("hijo") cada 8 semanas.
- Deshoje: Semanal. Retirar hojas con >50% de daño por Sigatoka.
- Desbellote: Cortar la flor masculina tras formarse la última mano.
- Embolse: Proteger racimo a las 2 semanas de floración.

3. FERTILIZACIÓN SUGERIDA
- Siembra: 150g Roca Fosfórica.
- Crecimiento: Urea y DAP (Nitrógeno/Fósforo).
- Producción: Cloruro de Potasio (KCl) para llenado.

4. CONTROL DE PLAGAS
- Sigatoka Negra: Control cultural (deshoje) y fungicidas sistémicos.
- Picudo Negro: Trampas de feromona."""
        },
        {
            "nombre_comun": "Tomate Chonto (Bajo Invernadero)",
            "nombre_cientifico": "Solanum lycopersicum",
            "dias_ciclo": 120,
            "detalles_cuidado": """CULTIVO DE TOMATE BAJO TECHO

1. REQUERIMIENTOS
- pH Suelo: 6.0 - 6.8.
- Densidad: 2.5 a 3 plantas por m2.

2. LABORES CRÍTICAS
- Tutorado: Indispensable guiar la planta verticalmente con fibra semanalmente.
- Poda de Chupones: Eliminar brotes axilares cada 4-6 días para mantener un solo tallo principal.
- Polinización: Vibrar los alambres o usar abejorros.

3. RIEGO Y NUTRICIÓN
- Riego por goteo: Pulsos cortos y frecuentes (4-6 veces al día).
- Exigente en Calcio (evitar "culo negro") y Potasio en llenado.

4. SANIDAD
- Monitoreo diario de Mosca Blanca y Trips (vectores de virus).
- Ventilación adecuada para prevenir Botrytis."""
        },
        {
            "nombre_comun": "Aguacate Hass",
            "nombre_cientifico": "Persea americana",
            "dias_ciclo": 240,
            "detalles_cuidado": """CULTIVO DE AGUACATE HASS (Exportación)

1. GENERALIDADES
- Zona óptima: 1.800 - 2.400 msnm.
- Suelo: Profundo, bien drenado (sensible a encharcamientos).

2. MANEJO
- Poda de Formación: Primeros 2 años para abrir copa.
- Poda de Sanidad: Retirar ramas secas o enfermas post-cosecha.
- Control de Arvenses: Plateo manual, evitar herbicidas cerca al tronco.

3. NUTRICIÓN
- Zinc y Boro: Críticos en floración para cuaje.
- Nitrógeno: Aplicar fraccionado en flujos vegetativos.

4. PLAGAS CUARENTENARIAS
- Monitoreo estricto de barrenadores (Heilipus, Stenoma).
- Ácaros: Controlar si la población supera el umbral económico."""
        },
        {
            "nombre_comun": "Café Variedad Castillo",
            "nombre_cientifico": "Coffea arabica",
            "dias_ciclo": 240,
            "detalles_cuidado": """CULTIVO DE CAFÉ (Tecnificado)

1. ESTABLECIMIENTO
- Densidad: 5.000 - 7.000 plantas/ha.
- Sombra: Regular sombrío temporal (guamo, plátano) según la zona.

2. MANEJO AGRONÓMICO
- Manejo Integrado de Broca (MIB): Re-re (Recolección de granos caídos y pasillas).
- Roya: La variedad Castillo es resistente, pero requiere nutrición balanceada.

3. FERTILIZACIÓN
- Basada en análisis de suelo.
- General: 3 ciclos al año (Inicio lluvias, mitaca, fin de año).

4. BENEFICIO
- Recolección solo de grano maduro (cereza).
- Despulpado el mismo día de recolección.
- Fermentación controlada (12-18 horas según clima)."""
        },
        {
            "nombre_comun": "Maíz Híbrido (Amarillo)",
            "nombre_cientifico": "Zea mays",
            "dias_ciclo": 135,
            "detalles_cuidado": """CULTIVO DE MAÍZ

1. PREPARACIÓN
- Suelo suelto y profundo.
- Siembra directa recomendada para conservar humedad.

2. FERTILIZACIÓN CRÍTICA
- Nitrógeno: Aplicar urea en etapa V4-V6 (rodilla). Es el nutriente más limitante.
- Fósforo: Todo al momento de la siembra.

3. CONTROL DE MALEZAS
- Periodo crítico: Los primeros 40 días el cultivo debe estar limpio ("en limpio").
- Uso de herbicidas pre-emergentes recomendado.

4. PLAGAS
- Gusano Cogollero (Spodoptera): Monitorear daño en hojas nuevas. Aplicar control si >10-20% de plantas afectadas."""
        },
        
        # --- PLANTAS ORNAMENTALES Y DE HOGAR ---
        {
            "nombre_comun": "Sábila (Aloe Vera)",
            "nombre_cientifico": "Aloe vera",
            "dias_ciclo": 0, # Perenne
            "detalles_cuidado": """CUIDADOS DEL ALOE VERA

1. LUZ Y UBICACIÓN
- Pleno sol o luz indirecta muy brillante.
- Evitar cambios bruscos de temperatura.

2. RIEGO (Suculenta)
- Riego escaso. Dejar secar completamente la tierra entre riegos.
- Exceso de agua pudre las raíces rápidamente.
- En invierno, reducir al mínimo.

3. SUSTRATO
- Muy bien drenado (tipo cactus). Mezcla de tierra con arena o perlita.

4. COSECHA
- Cortar las hojas basales (las más viejas y externas) cerca del tallo cuando estén carnosas."""
        },
        {
            "nombre_comun": "Lengua de Suegra (Sansevieria)",
            "nombre_cientifico": "Sansevieria trifasciata",
            "dias_ciclo": 0,
            "detalles_cuidado": """CUIDADOS DE LA SANSEVIERIA

1. RESISTENCIA
- Planta "todoterreno". Tolera poca luz y aire seco.
- Ideal para dormitorios (purifica el aire de noche).

2. RIEGO
- Muy poco. Cada 15-20 días en verano, mensual en invierno.
- No mojar el centro de la roseta de hojas.

3. ABONO
- Abono para plantas verdes o cactus una vez al mes en primavera/verano.
- No requiere poda, solo retirar hojas secas."""
        },
        {
            "nombre_comun": "Orquídea Mariposa",
            "nombre_cientifico": "Phalaenopsis spp.",
            "dias_ciclo": 0,
            "detalles_cuidado": """CUIDADOS DE LA ORQUÍDEA PHALAENOPSIS

1. LUZ
- Luz filtrada o indirecta. Nunca sol directo (quema las hojas).
- Raíces necesitan luz (usar macetas transparentes).

2. RIEGO
- Por inmersión: Sumergir la maceta en agua 10 min cuando las raíces se vean grises/plateadas.
- Si están verdes, NO regar.
- Evitar mojar el centro de las hojas (corona).

3. SUSTRATO
- Corteza de pino gruesa. No usar tierra normal.

4. FLORACIÓN
- Tras caer las flores, cortar la vara por encima del segundo nudo para estimular nueva floración."""
        },
        {
            "nombre_comun": "Suculenta Echeveria",
            "nombre_cientifico": "Echeveria elegans",
            "dias_ciclo": 0,
            "detalles_cuidado": """CUIDADOS DE SUCULENTAS (ECHEVERIA)

1. LUZ
- Necesita mucha luz, incluso sol directo de la mañana, para mantener su forma compacta.
- Si se estira (etiolación), le falta luz.

2. RIEGO "REMOJO Y SECADO"
- Regar profundamente hasta que salga agua por el drenaje, luego no regar hasta que el sustrato esté totalmente seco.
- No usar atomizador (rociador), el agua debe ir a la tierra, no a las hojas.

3. PROBLEMAS COMUNES
- Hojas arrugadas: Falta de agua.
- Hojas amarillas/transparentes y blandas: Exceso de agua (pudrición)."""
        },
        {
            "nombre_comun": "Helecho de Boston",
            "nombre_cientifico": "Nephrolepis exaltata",
            "dias_ciclo": 0,
            "detalles_cuidado": """CUIDADOS DEL HELECHO BOSTON

1. AMBIENTE
- Humedad alta es clave. Rociar las hojas frecuentemente o mantener en baño/cocina.
- Luz indirecta suave. El sol directo quema las frondas.

2. RIEGO
- Mantener el sustrato ligeramente húmedo, pero no encharcado.
- No dejar secar totalmente la tierra.

3. FERTILIZACIÓN
- Humus líquido o fertilizante para follaje cada 2-3 semanas en etapa de crecimiento."""
        },
        {
            "nombre_comun": "Anturio Rojo",
            "nombre_cientifico": "Anthurium andraeanum",
            "dias_ciclo": 0,
            "detalles_cuidado": """CUIDADOS DEL ANTURIO

1. ILUMINACIÓN
- Luz brillante indirecta para mantener la floración. Sin luz suficiente, no produce flores rojas.

2. RIEGO Y HUMEDAD
- Riego moderado cuando se seque la capa superficial.
- Alta humedad ambiental (pulverizar hojas, no las flores).

3. SUSTRATO
- Suelto y aireado (mezcla de tierra, turba y perlita).

4. LIMPIEZA
- Limpiar el polvo de las hojas con un paño húmedo para mejorar la fotosíntesis."""
        },
        {
            "nombre_comun": "Potos (Teléfono)",
            "nombre_cientifico": "Epipremnum aureum",
            "dias_ciclo": 0,
            "detalles_cuidado": """CUIDADOS DEL POTOS

1. VERSATILIDAD
- Puede ser colgante o trepadora (con tutor).
- Se adapta a luz baja, pero crece mejor con luz indirecta media.

2. RIEGO
- Dejar secar la tierra entre riegos. Es muy resistente a la sequía, pero sensible al encharcamiento.
- Si las hojas se ponen lacias, necesita agua.

3. PODA
- Pinzar (cortar puntas) los tallos largos para que la planta se vuelva más frondosa desde la base.
- Muy fácil de reproducir por esquejes en agua."""
        },

        # --- AROMÁTICAS Y HUERTO CASERO ---
        {
            "nombre_comun": "Menta / Hierbabuena",
            "nombre_cientifico": "Mentha spicata",
            "dias_ciclo": 0,
            "detalles_cuidado": """CULTIVO DE MENTA/HIERBABUENA

1. UBICACIÓN
- Sombra parcial o sol suave.
- Cuidado: Es invasiva (sus raíces se expanden rápido). Mejor cultivar en maceta individual.

2. RIEGO
- Exigente en agua. Mantener la tierra húmeda constantemente.
- Si le falta agua, se marchita rápido (pero se recupera al regar).

3. COSECHA
- Cosechar las puntas de los tallos frecuentemente para estimular crecimiento lateral y evitar que florezca (la floración reduce el aroma)."""
        },
        {
            "nombre_comun": "Albahaca Genovesa",
            "nombre_cientifico": "Ocimum basilicum",
            "dias_ciclo": 60, # Anual
            "detalles_cuidado": """CULTIVO DE ALBAHACA

1. LUZ Y CALOR
- Pleno sol (mínimo 6 horas).
- Muy sensible al frío y heladas.

2. RIEGO
- Regular, en la base de la planta. Evitar mojar las hojas por la noche (hongos).

3. PODA DE FLORES (IMPORTANTE)
- Cortar los espigas florales apenas aparezcan. Si florece, las hojas se amargan y la planta envejece y muere.

4. USOS
- Cosechar hojas superiores para consumo fresco (pesto, ensaladas)."""
        },
        {
            "nombre_comun": "Romero",
            "nombre_cientifico": "Salvia rosmarinus",
            "dias_ciclo": 0, # Perenne leñosa
            "detalles_cuidado": """CULTIVO DE ROMERO

1. SUELO Y LUZ
- Pleno sol.
- Suelo arenoso o pobre, pero con DRENAJE PERFECTO. No tolera humedad en raíces.

2. RIEGO
- Muy escaso. Es una planta mediterránea resistente a la sequía.
- Dejar secar completamente antes de volver a regar.

3. PODA
- Podar las puntas después de la floración para mantener forma compacta y evitar que se vuelva leñoso y despoblado en la base."""
        },
        {
            "nombre_comun": "Cilantro",
            "nombre_cientifico": "Coriandrum sativum",
            "dias_ciclo": 45,
            "detalles_cuidado": """CULTIVO DE CILANTRO

1. SIEMBRA
- Directa (no tolera trasplante).
- Sembrar escalonado (cada 2 semanas) para tener producción continua.

2. CLIMA
- Sol directo.
- En climas muy calurosos, tiende a "subirse" (florecer) prematuramente. Mantener suelo fresco.

3. RIEGO
- Suelo húmedo pero no encharcado.

4. COSECHA
- Se puede cortar hojas externas o arrancar la planta entera a los 40-50 días."""
        },

        # --- HORTALIZAS Y FRUTOS PEQUEÑOS ---
        {
            "nombre_comun": "Fresa (Variedad Albión)",
            "nombre_cientifico": "Fragaria x ananassa",
            "dias_ciclo": 0,
            "detalles_cuidado": """CULTIVO DE FRESA

1. SIEMBRA
- Usar camellones altos para facilitar drenaje.
- El cuello de la planta (corona) debe quedar a nivel del suelo, no enterrado.

2. ACOLCHADO (Mulch)
- Usar plástico o paja sobre la tierra para que el fruto no toque el suelo (evita pudrición).

3. RIEGO
- Riego localizado (goteo). El agua no debe tocar hojas ni frutos.
- Frecuente pero ligero.

4. PODA
- Eliminar estolones (hijos) si se busca producción de fruta, para que la planta concentre energía."""
        },
        {
            "nombre_comun": "Lechuga Crespa",
            "nombre_cientifico": "Lactuca sativa",
            "dias_ciclo": 60,
            "detalles_cuidado": """CULTIVO DE LECHUGA

1. CLIMA
- Prefiere climas frescos. El calor excesivo la vuelve amarga y acelera la floración.

2. RIEGO
- Frecuente y ligero. Raíces muy superficiales.
- El estrés hídrico afecta inmediatamente la calidad de la hoja.

3. SIEMBRA
- Semillero y trasplante a los 20-25 días.
- Distancia: 25-30 cm entre plantas.

4. COSECHA
- Cosechar temprano en la mañana cuando las hojas están turgentes e hidratadas."""
        },
        {
            "nombre_comun": "Pimentón / Morrón",
            "nombre_cientifico": "Capsicum annuum",
            "dias_ciclo": 150,
            "detalles_cuidado": """CULTIVO DE PIMENTÓN

1. EXIGENCIAS
- Mucho sol y calor. No tolera heladas.
- Suelo profundo y rico en nutrientes.

2. TUTORADO
- Las ramas son quebradizas y los frutos pesados. Necesita soporte (estacas o cuerdas).

3. RIEGO
- Constante. La falta de agua causa caída de flores y "pudrición apical" en el fruto (mancha negra abajo).

4. COSECHA
- Se pueden cosechar verdes o esperar a que maduren (rojo/amarillo) para sabor más dulce."""
        },
        {
            "nombre_comun": "Zanahoria",
            "nombre_cientifico": "Daucus carota",
            "dias_ciclo": 90,
            "detalles_cuidado": """CULTIVO DE ZANAHORIA

1. SUELO (CRÍTICO)
- Suelo suelto, arenoso y profundo, SIN PIEDRAS.
- Si el suelo es duro o tiene obstáculos, la zanahoria saldrá deforme o bifurcada.

2. SIEMBRA
- Directa. Semilla muy pequeña, mezclar con arena para distribuir mejor.

3. RALEO (Entresaque)
- Fundamental: Cuando tengan 3-4 cm, arrancar plantas sobrantes dejando 8-10 cm entre cada una. Si están muy juntas, no engrosan.

4. APORQUE
- Cubrir con tierra los "hombros" de la raíz si asoman, para que no se pongan verdes por el sol."""
        },
        {
            "nombre_comun": "Cebolla Larga / Junca",
            "nombre_cientifico": "Allium fistulosum",
            "dias_ciclo": 90,
            "detalles_cuidado": """CULTIVO DE CEBOLLA LARGA

1. CLIMA
- Se adapta bien a climas fríos y medios.

2. SIEMBRA
- Por "esqueje" (sembrar un tallo o "hijo" de otra planta).
- Profundidad: Enterrar bien para asegurar blanqueamiento del tallo.

3. APORQUE
- Amontonar tierra alrededor de la base periódicamente. Esto estimula que el tallo crezca blanco, grueso y largo.

4. SANIDAD
- Controlar Thrips (manchas plateadas en hojas) y hongos en época de lluvia."""
        }
    ]

    count_nuevos = 0
    for data in especies_data:
        # Verificar si existe por nombre común
        existe = Especie.query.filter_by(nombre_comun=data["nombre_comun"]).first()
        
        if not existe:
            nueva_especie = Especie(
                nombre_comun=data["nombre_comun"],
                nombre_cientifico=data["nombre_cientifico"],
                dias_ciclo_estimado=data["dias_ciclo"],
                detalles_cuidado=data["detalles_cuidado"]
            )
            db.session.add(nueva_especie)
            print(f"   🌱 Insertando: {data['nombre_comun']}")
            count_nuevos += 1
        else:
            # Opcional: Actualizar la ficha si ya existe (para corregir textos)
            existe.detalles_cuidado = data["detalles_cuidado"]
            print(f"   🔄 Actualizando ficha técnica de: {data['nombre_comun']}")

    try:
        db.session.commit()
        print(f"\n✅ Proceso completado exitosamente.")
        if count_nuevos > 0:
            print(f"   -> Se crearon {count_nuevos} nuevas especies.")
        print("   -> Fichas técnicas sincronizadas.")
        
    except Exception as e:
        db.session.rollback()
        print(f"\n❌ Error al guardar datos: {e}")

    print("\n--- LISTO. Tu base de datos está actualizada y alimentada. ---")