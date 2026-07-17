"""
Document Agent — Generación asincrónica de documentos PDF con cola persistente.

Responsabilidades exclusivas:
- Cola de trabajos async (3 workers concurrentes)
- Renderizado Jinja2 → WeasyPrint → PDF
- Upload a MinIO (S3-compatible)
- Retry con exponential backoff (max 3 intentos)
- Evento DocumentReady al completarse
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
import httpx
from botocore.exceptions import ClientError
from jinja2 import Environment, FileSystemLoader, select_autoescape
from tenacity import retry, stop_after_attempt, wait_exponential

from agents.base_agent import BaseAgent
from core.mcp.envelope import MCPEnvelope

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
DB_API_URL = os.environ.get("DB_API_URL", "http://api:8000")

REQUIRED_FIELDS = {
    "INVOICE":     ["reservation_code", "total_cost"],
    "LIQUIDATION": ["reservation_code", "total_charged", "total_paid"],
    "VOUCHER":     ["reservation_code", "destination"],
    "REPORT":      ["report_type", "period"],
    "CONTRACT":    ["reservation_code", "client_id"],
}


class DocumentAgent(BaseAgent):
    agent_id = "document-agent"
    queue_name = "document-jobs"
    system_prompt_file = "agents/document/prompts/system_prompt.txt"

    def __init__(self) -> None:
        super().__init__()
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
        self._bucket = "everywheretravel-docs"
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            self._s3.head_bucket(Bucket=self._bucket)
        except ClientError:
            try:
                self._s3.create_bucket(Bucket=self._bucket)
                logger.info(f"[Document] Bucket creado: {self._bucket}")
            except Exception as e:
                logger.warning(f"[Document] No se pudo crear bucket: {e}")

    def _register_handlers(self) -> None:
        self._consumer.register_handler("DocumentJob", self.handle_message)

    async def handle_message(self, envelope: MCPEnvelope) -> None:
        job = envelope.payload
        job_id = job.get("job_id", str(uuid.uuid4()))
        doc_type = job.get("document_type")
        template_data = job.get("template_data", {})

        logger.info(
            f"[Document] Procesando job={job_id} tipo={doc_type} "
            f"prioridad={job.get('priority')}"
        )

        # Actualizar estado en DB
        await self._update_job_status(job_id, "PROCESSING")

        # Validar campos requeridos
        missing = self._check_required_fields(doc_type, template_data)
        if missing:
            await self._fail_job(job_id, f"Campos faltantes: {missing}", envelope)
            return

        try:
            document_url = await self._generate_with_retry(
                job_id, doc_type, template_data
            )
            expires_at = (
                datetime.now(timezone.utc) + timedelta(days=7)
            ).isoformat()

            # Actualizar estado COMPLETE en DB
            await self._update_job_status(job_id, "COMPLETE", document_url)

            # Publicar DocumentReady
            await self.publish(
                payload_type="DocumentReady",
                payload={
                    "job_id": job_id,
                    "document_type": doc_type,
                    "reference_id": job.get("reference_id"),
                    "document_url": document_url,
                    "expires_at": expires_at,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                },
                receiver_agent="notification-agent",
                routing_key="notification.document_ready",
                saga_id=envelope.saga_id,
            )

            self._messages_processed += 1
            logger.info(f"[Document] Documento generado: {document_url}")

        except Exception as e:
            await self._fail_job(job_id, str(e), envelope)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        reraise=True,
    )
    async def _generate_with_retry(
        self, job_id: str, doc_type: str, data: dict
    ) -> str:
        html = await self._render_template(doc_type, data)
        pdf_bytes = await self._html_to_pdf(html)
        url = await self._upload_to_minio(job_id, doc_type, pdf_bytes)
        return url

    async def _render_template(self, doc_type: str, data: dict) -> str:
        template_name = f"{doc_type.lower()}.html"
        try:
            template = self._jinja.get_template(template_name)
            return template.render(**data)
        except Exception:
            # Fallback: template genérico
            return self._generic_html(doc_type, data)

    async def _html_to_pdf(self, html: str) -> bytes:
        try:
            import weasyprint
            pdf = weasyprint.HTML(string=html).write_pdf()
            return pdf
        except ImportError:
            # Fallback en entorno sin WeasyPrint
            return html.encode()

    async def _upload_to_minio(
        self, job_id: str, doc_type: str, content: bytes
    ) -> str:
        key = f"{doc_type.lower()}/{datetime.now().strftime('%Y/%m')}/{job_id}.pdf"
        self._s3.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=content,
            ContentType="application/pdf",
        )
        url = self._s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=604800,  # 7 días
        )
        return url

    async def _fail_job(
        self, job_id: str, reason: str, envelope: MCPEnvelope
    ) -> None:
        logger.error(f"[Document] Job fallido {job_id}: {reason}")
        await self._update_job_status(job_id, "FAILED", error=reason)
        await self.publish(
            payload_type="DocumentFailed",
            payload={"job_id": job_id, "reason": reason},
            receiver_agent="monitoring-agent",
            routing_key="monitoring.document_failed",
            saga_id=envelope.saga_id,
        )

    def _check_required_fields(self, doc_type: str, data: dict) -> list[str]:
        required = REQUIRED_FIELDS.get(doc_type, [])
        return [f for f in required if f not in data]

    async def _update_job_status(
        self, job_id: str, status: str,
        url: str | None = None, error: str | None = None
    ) -> None:
        try:
            await self._http.patch(
                f"/api/v1/document-jobs/{job_id}",
                json={"status": status, "document_url": url, "error_message": error},
            )
        except Exception as e:
            logger.warning(f"[Document] Error actualizando estado del job: {e}")

    def _generic_html(self, doc_type: str, data: dict) -> str:
        return f"""
        <html><body>
        <h1>Everywhere Travel — {doc_type}</h1>
        <pre>{data}</pre>
        <p>Generado: {datetime.now().isoformat()}</p>
        </body></html>
        """


if __name__ == "__main__":
    from core.logging_config import configure_logging
    configure_logging("document-agent")
    agent = DocumentAgent()
    asyncio.run(agent.run())
