"""Fuente de conocimiento curada para RAG — guías de destino.

Reemplaza el diccionario estático que existía en
agents/itinerary/agent.py::_tool_get_destination_info (comentado ahí mismo como
"en producción se conectaría a una API de viajes"). Aquí formalizamos esa fuente
como texto plano; scripts/build_rag_index.py la embebe en la tabla
`destination_knowledge` (pgvector) para que ItineraryAgent y SalesAgent la
recuperen por similaridad semántica en vez de un match exacto de string.

Cada entrada es un chunk pequeño y autocontenido (mejor para recuperación
semántica que un párrafo único gigante por destino).
"""
from __future__ import annotations

DESTINATION_KNOWLEDGE: list[dict[str, str]] = [
    # ─── Cusco ──────────────────────────────────────────────────────────────
    {
        "destination": "Cusco, Perú",
        "title": "Clima y equipaje — Cusco",
        "content": (
            "Cusco tiene clima templado de montaña, entre 7°C y 18°C. Temporada seca de mayo a "
            "octubre (mejor época para viajar), temporada de lluvias de noviembre a abril. "
            "Se recomienda llevar ropa en capas, impermeable ligero y protector solar de alta protección."
        ),
    },
    {
        "destination": "Cusco, Perú",
        "title": "Altitud y salud — Cusco",
        "content": (
            "Cusco está a 3,399 msnm, con riesgo real de soroche (mal de altura) los primeros 1-2 días. "
            "Se recomienda mate de coca, hidratación abundante, evitar alcohol el primer día y "
            "aclimatarse antes de subir a Machu Picchu (2,430 msnm, algo más baja que la ciudad)."
        ),
    },
    {
        "destination": "Cusco, Perú",
        "title": "Cultura y práctica — Cusco",
        "content": (
            "Ciudad Inca y Colonial, Patrimonio de la Humanidad. Se habla quechua y español. "
            "El Mercado San Pedro es una parada obligatoria para gastronomía local. Moneda: Sol "
            "peruano (PEN); propinas de 10% son costumbre en restaurantes turísticos."
        ),
    },
    {
        "destination": "Cusco, Perú",
        "title": "Logística de viaje — Machu Picchu",
        "content": (
            "Los boletos de tren a Machu Picchu (Ollantaytambo o Poroy) y la entrada al santuario "
            "deben reservarse con semanas de anticipación en temporada alta, ya que hay cupo diario "
            "limitado. Aclimatarse en Cusco o el Valle Sagrado antes de la excursión es clave."
        ),
    },
    # ─── Lima ───────────────────────────────────────────────────────────────
    {
        "destination": "Lima, Perú",
        "title": "Clima — Lima",
        "content": (
            "Lima tiene clima desértico costero, entre 12°C y 28°C. Garúa (llovizna gris persistente) "
            "en invierno, de junio a octubre. No hay riesgo de altitud (0-154 msnm)."
        ),
    },
    {
        "destination": "Lima, Perú",
        "title": "Gastronomía y cultura — Lima",
        "content": (
            "Lima es considerada la capital gastronómica de Latinoamérica, con mezcla de arquitectura "
            "colonial, republicana y moderna. Miraflores y Barranco son las zonas turísticas más seguras "
            "y con mejor oferta de restaurantes."
        ),
    },
    {
        "destination": "Lima, Perú",
        "title": "Practicidad y seguridad — Lima",
        "content": (
            "Ciudad de más de 10 millones de habitantes con tráfico intenso; se recomienda usar apps de "
            "taxi (Uber, Cabify) en vez de taxis de calle. Evitar mostrar joyas u objetos de valor en "
            "vía pública, especialmente en el centro histórico."
        ),
    },
    # ─── Arequipa ───────────────────────────────────────────────────────────
    {
        "destination": "Arequipa, Perú",
        "title": "Clima y altitud — Arequipa",
        "content": (
            "Arequipa está a 2,335 msnm, con cielos soleados casi todo el año y noches frías (0-5°C). "
            "La aclimatación necesaria es leve comparada con Cusco."
        ),
    },
    {
        "destination": "Arequipa, Perú",
        "title": "Cultura y gastronomía — Arequipa",
        "content": (
            "Conocida como la Ciudad Blanca por su arquitectura colonial de sillar volcánico. El "
            "Monasterio de Santa Catalina es una visita imperdible. El rocoto relleno es el plato "
            "bandera de la región. Es una de las ciudades más seguras del Perú para turistas."
        ),
    },
    {
        "destination": "Arequipa, Perú",
        "title": "Excursiones — Cañón del Colca",
        "content": (
            "Arequipa es la base ideal para visitar el Cañón del Colca, uno de los más profundos del "
            "mundo, famoso por el vuelo del cóndor andino observable desde el mirador Cruz del Cóndor."
        ),
    },
    # ─── Cancún / México ────────────────────────────────────────────────────
    {
        "destination": "Cancún, México",
        "title": "Clima y playa — Cancún",
        "content": (
            "Clima tropical cálido todo el año, entre 24°C y 32°C. Temporada de huracanes de junio a "
            "noviembre (mayor riesgo agosto-octubre). Aguas turquesas del Caribe, ideal para snorkel "
            "y buceo en la segunda barrera de coral más grande del mundo."
        ),
    },
    {
        "destination": "Cancún, México",
        "title": "Practicidad — Cancún",
        "content": (
            "Moneda: Peso mexicano (MXN), aunque en la zona hotelera aceptan dólares. Los resorts "
            "todo incluido concentran la oferta turística; la Zona Hotelera está conectada por avenida "
            "principal con transporte público (colectivos) económico."
        ),
    },
    {
        "destination": "Cancún, México",
        "title": "Excursiones cercanas — Riviera Maya",
        "content": (
            "Desde Cancún son accesibles en excursión de un día Chichén Itzá (zona arqueológica maya, "
            "una de las 7 maravillas del mundo moderno), Tulum y los cenotes de la Riviera Maya."
        ),
    },
    # ─── Europa ─────────────────────────────────────────────────────────────
    {
        "destination": "Europa",
        "title": "Documentación — Europa (Schengen)",
        "content": (
            "Para ciudadanos peruanos, el ingreso a la mayoría de países de Europa (zona Schengen) no "
            "requiere visa para estadías turísticas cortas, pero sí pasaporte vigente con al menos 6 "
            "meses de validez y, según el país, comprobante de solvencia y seguro de viaje."
        ),
    },
    {
        "destination": "Europa",
        "title": "Transporte interurbano — Europa",
        "content": (
            "El tren de alta velocidad es la forma más eficiente de moverse entre ciudades europeas "
            "cercanas (ej. Madrid-París en tren+conexión, o trayectos internos como París-Roma en "
            "tren nocturno). Reservar con anticipación reduce el costo significativamente."
        ),
    },
    {
        "destination": "Europa",
        "title": "Clima y temporada — Europa",
        "content": (
            "El clima varía fuertemente por país y estación. La temporada alta turística (junio-agosto) "
            "tiene mejor clima pero mayores precios y aglomeraciones; primavera (abril-mayo) y otoño "
            "(septiembre-octubre) ofrecen buen clima con menor afluencia."
        ),
    },
]


def default_destination_snippet(destination: str) -> dict[str, str]:
    """Snippet genérico cuando no hay conocimiento curado para el destino exacto."""
    return {
        "destination": destination,
        "climate": "Consultar pronóstico local antes del viaje.",
        "altitude": "Verificar altitud según itinerario.",
        "currency": "Verificar moneda local. Cambio en aeropuerto o banco.",
        "culture": "Respetar costumbres locales. Vestimenta apropiada en sitios religiosos.",
        "tips": "Llevar pasaporte, seguro de viaje y copia de reservas.",
    }
