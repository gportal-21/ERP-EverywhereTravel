"""
Itinerary Agent — Genera itinerarios día a día con Claude vía Swarms.

Flujo:
  1. Recibe QuotationResult (VALIDATED) o petición directa de la API
  2. swarms.Agent redacta el itinerario completo día a día en JSON
  3. El JSON se renderiza en la plantilla HTML profesional
  4. xhtml2pdf convierte HTML → PDF
  5. El PDF se sube a MinIO con URL firmada
  6. Publica ItineraryReady con el URL de descarga

Herramientas Swarms:
  - _tool_get_destination_info: datos culturales/clima del destino
  - _tool_calculate_days: calcula la distribución de días del viaje
  - _tool_get_included_services: obtiene los servicios incluidos del paquete
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import boto3
import httpx
from botocore.exceptions import ClientError
from jinja2 import Environment, FileSystemLoader, select_autoescape

from agents.base_agent import BaseAgent
from agents.swarms_compat import Agent
from core.mcp.envelope import MCPEnvelope

logger = logging.getLogger(__name__)

DB_API_URL    = os.environ.get("DB_API_URL", "http://api:8000")
LLM_MODEL     = os.environ.get("LLM_MODEL", "ollama/qwen3:8b")
ENABLE_LLM_ITINERARY = os.environ.get("ENABLE_LLM_ITINERARY", "false").lower() == "true"
TEMPLATES_DIR = Path(__file__).parent.parent / "document" / "templates"
BUCKET        = "everywheretravel-docs"


# ── Swarms Tools ──────────────────────────────────────────────────────────────

def _tool_get_destination_info(destination: str) -> str:
    """Returns cultural, climate and practical information about a travel destination.

    Args:
        destination: The travel destination (city, country or region)

    Returns:
        JSON string with climate, culture, currency, timezone and tips
    """
    # Base de conocimiento estática (en producción se conectaría a una API de viajes)
    INFO = {
        "cusco": {
            "climate": "Clima templado, 7-18°C. Temporada seca mayo-octubre. Llevar ropa en capas.",
            "altitude": "3,399 msnm. Riesgo de soroche los primeros días. Mate de coca recomendado.",
            "currency": "Sol peruano (PEN). Hay cajeros en el centro. Propinas: 10% restaurantes.",
            "culture": "Ciudad Inca y Colonial. Quechua y español. Mercado San Pedro imperdible.",
            "tips": "Aclimatarse 1-2 días antes de visitar Machu Picchu. Reservar trenes con anticipación.",
        },
        "lima": {
            "climate": "Clima desértico costero, 12-28°C. Garúa en invierno (jun-oct).",
            "altitude": "0-154 msnm. Sin riesgo de altura.",
            "currency": "Sol peruano (PEN). Ciudad de 10M habitantes. Miraflores zona turística segura.",
            "culture": "Capital gastronómica de Latinoamérica. Mezcla colonial, republicana y moderna.",
            "tips": "Tráfico intenso. Usar Uber o taxi de app. No mostrar joyas en la calle.",
        },
        "arequipa": {
            "climate": "2,335 msnm. Cielos soleados casi todo el año. Noches frías (0-5°C).",
            "altitude": "2,335 msnm. Leve aclimatación recomendada.",
            "currency": "Sol peruano. Ciudad Blanca por el sillar volcánico. Muy segura para turistas.",
            "culture": "Arquitectura colonial de sillar. Monasterio Santa Catalina imperdible.",
            "tips": "Base ideal para Colca Canyon. Rocoto relleno es el plato bandera.",
        },
    }
    dest_key = destination.lower().split(",")[0].strip()
    for key, info in INFO.items():
        if key in dest_key:
            return json.dumps({"destination": destination, **info})

    return json.dumps({
        "destination": destination,
        "climate": "Consultar pronóstico local antes del viaje.",
        "altitude": "Verificar altitud según itinerario.",
        "currency": "Verificar moneda local. Cambio en aeropuerto o banco.",
        "culture": "Respetar costumbres locales. Vestimenta apropiada en sitios religiosos.",
        "tips": "Llevar pasaporte, seguro de viaje y copia de reservas.",
    })


def _tool_calculate_days(start_date: str, end_date: str) -> str:
    """Calculates trip duration and suggests activity distribution across days.

    Args:
        start_date: Trip start date (YYYY-MM-DD)
        end_date: Trip end date (YYYY-MM-DD)

    Returns:
        JSON string with total_days, arrival_day, departure_day and suggestions
    """
    try:
        start = datetime.fromisoformat(start_date)
        end   = datetime.fromisoformat(end_date)
        total = max(1, (end - start).days + 1)
        return json.dumps({
            "total_days": total,
            "arrival_day": 1,
            "departure_day": total,
            "full_days": max(0, total - 2),
            "suggestion": (
                f"Día 1: llegada y aclimatación. "
                f"Días 2-{total-1}: actividades principales. "
                f"Día {total}: visita libre y traslado al aeropuerto."
            ) if total > 2 else f"Viaje de {total} día(s).",
        })
    except Exception:
        return json.dumps({"total_days": 5, "suggestion": "Itinerario estándar de 5 días."})


def _tool_get_included_services(line_items_json: str) -> str:
    """Extracts included services from quotation line items for the itinerary.

    Args:
        line_items_json: JSON string of line_items from the quotation

    Returns:
        JSON string with included list and not_included standard items
    """
    try:
        items = json.loads(line_items_json)
        included = [item.get("concept", "") for item in items if item.get("subtotal", 0) > 0]
        return json.dumps({
            "included": included or ["Alojamiento según programa", "Traslados incluidos en itinerario"],
            "not_included": [
                "Boletos de avión internacionales (salvo indicación)",
                "Propinas al guía y conductor",
                "Gastos personales y souvenirs",
                "Comidas no especificadas en el programa",
                "Seguro de viaje (recomendado)",
            ],
        })
    except Exception:
        return json.dumps({
            "included": ["Alojamiento", "Traslados", "Guía local"],
            "not_included": ["Vuelos", "Propinas", "Gastos personales"],
        })


# ── Agent ─────────────────────────────────────────────────────────────────────

class ItineraryAgent(BaseAgent):
    agent_id = "itinerary-agent"
    queue_name = "itinerary-events"
    system_prompt_file = "agents/itinerary/prompts/system_prompt.txt"

    def __init__(self) -> None:
        super().__init__()
        self._swarm_agent: Agent | None = None
        self._http = httpx.AsyncClient(base_url=DB_API_URL, timeout=60)
        self._jinja = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=select_autoescape(["html"]),
        )
        self._s3 = boto3.client(
            "s3",
            endpoint_url=f"http://{os.environ.get('MINIO_ENDPOINT', 'minio:9000')}",
            aws_access_key_id=os.environ.get("MINIO_ACCESS_KEY", "etminio"),
            aws_secret_access_key=os.environ.get("MINIO_SECRET_KEY", "etminiopass"),
        )
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            self._s3.head_bucket(Bucket=BUCKET)
        except ClientError:
            try:
                self._s3.create_bucket(Bucket=BUCKET)
            except Exception:
                pass

    async def initialize(self) -> None:
        await super().initialize()
        self._swarm_agent = Agent(
            agent_name="itinerary-writer-et",
            system_prompt=self._system_prompt,
            model_name=LLM_MODEL,
            max_loops=1,
            tools=[
                _tool_get_destination_info,
                _tool_calculate_days,
                _tool_get_included_services,
            ],
            output_type="str",
            verbose=False,
            temperature=0.7,  # más creatividad para redacción de viajes
        )
        logger.info("[Itinerary] Swarms Agent inicializado con 3 tools de viaje")

    def _register_handlers(self) -> None:
        self._consumer.register_handler("QuotationResult", self.handle_message)
        self._consumer.register_handler("GenerateItinerary", self.handle_message)

    async def handle_message(self, envelope: MCPEnvelope) -> None:
        payload = envelope.payload

        # Solo procesar cotizaciones VALIDATED
        if envelope.payload_type == "QuotationResult" and payload.get("status") != "VALIDATED":
            return

        logger.info(
            f"[Itinerary] Generando itinerario | "
            f"destino={payload.get('destination', 'N/A')} saga={envelope.saga_id}"
        )

        try:
            itinerary_data = await self._generate_itinerary(payload)
            pdf_url = await self._render_and_upload_pdf(
                template_name="itinerary.html",
                data={**itinerary_data, "generated_at": datetime.now().strftime("%d/%m/%Y %H:%M")},
                doc_type="itinerary",
                reference_id=payload.get("quote_id", str(uuid.uuid4())),
            )

            await self._save_document_job(payload, pdf_url, "ITINERARY")

            await self.publish(
                payload_type="ItineraryReady",
                payload={
                    "quote_id": payload.get("quote_id"),
                    "client_id": payload.get("client_id"),
                    "destination": itinerary_data.get("destination"),
                    "itinerary_url": pdf_url,
                    "title": itinerary_data.get("title"),
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                },
                receiver_agent="notification-agent",
                routing_key="notification.itinerary_ready",
                saga_id=envelope.saga_id,
            )

            await self._redis.publish_realtime(
                f"client:{payload.get('client_id')}",
                {"event": "itinerary_ready", "url": pdf_url, "title": itinerary_data.get("title")},
            )

            self._messages_processed += 1
            logger.info(f"[Itinerary] PDF generado: {pdf_url}")

        except Exception as e:
            logger.error(f"[Itinerary] Error generando itinerario: {e}")

    async def _generate_itinerary(self, payload: dict) -> dict:
        """Usa swarms.Agent para redactar el itinerario completo."""
        destination   = payload.get("destination", "Destino no especificado")
        start_date    = payload.get("start_date") or payload.get("customizations", {}).get("start_date", "")
        end_date      = payload.get("end_date")   or payload.get("customizations", {}).get("end_date", "")
        traveler_count = payload.get("traveler_count") or payload.get("customizations", {}).get("traveler_count", 1)
        line_items    = json.dumps(payload.get("line_items", []))
        total_cost    = payload.get("total_cost", 0)

        prompt = (
            f"Generate a complete travel itinerary with these details:\n"
            f"- Destination: {destination}\n"
            f"- Dates: {start_date} to {end_date}\n"
            f"- Travelers: {traveler_count}\n"
            f"- Package includes: {line_items}\n"
            f"- Total price: S/. {total_cost}\n\n"
            f"Use the tools to get destination info, calculate day distribution, "
            f"and extract included services. Then write a rich, detailed itinerary. "
            f"Return ONLY valid JSON matching the specified schema."
        )

        if not ENABLE_LLM_ITINERARY:
            logger.info("[Itinerary] LLM deshabilitado para itinerario; usando fallback determinístico")
            return self._fallback_itinerary(destination, start_date, end_date, traveler_count)

        try:
            raw = await asyncio.to_thread(self._swarm_agent.run, prompt)
            return self._parse_itinerary_json(raw, destination, start_date, end_date, traveler_count)
        except Exception as e:
            logger.warning(f"[Itinerary] Swarms Agent falló ({type(e).__name__}), usando fallback")
            return self._fallback_itinerary(destination, start_date, end_date, traveler_count)

    def _parse_itinerary_json(
        self, raw: str, destination: str, start_date: str, end_date: str, travelers: int
    ) -> dict:
        try:
            text = raw.strip()
            if "```" in text:
                for block in reversed(text.split("```")):
                    cleaned = block.lstrip("json").strip()
                    if cleaned.startswith("{"):
                        text = cleaned
                        break
            elif "{" in text:
                start = text.rfind("{")
                end   = text.rfind("}") + 1
                text  = text[start:end]

            data = json.loads(text)
            if "days" in data:
                return data
        except Exception:
            pass
        return self._fallback_itinerary(destination, start_date, end_date, travelers)

    def _fallback_itinerary(
        self, destination: str, start_date: str, end_date: str, travelers: int
    ) -> dict:
        """Itinerario estructurado cuando el LLM no está disponible."""
        try:
            s = datetime.fromisoformat(start_date)
            e = datetime.fromisoformat(end_date)
            days_count = max(1, (e - s).days + 1)
        except Exception:
            days_count = 5

        days = []
        for i in range(days_count):
            if i == 0:
                days.append({
                    "day": 1, "title": f"Día 1: Llegada a {destination}",
                    "morning": "Traslado al aeropuerto de origen. Check-in del vuelo.",
                    "afternoon": f"Llegada a {destination}. Traslado al hotel y check-in.",
                    "evening": "Cena de bienvenida en restaurante local. Descanso.",
                    "accommodation": "Hotel según categoría del paquete.",
                    "meals": "Cena incluida.",
                    "tip": "Hidratarse bien y descansar para aclimatarse.",
                })
            elif i == days_count - 1:
                days.append({
                    "day": days_count, "title": f"Día {days_count}: Día libre y Regreso",
                    "morning": "Desayuno en el hotel. Tiempo libre para compras y últimas visitas.",
                    "afternoon": "Traslado al aeropuerto para vuelo de regreso.",
                    "evening": "Llegada al destino de origen.",
                    "accommodation": "N/A — día de regreso.",
                    "meals": "Desayuno incluido.",
                    "tip": "Confirmar horario de vuelo con 24h de anticipación.",
                })
            else:
                days.append({
                    "day": i + 1, "title": f"Día {i+1}: Exploración de {destination}",
                    "morning": f"Desayuno en el hotel. Visita a los principales atractivos de {destination}.",
                    "afternoon": "Almuerzo en restaurante local. Continuación del recorrido turístico.",
                    "evening": "Cena y actividades opcionales en el destino.",
                    "accommodation": "Hotel según categoría del paquete.",
                    "meals": "Desayuno incluido. Almuerzo y cena por cuenta del viajero.",
                    "tip": "Llevar calzado cómodo, protector solar y agua.",
                })

        return {
            "title": f"Itinerario — {destination}",
            "subtitle": f"Viaje especial para {travelers} viajero{'s' if travelers > 1 else ''}",
            "destination": destination,
            "duration_summary": f"{days_count} días / {days_count - 1} noches",
            "overview": (
                f"Disfruta de una experiencia inolvidable en {destination}. "
                f"Este itinerario ha sido diseñado especialmente para {travelers} "
                f"viajero{'s' if travelers > 1 else ''}, combinando cultura, gastronomía y aventura."
            ),
            "days": days,
            "included_services": ["Alojamiento en hotel seleccionado", "Traslados aeropuerto-hotel", "Guía local"],
            "not_included": ["Boletos aéreos", "Gastos personales", "Propinas", "Seguro de viaje"],
            "recommendations": "Llevar documentos de identidad, ropa cómoda y cámara fotográfica.",
            "emergency_contacts": "Emergencias: 911 | Everywhere Travel 24h: +51 999 000 000",
        }

    async def _render_and_upload_pdf(
        self, template_name: str, data: dict, doc_type: str, reference_id: str
    ) -> str:
        html = await self._render_html(template_name, data)
        pdf_bytes = await asyncio.to_thread(self._html_to_pdf, html)
        return await asyncio.to_thread(
            self._upload_pdf, pdf_bytes, doc_type, reference_id
        )

    async def _render_html(self, template_name: str, data: dict) -> str:
        try:
            template = self._jinja.get_template(template_name)
            return template.render(**data)
        except Exception as e:
            logger.warning(f"[Itinerary] Template '{template_name}' no encontrado: {e}")
            return self._generic_html(data)

    def _html_to_pdf(self, html: str) -> bytes:
        try:
            from xhtml2pdf import pisa
            buf = io.BytesIO()
            pisa.CreatePDF(html.encode("utf-8"), dest=buf, encoding="utf-8")
            return buf.getvalue()
        except Exception as e:
            logger.warning(f"[Itinerary] xhtml2pdf falló ({e}), usando HTML plano")
            return html.encode("utf-8")

    def _upload_pdf(self, content: bytes, doc_type: str, reference_id: str) -> str:
        key = f"{doc_type}/{datetime.now().strftime('%Y/%m')}/{reference_id}_{uuid.uuid4().hex[:6]}.pdf"
        content_type = "application/pdf" if content[:4] == b"%PDF" else "text/html"
        self._s3.put_object(Bucket=BUCKET, Key=key, Body=content, ContentType=content_type)
        url = self._s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": BUCKET, "Key": key},
            ExpiresIn=604800,
        )
        # El presigned URL usa el hostname interno (minio:9000); reemplazar con el público
        public = os.environ.get("MINIO_PUBLIC_URL", "http://localhost:9000")
        internal = f"http://{os.environ.get('MINIO_ENDPOINT', 'minio:9000')}"
        return url.replace(internal, public)

    async def _save_document_job(self, payload: dict, url: str, doc_type: str) -> None:
        try:
            await self._http.post("/api/v1/document-jobs", json={
                "id": str(uuid.uuid4()),
                "document_type": doc_type,
                "reference_id": payload.get("quote_id", str(uuid.uuid4())),
                "reference_type": "quotation",
                "template_data": payload,
                "status": "COMPLETE",
                "document_url": url,
                "requested_by_agent": self.agent_id,
            })
        except Exception as e:
            logger.warning(f"[Itinerary] Error guardando DocumentJob: {e}")

    def _generic_html(self, data: dict) -> str:
        days_html = ""
        for day in data.get("days", []):
            days_html += f"""
            <div class="day">
                <h3>{day.get('title', '')}</h3>
                <p><b>Mañana:</b> {day.get('morning', '')}</p>
                <p><b>Tarde:</b> {day.get('afternoon', '')}</p>
                <p><b>Noche:</b> {day.get('evening', '')}</p>
                <p><b>Alojamiento:</b> {day.get('accommodation', '')}</p>
                <p><b>💡 Tip:</b> {day.get('tip', '')}</p>
            </div>"""
        return f"""<html><body style="font-family:Arial;padding:20px;color:#333">
        <h1 style="color:#1e40af">{data.get('title','')}</h1>
        <p>{data.get('overview','')}</p>
        {days_html}
        <p><i>Generado por Everywhere Travel</i></p>
        </body></html>"""


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    agent = ItineraryAgent()
    asyncio.run(agent.run())
