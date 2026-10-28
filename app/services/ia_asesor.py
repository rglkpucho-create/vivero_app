"""
BioAsesor AI v3.0 Ultra — Motor Híbrido de Inteligencia Agronómica y Comercial
Desarrollado para EcoSistem SaaS.

Características:
1. Conexión Dual: Google Gemini AI (LLM) con fallback automático e instantáneo
   al Motor Cognitivo Agronómico Local (Neuro-Core v3.0).
2. Detección de Pisos Térmicos y Climas de Colombia (msnm y municipios).
3. Calculadora de Terreno & Densidad de Siembra (cercas vivas, forestales, frutales).
4. Doctor de Plantas (Diagnóstico fitosanitario, plagas, clorosis y hongos).
5. Protocolo de Ahoyado, Sustratos y Enraizamiento.
6. Vinculación en tiempo real con inventario vivo (LoteProduccion e Insumos).
7. Chips de seguimiento dinámicos (Follow-up suggestions).
"""

import os
import re
import json
import logging
from unicodedata import normalize, category
from flask import url_for

logger = logging.getLogger(__name__)

# ==============================================================================
# BASE DE CONOCIMIENTO AGRONÓMICA COLOMBIANA (PISOS TÉRMICOS Y MUNICIPIOS)
# ==============================================================================

PISOS_TERMICOS_COLOMBIA = {
    'calido': {
        'nombre': 'Clima Cálido (0 - 1.000 msnm | Temp > 24°C)',
        'ciudades': [
            'cali', 'barranquilla', 'cartagena', 'santa marta', 'valledupar', 'cucuta',
            'cúcuta', 'villavicencio', 'neiva', 'monteria', 'montería', 'palmira',
            'girardot', 'melgar', 'la dorada', 'dorada', 'espinal', 'yopal', 'sincelejo',
            'riohacha', 'buenaventura', 'tumaco', 'arauca', 'florencia', 'mariquita',
            'honda', 'turbaco', 'soledad', 'malambo', 'ciénaga', 'cienaga', 'magangue'
        ],
        'especies_clave': ['limón tahití', 'naranja valencia', 'mango', 'aguacate lorena', 'teca', 'melina', 'acacia', 'matarratón', 'ceiba', 'saman', 'guayacan rosado'],
        'consejo': 'En clima cálido la evapotranspiración es alta. Aplica acolchado (mulch) orgánico de 5cm alrededor del plato para retener humedad y riega temprano (antes de 8:00 AM) o al caer el sol.'
    },
    'templado': {
        'nombre': 'Clima Medio / Cafetero (1.000 - 2.000 msnm | 17°C - 24°C)',
        'ciudades': [
            'medellin', 'medellín', 'bucaramanga', 'pereira', 'armenia', 'ibague', 'ibagué',
            'popayan', 'popayán', 'san gil', 'rionegro', 'fusagasuga', 'fusagasugá',
            'ocana', 'ocaña', 'andes', 'jericó', 'jerico', 'guarne', 'marinilla', 'la ceja',
            'santa rosa de cabal', 'dosquebradas', 'calarca', 'calarcá', 'chinchina', 'chinchiná'
        ],
        'especies_clave': ['aguacate hass', 'café', 'mandarina', 'limón mandarino', 'plátano', 'guanábana', 'guamo', 'yarumo', 'chicalá', 'nogal cafetero'],
        'consejo': 'Zona óptima para frutales de alto valor como Aguacate Hass y Cítricos. Controla la pendiente para evitar escorrentía y realiza podas de aclareo para favorecer aireación y floración.'
    },
    'frio': {
        'nombre': 'Clima Frío Andino (2.000 - 3.000 msnm | 12°C - 17°C)',
        'ciudades': [
            'bogota', 'bogotá', 'tunja', 'pasto', 'sogamoso', 'duitama', 'zipaquira',
            'zipaquirá', 'facatativa', 'facatativá', 'chia', 'chía', 'cajica', 'cajicá',
            'sopo', 'sopó', 'tabio', 'tenjo', 'ipiales', 'manizales', 'pamplona',
            'villa de leyva', 'paipa', 'mosquera', 'funza', 'madrid', 'subachoque'
        ],
        'especies_clave': ['aliso', 'roble andino', 'cedro negro', 'pino pátula', 'ciprés', 'manzano', 'durazno', 'ciruelo', 'uchuva', 'brevo', 'eugenia', 'palma de cera'],
        'consejo': 'En clima frío el crecimiento radicular es más pausado pero constante. Siembra en camellones o lomos para que el suelo drene el exceso de humedad invernal y protégete de las heladas nocturnas.'
    }
}


