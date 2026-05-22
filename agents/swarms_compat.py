"""
Swarms Compatibility Layer — Everywhere Travel

Problema: swarms==6.8.7 tiene dependencias opcionales pesadas
(transformers/PyTorch, langchain_community) que se importan en tiempo de carga
de __init__.py aunque no se usen.

Solución: parchear los módulos/atributos faltantes ANTES de importar swarms.
Las clases stub permiten que swarms cargue sin PyTorch ni las features de ML avanzado.
Solo usamos Agent, SequentialWorkflow y AgentRearrange → las demás features no son necesarias.
"""
from __future__ import annotations

import sys
import types
import logging

logger = logging.getLogger(__name__)


def _patch_transformers() -> None:
    """
    transformers está instalado pero sin PyTorch sus clases de logits no existen.
    swarms/tools/logits_processor.py hereda de transformers.LogitsWarper en
    tiempo de definición de clase (nivel de módulo) — no en tiempo de uso.
    Parcheamos con un stub antes de que swarms importe ese módulo.
    """
    try:
        import transformers  # noqa: PLC0415

        missing = []
        for attr in ("LogitsWarper", "LogitsProcessor", "LogitsProcessorList"):
            if not hasattr(transformers, attr):
                missing.append(attr)
                setattr(transformers, attr, type(attr, (), {
                    "__init__": lambda self, *a, **kw: None,
                    "__call__":  lambda self, *a, **kw: a[1] if len(a) > 1 else None,
                }))

        if missing:
            logger.debug(f"[swarms_compat] transformers stubs creados: {missing}")
    except ImportError:
        # transformers no instalado: crear módulo stub completo
        fake = types.ModuleType("transformers")
        for attr in ("LogitsWarper", "LogitsProcessor", "LogitsProcessorList"):
            setattr(fake, attr, type(attr, (), {}))
        sys.modules["transformers"] = fake
        logger.debug("[swarms_compat] transformers módulo stub creado (no instalado)")


def _patch_tool_agent() -> None:
    """
    swarms/agents/tool_agent.py usa Jsonformer (requiere PyTorch).
    Reemplazamos el módulo antes de que Python lo cargue.
    """
    if "swarms.agents.tool_agent" not in sys.modules:
        fake = types.ModuleType("swarms.agents.tool_agent")
        fake.ToolAgent = type("ToolAgent", (), {
            "__init__": lambda self, *a, **kw: None,
            "run":      lambda self, *a, **kw: "",
        })
        sys.modules["swarms.agents.tool_agent"] = fake


def _ensure_langchain_stubs() -> None:
    """
    Asegura que langchain_community esté disponible como módulo.
    Si ya está instalado por pip, este bloque no hace nada.
    Si no está instalado, crea stubs mínimos para que swarm_models cargue.
    """
    stub_paths = [
        "langchain_community",
        "langchain_community.embeddings",
        "langchain_community.embeddings.openai",
        "langchain_community.chat_models",
        "langchain_community.llms",
    ]
    try:
        import langchain_community  # noqa: F401, PLC0415
        return  # ya instalado → no necesitamos stubs
    except ImportError:
        pass

    for path in stub_paths:
        if path not in sys.modules:
            mod = types.ModuleType(path)
            sys.modules[path] = mod

    # OpenAIEmbeddings stub (swarm_models lo importa)
    lc_emb = sys.modules.get("langchain_community.embeddings.openai")
    if lc_emb and not hasattr(lc_emb, "OpenAIEmbeddings"):
        lc_emb.OpenAIEmbeddings = type("OpenAIEmbeddings", (), {"__init__": lambda s, *a, **k: None})

    logger.debug("[swarms_compat] langchain_community stubs creados (no instalado)")


def _apply_all_patches() -> None:
    """Aplica todos los parches necesarios. Debe llamarse antes de 'import swarms'."""
    _ensure_langchain_stubs()
    _patch_transformers()
    _patch_tool_agent()


# ── Aplicar parches y exponer las clases de Swarms ───────────────────────────

_apply_all_patches()

try:
    from swarms import Agent, AgentRearrange, SequentialWorkflow  # noqa: E402
    SWARMS_AVAILABLE = True
    logger.info("[swarms_compat] swarms cargado correctamente (Agent, SequentialWorkflow, AgentRearrange)")
except Exception as exc:
    SWARMS_AVAILABLE = False
    logger.error(f"[swarms_compat] swarms no disponible: {exc}")

    # Stubs de último recurso para que los agentes no crasheen en import
    class Agent:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            self._name = kwargs.get("agent_name", "stub-agent")
            logger.warning(f"[swarms_compat] Usando Agent STUB (swarms no disponible): {self._name}")

        def run(self, task: str) -> str:
            logger.warning(f"[swarms_compat] Agent.run() stub — devolviendo vacío")
            return ""

    class SequentialWorkflow:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs): pass
        def run(self, task: str) -> str: return ""

    class AgentRearrange:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs): pass
        def run(self, task: str) -> str: return ""


__all__ = ["Agent", "SequentialWorkflow", "AgentRearrange", "SWARMS_AVAILABLE"]
