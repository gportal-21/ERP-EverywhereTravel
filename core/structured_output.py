"""Structured Output — fuerza y valida las salidas JSON del LLM contra un schema Pydantic.

Antes: cada agente pedía "Return ONLY valid JSON" en el prompt y parseaba el
texto con regex/split de bloques ```json``` (ver *_parse_*_output en los
agentes), sin garantía real de que el LLM respetara el formato.

Ahora: el JSON Schema del modelo Pydantic se pasa como `response_schema` al
`Agent` de Swarms (agents/swarms_compat.py), que para el proveedor activo
(Ollama) lo reenvía como `format` en `/api/generate` — Ollama restringe el
decoding token a token para que la salida cumpla el schema (constrained
decoding, disponible desde Ollama >= 0.5). Esto es sustancialmente más
confiable que solo instruir por prompt, que es importante porque el modelo
activo es local de 8B (ver README, sección "Nota sobre el proveedor LLM").

parse_structured_output() todavía intenta una extracción manual como red de
seguridad (proveedores/modelos que ignoren `format`, o el _FallbackAgent de
swarms_compat cuando ni Ollama ni swarms están disponibles).
"""
from __future__ import annotations

import logging
from typing import TypeVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def _extract_json_block(raw: str) -> str:
    text = raw.strip()
    if "```" in text:
        for block in reversed(text.split("```")):
            cleaned = block.lstrip("json").strip()
            if cleaned.startswith("{") or cleaned.startswith("["):
                return cleaned
    if "{" in text and "}" in text:
        start, end = text.find("{"), text.rfind("}") + 1
        if 0 <= start < end:
            return text[start:end]
    if "[" in text and "]" in text:
        start, end = text.find("["), text.rfind("]") + 1
        if 0 <= start < end:
            return text[start:end]
    return text


def parse_structured_output(raw: str, model: type[T]) -> T | None:
    """Valida `raw` contra `model`. Retorna None si no se pudo obtener una
    instancia válida ni con constrained decoding ni con extracción manual —
    el llamador debe usar su fallback determinístico en ese caso."""
    try:
        return model.model_validate_json(raw)
    except ValidationError:
        pass
    except Exception:
        pass

    extracted = _extract_json_block(raw)
    try:
        return model.model_validate_json(extracted)
    except ValidationError as e:
        logger.warning("[StructuredOutput] %s no validó contra %s: %s", extracted[:200], model.__name__, e)
        return None
    except Exception as e:
        logger.warning("[StructuredOutput] %s no es JSON válido: %s", extracted[:200], e)
        return None