def _limpiar_texto(texto):
    """Elimina tildes y caracteres especiales para matching robusto."""
    if not texto:
        return ""
    texto = texto.lower()
    return "".join(c for c in normalize("NFD", texto) if category(c) != "Mn")


# ==============================================================================
# MOTOR COGNITIVO LOCAL AGRONÓMICO (NEURO-CORE v3.0)
# ==============================================================================

def procesar_consulta_local(pregunta_raw, empresa, plantas_disp, insumos_disp):
    """
    Motor agronómico local experto en agricultura colombiana.
    Analiza semántica, clima, cálculo de terreno, fitopatología y catálogo en vivo.
    """
    pregunta = _limpiar_texto(pregunta_raw)
    palabras = set(re.findall(r'\b\w+\b', pregunta))

    sugeridos = []
    chips = []
    respuesta_md = ""

    # --------------------------------------------------------------------------
    # 1. DETECCIÓN DE CÁLCULO DE TERRENO Y DENSIDAD DE SIEMBRA
    # --------------------------------------------------------------------------
    metros_match = re.search(r'(\d+)\s*(metros|metro|mts|m)\b', pregunta)
    hectareas_match = re.search(r'(\d+(\.\d+)?)\s*(hectarea|hectareas|ha|has)\b', pregunta)
    es_calculo = any(k in pregunta for k in ['cuantas plantas', 'cuantos arboles', 'densidad', 'cuanto necesito', 'cuanto me cuesta', 'calcular'])

    if (metros_match or hectareas_match or es_calculo) and any(k in pregunta for k in ['cerca', 'sembrar', 'plantas', 'arboles', 'hectarea', 'terreno', 'lote']):
        if metros_match and any(k in pregunta for k in ['cerca', 'lindero', 'cerramiento', 'lineal']):
            metros = int(metros_match.group(1))
            cant_tupida = int(round(metros / 1.5))
            cant_estandar = int(round(metros / 2.0))
            
            # Buscar planta de cerca viva en stock
            precio_ref = 3500
            planta_cerca = None
            for p in plantas_disp:
                nom = _limpiar_texto(p.especie.nombre_comun)
                if any(t in nom for t in ['matarraton', 'acacia', 'limon', 'swinglea', 'eugenia', 'pino', 'cedro', 'arbol']):
                    planta_cerca = p
                    precio_ref = float(p.especie.precio_venta_sugerido or 3500)
                    break
            
            costo_est = cant_estandar * precio_ref
            
            respuesta_md = (
                f"📐 **Cálculo de Plántulas para {metros} Metros de Cerca Viva:**\n\n"
                f"Para un cerramiento biológico efectivo y duradero en tu predio, te presento dos opciones técnicas:\n\n"
                f"• **Barrera Rompevientos Densa (1.5 m entre plántulas):** Requieres **{cant_tupida} plántulas**.\n"
                f"• **Cerramiento Estándar de Finca (2.0 m entre plántulas):** Requieres **{cant_estandar} plántulas**.\n\n"
                f"💡 **Costo estimado de plántulas:** Aprox. **${costo_est:,.0f} COP** "
                f"(a ${precio_ref:,.0f} COP c/u con calidad certificada de vivero).\n\n"
                f"**Recomendación de siembra:** Ahoyado de 30x30 cm con 300g de materia orgánica y 20g de micorriza en la base."
            )
            if planta_cerca:
                sugeridos.append(_formatear_item(planta_cerca, 'lote'))
            
            chips = [
                f"¿Cómo preparar el hoyo de siembra?",
                f"Abonos recomendados para cerca",
                f"¿Hacen envíos de plántulas?"
            ]
            return respuesta_md, sugeridos, chips

        elif hectareas_match or 'hectarea' in pregunta:
            ha = float(hectareas_match.group(1)) if hectareas_match else 1.0
            densidad_forestal = int(round(ha * 1111)) # 3x3m
            densidad_frutales = int(round(ha * 400))  # 5x5m citricos
            densidad_aguacate = int(round(ha * 277))  # 6x6m aguacate
            
            respuesta_md = (
                f"🚜 **Planificación de Siembra para {ha} Hectárea(s) ({ha*10000:,.0f} m²):**\n\n"
                f"Según el propósito productivo o ecológico de tu terreno, la densidad técnica recomendada es:\n\n"
                f"1. **Reforestación o Maderables (Marco 3m x 3m):** Requieres **{densidad_forestal:,} plántulas**.\n"
                f"2. **Cítricos / Limón Tahití (Marco 5m x 5m):** Requieres **{densidad_frutales:,} árboles injertados**.\n"
                f"3. **Aguacate Hass (Marco 6m x 6m):** Requieres **{densidad_aguacate:,} árboles certificados**.\n"
                f"4. **Plátano o Sombrío de Café (Marco 3m x 2m):** Requieres aprox. **{int(ha*1666):,} sitios**.\n\n"
                f"🌿 En **{empresa.nombre}** preparamos lotes completos con entrega escalonada para que siembres al ritmo de las lluvias."
            )
            for p in plantas_disp[:2]:
                sugeridos.append(_formatear_item(p, 'lote'))
                
            chips = [
                "Frutales disponibles",
                "Árboles nativos disponibles",
                "¿Cómo solicitar cotización formal?"
            ]
            return respuesta_md, sugeridos, chips

    # --------------------------------------------------------------------------
    # 2. DOCTOR DE PLANTAS (DIAGNÓSTICO FITOSANITARIO)
    # --------------------------------------------------------------------------
    es_hoja_amarilla = any(k in pregunta for k in ['amarilla', 'amarillas', 'amarilleo', 'clorosis', 'palida'])
    es_mancha = any(k in pregunta for k in ['mancha', 'manchas', 'puntos negros', 'negra', 'marron', 'parda', 'hongo', 'hongos', 'roya', 'antracnosis'])
    es_plaga = any(k in pregunta for k in ['plaga', 'plagas', 'bicho', 'bichos', 'pulgon', 'pulgones', 'cochinilla', 'mosca blanca', 'gusano', 'oruga', 'comida', 'arrugada', 'pegajosa', 'hormiga'])
    es_caida = any(k in pregunta for k in ['cae', 'caen', 'caida', 'bota', 'flores', 'frutos pequenos'])

    if es_hoja_amarilla or es_mancha or es_plaga or es_caida:
        if es_hoja_amarilla:
            respuesta_md = (
                f"🩺 **Diagnóstico BioAsesor: Hojas Amarillas (Clorosis):**\n\n"
                f"El amarillamiento suele tener 3 causas principales en plántulas y árboles:\n\n"
                f"1. **Exceso de Riego o Drenaje Deficiente:** Si la hoja está amarilla, blanda y se desprende fácil, "
                f"las raíces se están asfixiando. *Solución:* Suspende el riego hasta que el sustrato seque a 3cm de profundidad.\n"
                f"2. **Deficiencia de Hierro o Magnesio:** Si la hoja se pone amarilla pero las **venas permanecen verdes**, "
                f"es clorosis férrica por pH alto. *Solución:* Aplicar quelatos de hierro o sulfato de magnesio.\n"
                f"3. **Falta de Nitrógeno:** Si el amarilleo empieza en las hojas más viejas (las de abajo). *Solución:* Abonar con compost maduro o abono rico en nitrógeno."
            )
        elif es_mancha:
            respuesta_md = (
                f"🔬 **Diagnóstico BioAsesor: Manchas Foliares / Hongos (Antracnosis o Cercospora):**\n\n"
                f"Las manchas circulares oscuras, bordes quemados o necrosis son causadas por hongos favorecidos por alta humedad:\n\n"
                f"1. **Poda Sanitaria Urgente:** Corta las hojas afectadas con tijeras desinfectadas (alcohol al 70%) y quémalas o deséchalas fuera del cultivo.\n"
                f"2. **Manejo del Riego:** Riega directamente a la base de la raíz, **nunca mojes el follaje**.\n"
                f"3. **Tratamiento Curativo:** Aspersión de Oxicloruro de Cobre o Caldo Bordelés al 1% cada 10 a 15 días hasta frenar el avance."
            )
        elif es_plaga:
            respuesta_md = (
                f"🐛 **Diagnóstico BioAsesor: Control Ecológico de Plagas:**\n\n"
                f"Para hojas arrugadas, melaza pegajosa o presencia de pulgones y cochinillas:\n\n"
                f"1. **Tratamiento Orgánico:** Prepara una mezcla de **Jabón Potásico (10 ml/L)** + **Aceite de Neem (5 ml/L)**.\n"
                f"2. **Modo de Aplicación:** Aspersión foliar profunda cubriendo especialmente el **envés de las hojas** (donde se esconden los insectos).\n"
                f"3. **Frecuencia:** Cada 5 días durante 3 semanas, siempre al atardecer para evitar quemaduras por el sol."
            )
        else:
            respuesta_md = (
                f"🌸 **Diagnóstico BioAsesor: Caída Prematura de Flores o Frutos:**\n\n"
                f"La caída floral o aborto de frutillos responde a desbalances nutricionales o estrés hídrico:\n\n"
                f"1. **Déficit de Boro y Calcio:** Son los dos minerales esenciales para el cuaje de flores. Aplica fertilizante foliar rico en Calcio-Boro.\n"
                f"2. **Estrés por Sequía:** Mantén un riego uniforme durante la floración sin encharcar."
            )
        
        # Insumos sugeridos
        for ins in insumos_disp:
            nom = _limpiar_texto(ins.nombre)
            if any(t in nom for t in ['abono', 'fertilizante', 'sustrato', 'tierra', 'nutriente', 'humus', 'compost']):
                sugeridos.append(_formatear_item(ins, 'insumo'))
                if len(sugeridos) >= 2:
                    break
        
        chips = [
            "¿Cómo aplicar abono orgánico?",
            "Guía de riego recomendada",
            "Ver insumos y sustratos disponibles"
        ]
        return respuesta_md, sugeridos, chips

    # --------------------------------------------------------------------------
    # 3. DETECCIÓN DE CLIMA, ALTITUD (MSNM) Y MUNICIPIOS COLOMBIANOS
    # --------------------------------------------------------------------------
    clima_detectado = None
    ciudad_detectada = None

    for k_clima, data_clima in PISOS_TERMICOS_COLOMBIA.items():
        for c in data_clima['ciudades']:
            if c in pregunta:
                clima_detectado = k_clima
                ciudad_detectada = c.title()
                break
        if clima_detectado:
            break

    if not clima_detectado:
        if any(k in pregunta for k in ['clima calido', 'tierra caliente', 'calor', 'bajo msnm', 'costa', 'llanuras']):
            clima_detectado = 'calido'
        elif any(k in pregunta for k in ['clima frio', 'tierra fria', 'sabana', 'paramo', 'altiplano', 'heladas']):
            clima_detectado = 'frio'
        elif any(k in pregunta for k in ['clima templado', 'clima medio', 'zona cafetera', 'eje cafetero']):
            clima_detectado = 'templado'

    if clima_detectado:
        info_c = PISOS_TERMICOS_COLOMBIA[clima_detectado]
        loc_txt = f" para la región de **{ciudad_detectada}**" if ciudad_detectada else ""
        respuesta_md = (
            f"📍 **Recomendación Agronómica{loc_txt} — {info_c['nombre']}:**\n\n"
            f"{info_c['consejo']}\n\n"
            f"**Especies con máxima adaptabilidad y vigor:**\n"
        )
        for esp in info_c['especies_clave'][:5]:
            respuesta_md += f"• **{esp.title()}**\n"
        
        # Buscar en catálogo de la empresa
        for p in plantas_disp:
            nom = _limpiar_texto(p.especie.nombre_comun)
            if any(_limpiar_texto(esp) in nom for esp in info_c['especies_clave']):
                sugeridos.append(_formatear_item(p, 'lote'))
                if len(sugeridos) >= 3:
                    break

        chips = [
            "Distancia de siembra recomendada",
            "¿Cómo preparar el suelo y ahoyado?",
            "Ver catálogo completo de plántulas"
        ]
        return respuesta_md, sugeridos, chips

    # --------------------------------------------------------------------------
    # 4. CERCA VIVA / LINDEROS / REFORESTACIÓN
    # --------------------------------------------------------------------------
    if any(k in pregunta for k in ['cerca', 'cercas', 'lindero', 'cerramiento', 'reforestar', 'reforestacion', 'viento', 'sombra', 'nativo', 'nativos', 'madera']):
        respuesta_md = (
            f"🌲 **Guía Técnica de Cercas Vivas & Reforestación — {empresa.nombre}:**\n\n"
            f"Para cerramientos biológicos y reforestación en fincas colombianas:\n\n"
            f"1. **Preparación del Terreno:** Ahoyado de **30x30 cm** de profundidad. Descompacta el fondo con barra o pala.\n"
            f"2. **Distancia de Siembra:**\n"
            f"   • *Cercas Vivas:* 1.5 a 2.0 metros entre plantas.\n"
            f"   • *Reforestación Protectora:* 3.0 x 3.0 metros (1.111 árboles/ha).\n"
            f"3. **Abonado de Fondo:** Mezcla 300g de compost orgánico maduro con la tierra fértil extraída y aplica 20g de micorriza al contacto de la raíz."
        )
        for p in plantas_disp:
            nom = _limpiar_texto(p.especie.nombre_comun)
            if any(t in nom for t in ['arbol', 'roble', 'cedro', 'guayacan', 'acacia', 'matarraton', 'pino', 'yarumo', 'sauce', 'nogal', 'eugenia']):
                sugeridos.append(_formatear_item(p, 'lote'))
                if len(sugeridos) >= 3:
                    break
        
        chips = [
            "Calcular plántulas para 100m de cerca",
            "¿Qué abono debo aplicar al sembrar?",
            "Cotizar árboles por WhatsApp"
        ]
        return respuesta_md, sugeridos, chips

    # --------------------------------------------------------------------------
    # 5. FRUTALES INJERTADOS
    # --------------------------------------------------------------------------
    if any(k in pregunta for k in ['fruta', 'frutal', 'frutales', 'injerto', 'injertado', 'citrico', 'citricos', 'limon', 'naranja', 'aguacate', 'mango', 'mandarina', 'guayaba']):
        respuesta_md = (
            f"🍊 **Frutales Injertados de Alto Rendimiento en {empresa.nombre}:**\n\n"
            f"Nuestras plántulas cuentan con **patrón seleccionado** (vigor radicular resistente a hongos de suelo) y copa certificada:\n\n"
            f"• **Ahoyado Óptimo:** 40 x 40 x 40 cm. Desinfecta el hoyo con 50g de cal agrícola si el suelo es ácido.\n"
            f"• **Precaución Clave:** **Nunca entierres el nudo de injerto**; debe quedar al menos 5 a 10 cm por encima del nivel del suelo.\n"
            f"• **Riego Inicial:** 5 a 10 litros por árbol cada 3 días durante los primeros 45 días pos-trasplante."
        )
        for p in plantas_disp:
            nom = _limpiar_texto(p.especie.nombre_comun)
            if any(t in nom for t in ['limon', 'naranja', 'mandarina', 'aguacate', 'mango', 'citrico', 'guayaba', 'guanabana', 'maracuya']):
                sugeridos.append(_formatear_item(p, 'lote'))
                if len(sugeridos) >= 3:
                    break

        chips = [
            "Distancia de siembra para frutales",
            "Control de plagas en cítricos",
            "¿Cómo hacer un pedido y envío?"
        ]
        return respuesta_md, sugeridos, chips

    # --------------------------------------------------------------------------
    # 6. RIEGO Y CUIDADOS GENERALES
    # --------------------------------------------------------------------------
    if any(k in pregunta for k in ['riego', 'regar', 'agua', 'humedad', 'frecuencia', 'cuanto regar']):
        respuesta_md = (
            f"💧 **Protocolo de Riego Profesional BioAsesor:**\n\n"
            f"1. **Plántulas Recién Trasplantadas (Días 1 a 20):** Riego suave diario o interdiario en horas frescas (antes de las 8:00 AM o después de las 5:00 PM).\n"
            f"2. **Plantas Establecidas (Árboles y Frutales):** 2 veces por semana con abundante agua en la base (riego profundo para inducir raíces profundas).\n"
            f"3. **Técnica del Dedo (Prueba de Campo):** Introduce un dedo o vara de madera 5 cm en la tierra. Si sale fresca con partículas adheridas, **no necesita agua**. Si sale seca y polvorienta, aplica riego inmediato."
        )
        chips = [
            "Abono recomendado para crecimiento",
            "Plantas para jardín o interior",
            "Ver catálogo de plántulas disponibles"
        ]
        return respuesta_md, sugeridos, chips

    # --------------------------------------------------------------------------
    # 7. ENVÍOS, PEDIDOS Y UBICACIÓN
    # --------------------------------------------------------------------------
    if any(k in pregunta for k in ['pedido', 'pedidos', 'envio', 'envios', 'domicilio', 'costo', 'precio', 'comprar', 'despacho', 'donde estan', 'ubicacion', 'direccion', 'telefono']):
        tel_wa = (empresa.whatsapp_pedidos or empresa.telefono or '')
        ciudad_vivero = empresa.ciudad or 'Colombia'
        dir_vivero = empresa.direccion or 'Vivero principal'
        
        respuesta_md = (
            f"📦 **Envíos, Despachos y Medios de Pago — {empresa.nombre}:**\n\n"
            f"• **Sede Física:** {dir_vivero}, {ciudad_vivero}.\n"
            f"• **Cobertura:** Despachos locales en vehículo acondicionado y envíos nacionales protegidos por transportadora agrícola.\n"
            f"• **Canales de Pago:** Aceptamos Nequi, Daviplata, Bancolombia, PSE y pago contraentrega en zona de cobertura.\n"
            f"• **Atención Directa:** Comunícate a nuestro WhatsApp oficial **{tel_wa}** para coordinar tu despacho inmediato."
        )
        chips = [
            "Ver plántulas disponibles",
            "¿Tienen árboles para cerca viva?",
            "Cotizar con un asesor humano"
        ]
        return respuesta_md, sugeridos, chips

    # --------------------------------------------------------------------------
    # 8. BÚSQUEDA DIRECTA POR PALABRA CLAVE EN EL CATÁLOGO
    # --------------------------------------------------------------------------
    terminos_busqueda = [w for w in palabras if len(w) >= 3 and w not in ['para', 'como', 'tengo', 'unas', 'unos', 'donde', 'puedo', 'cual', 'cuales']]
    
    for p in plantas_disp:
        nom_esp = _limpiar_texto(p.especie.nombre_comun)
        nom_cie = _limpiar_texto(p.especie.nombre_cientifico or '')
        if any(t in nom_esp or t in nom_cie for t in terminos_busqueda):
            sugeridos.append(_formatear_item(p, 'lote'))
            if len(sugeridos) >= 4:
                break
                
    if not sugeridos:
        for ins in insumos_disp:
            nom_ins = _limpiar_texto(ins.nombre)
            if any(t in nom_ins for t in terminos_busqueda):
                sugeridos.append(_formatear_item(ins, 'insumo'))
                if len(sugeridos) >= 3:
                    break

    if sugeridos:
        respuesta_md = (
            f"✨ **He encontrado estas plántulas y productos en nuestro inventario en vivo** que coinciden exactamente con tu consulta:\n\n"
            f"Puedes ver la disponibilidad y agregarlos al pedido al instante:"
        )
        chips = [
            "¿Cómo se deben sembrar?",
            "¿Tienen servicio de envío?",
            "Ver más productos del catálogo"
        ]
        return respuesta_md, sugeridos, chips

    # --------------------------------------------------------------------------
    # 9. RESPUESTA GENERAL CONSULTIVA
    # --------------------------------------------------------------------------
    total_lotes = len(plantas_disp)
    total_insumos = len(insumos_disp)
    respuesta_md = (
        f"🌱 ¡Con gusto te asesoro! En **{empresa.nombre}** contamos actualmente con **{total_lotes} lotes de plántulas vivas** "
        f"y **{total_insumos} insumos y sustratos** listos para despacho en {empresa.ciudad or 'Colombia'}.\n\n"
        f"Dime qué proyecto deseas emprender hoy: ¿buscas árboles para cerramientos o cercas vivas, árboles frutales injertados, especies nativas para reforestación o plantas ornamentales?"
    )
    for p in plantas_disp[:3]:
        sugeridos.append(_formatear_item(p, 'lote'))
        
    chips = [
        "🌲 Cercas vivas y linderos",
        "🍊 Frutales injertados",
        "📐 Calcular plantas para mi terreno",
        "💧 Guía de riego y cuidados"
    ]
    return respuesta_md, sugeridos, chips


def _formatear_item(prod, tipo):
    """Convierte un lote o insumo en diccionario listo para renderizar."""
    if tipo == 'lote':
        return {
            'id': prod.id,
            'tipo': 'lote',
            'nombre': prod.especie.nombre_comun,
            'cientifico': prod.especie.nombre_cientifico or '',
            'precio': prod.especie.precio_venta_sugerido or 0,
            'stock': prod.cantidad_actual,
            'img': url_for('static', filename=prod.especie.imagen_url) if prod.especie.imagen_url else ''
        }
    else:
        return {
            'id': prod.id,
            'tipo': 'insumo',
            'nombre': prod.nombre,
            'cientifico': 'Insumo agrícola',
            'precio': prod.precio_venta or 0,
            'stock': prod.cantidad_actual,
            'img': url_for('static', filename=prod.imagen_url) if prod.imagen_url else ''
        }


# ==============================================================================
# PROVEEDOR GOOGLE GEMINI (LLM HYBRID ENGINE)
# ==============================================================================

def consultar_gemini_agronomo(pregunta, empresa, plantas_disp, insumos_disp):
    """
    Invoca Google Gemini AI con grounding del inventario vivo de la empresa.
    Retorna (texto_respuesta, items_sugeridos, chips_sugeridos) o None si falla.
    """
    api_key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')
    if not api_key:
        return None

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        
        # Resumen del catálogo real
        catalogo_contexto = []
        for p in plantas_disp[:15]:
            catalogo_contexto.append({
                'id': p.id,
                'nombre': p.especie.nombre_comun,
                'cientifico': p.especie.nombre_cientifico,
                'precio_cop': p.especie.precio_venta_sugerido or 0,
                'stock_disponible': p.cantidad_actual
            })
            
        system_instruction = (
            f"Eres BioAsesor AI v3.0, el ingeniero agrónomo y asesor técnico del vivero '{empresa.nombre}' "
            f"ubicado en {empresa.ciudad or 'Colombia'}. "
            f"Tu misión es asesorar a clientes, agricultores y viveristas con calidez, rigor botánico colombiano "
            f"y enfoque comercial ético. Responde de manera concisa (máximo 3 párrafos), clara, en formato Markdown con viñetas. "
            f"Inventario en vivo disponible en el vivero: {json.dumps(catalogo_contexto, ensure_ascii=False)}. "
            f"Si el usuario pregunta por algo que tenemos en catálogo, menciónalo con su precio en COP."
        )

        model = genai.GenerativeModel(
            model_name='gemini-1.5-flash',
            system_instruction=system_instruction
        )
        
        response = model.generate_content(pregunta)
        if response and response.text:
            texto = response.text
            
            # Extraer productos coincidentes
            sugeridos = []
            for p in plantas_disp:
                if p.especie.nombre_comun.lower() in texto.lower():
                    sugeridos.append(_formatear_item(p, 'lote'))
                    if len(sugeridos) >= 3:
                        break
                        
            chips = [
                "¿Cómo sembrar esta especie?",
                "¿Qué abono me recomiendas?",
                "¿Hacen despachos a mi ciudad?"
            ]
            return texto, sugeridos, chips

    except Exception as e:
        logger.warning(f"Error invocando Gemini AI: {e}. Usando fallback local...")
        return None

    return None


# ==============================================================================
# INTERFAZ PÚBLICA PRINCIPAL
# ==============================================================================

def responder_consulta_agronomica(pregunta, empresa, plantas_disp, insumos_disp):
    """
    Punto de entrada unificado para BioAsesor AI.
    Intenta Gemini primero si está configurado, o ejecuta el motor cognitivo local.
    """
    # 1. Intentar LLM Gemini si está disponible
    resultado_gemini = consultar_gemini_agronomo(pregunta, empresa, plantas_disp, insumos_disp)
    if resultado_gemini:
        return resultado_gemini

    # 2. Motor cognitivo local altamente enriquecido
    return procesar_consulta_local(pregunta, empresa, plantas_disp, insumos_disp)
