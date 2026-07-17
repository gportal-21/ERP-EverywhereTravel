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
import os
from collections.abc import Callable

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


import importlib
import importlib.abc
import importlib.machinery


class _LangchainStubFinder(importlib.abc.MetaPathFinder):
    """
    Meta import hook (Python 3.4+) que intercepta TODOS los imports de
    langchain_community.* y devuelve modulos stub automaticamente.
    """
    class _Dummy:
        def __init__(self, *a, **k): pass
        def __init_subclass__(cls, **k): pass
        def __call__(self, *a, **k): return self

    def find_spec(self, fullname, path, target=None):
        if fullname == "langchain_community" or fullname.startswith("langchain_community."):
            return importlib.machinery.ModuleSpec(fullname, self, is_package=True)
        return None

    def create_module(self, spec):
        class _StubModule(types.ModuleType):
            """Modulo que devuelve _Dummy para cualquier atributo no encontrado."""
            def __getattr__(self, name):
                return _LangchainStubFinder._Dummy
        mod = _StubModule(spec.name)
        mod.__path__ = []
        mod.__package__ = spec.name
        mod.__loader__ = self
        mod.__spec__ = spec
        return mod

    def exec_module(self, module):
        pass


def _ensure_langchain_stubs() -> None:
    """
    Purga langchain_community real de sys.modules e instala el finder
    moderno que genera stubs on-demand para cualquier submodulo.
    """
    to_remove = [k for k in list(sys.modules) if k == "langchain_community" or k.startswith("langchain_community.")]
    for k in to_remove:
        del sys.modules[k]

    if not any(isinstance(f, _LangchainStubFinder) for f in sys.meta_path):
        sys.meta_path.insert(0, _LangchainStubFinder())

    logger.debug("[swarms_compat] langchain_community stub finder instalado")


class _TelemetryStubFinder(importlib.abc.MetaPathFinder):
    """
    Meta import hook que intercepta TODOS los imports de swarms.telemetry.*
    y devuelve modulos stub que retornan no-ops para cualquier atributo.
    Esto evita que swarms intente enviar telemetria o cargue deps pesadas.
    """

    def find_spec(self, fullname, path, target=None):
        if fullname == "swarms.telemetry" or fullname.startswith("swarms.telemetry."):
            return importlib.machinery.ModuleSpec(fullname, self, is_package=True)
        return None

    def create_module(self, spec):
        class _StubModule(types.ModuleType):
            __all__ = []
            def __getattr__(self, name):
                if name.startswith("__") and name.endswith("__"):
                    raise AttributeError(name)
                return lambda *a, **k: {}
        mod = _StubModule(spec.name)
        mod.__path__ = []
        mod.__package__ = spec.name
        mod.__loader__ = self
        mod.__spec__ = spec
        return mod

    def exec_module(self, module):
        pass


def _disable_swarms_telemetry() -> None:
    """Neutraliza la telemetria de swarms para evitar cuelgues de red."""
    import os
    os.environ["SWARM_DISABLE_TELEMETRY"] = "true"
    os.environ.setdefault("WORKSPACE_DIR", "/tmp/swarms")

    # Purgar cualquier modulo de telemetria ya cargado
    to_remove = [k for k in list(sys.modules) if k == "swarms.telemetry" or k.startswith("swarms.telemetry.")]
    for k in to_remove:
        del sys.modules[k]

    # Instalar finder que genera stubs para swarms.telemetry.*
    if not any(isinstance(f, _TelemetryStubFinder) for f in sys.meta_path):
        sys.meta_path.insert(0, _TelemetryStubFinder())

    logger.debug("[swarms_compat] swarms.telemetry stub finder instalado")


def _apply_all_patches() -> None:
    """Aplica todos los parches necesarios. Debe llamarse antes de 'import swarms'."""
    _ensure_langchain_stubs()
    _disable_swarms_telemetry()
    _patch_transformers()
    _patch_tool_agent()


# ── Aplicar parches y exponer las clases de Swarms ───────────────────────────

_apply_all_patches()

try:
    from swarms import Agent as _SwarmsAgent  # noqa: E402
    from swarms import AgentRearrange as _SwarmsAgentRearrange  # noqa: E402
    from swarms import SequentialWorkflow as _SwarmsSequentialWorkflow  # noqa: E402
    SWARMS_AVAILABLE = True
    logger.info("[swarms_compat] swarms cargado correctamente (Agent, SequentialWorkflow, AgentRearrange)")
except Exception as exc:
    SWARMS_AVAILABLE = False
    logger.warning(f"[swarms_compat] swarms no disponible; Ollama directo/fallback activo: {exc}")
    _SwarmsAgent = None
    _SwarmsSequentialWorkflow = None
    _SwarmsAgentRearrange = None

    # Stubs de último recurso para que los agentes no crasheen en import
    class _FallbackAgent:
        def __init__(self, *args, **kwargs):
            self._name = kwargs.get("agent_name", "stub-agent")
            logger.warning(f"[swarms_compat] Usando Agent STUB (swarms no disponible): {self._name}")

        def run(self, task: str) -> str:
            logger.warning(f"[swarms_compat] Agent.run() stub — devolviendo vacío")
            return ""

else:
    _FallbackAgent = None


def _is_ollama_model(model_name: str | None) -> bool:
    provider = os.environ.get("LLM_PROVIDER", "").lower()
    return provider == "ollama" or bool(model_name and model_name.startswith("ollama/"))


def _ollama_model_name(model_name: str | None) -> str:
    model = (model_name or os.environ.get("LLM_MODEL") or "ollama/qwen3:8b").strip()
    return model.removeprefix("ollama/")


def _ollama_base_url() -> str:
    base_url = os.environ.get("OLLAMA_BASE_URL") or os.environ.get("OLLAMA_HOST") or "http://localhost:11434"
    if not base_url.startswith(("http://", "https://")):
        base_url = f"http://{base_url}"
    return base_url.rstrip("/")


class _OllamaAgent:
    """Adaptador síncrono mínimo compatible con swarms.Agent usando la API local de Ollama."""

    def __init__(self, *args, **kwargs):
        self.agent_name = kwargs.get("agent_name") or (args[0] if args else "ollama-agent")
        self.system_prompt = kwargs.get("system_prompt", "")
        self.model_name = _ollama_model_name(kwargs.get("model_name"))
        self.temperature = kwargs.get("temperature", 0.2)
        self.tools: list[Callable] = kwargs.get("tools") or []
        self.timeout = float(os.environ.get("OLLAMA_TIMEOUT", "120"))
        self.base_url = _ollama_base_url()
        # Salida estructurada forzada: si se pasa un JSON Schema (Pydantic
        # .model_json_schema()), Ollama restringe el decoding para que la
        # respuesta cumpla el schema (constrained decoding, Ollama >= 0.5),
        # en vez de depender de "Return ONLY valid JSON" + parseo con regex.
        self.response_schema: dict | None = kwargs.get("response_schema")
        logger.info(
            "[swarms_compat] %s usando Ollama model=%s url=%s structured_output=%s",
            self.agent_name,
            self.model_name,
            self.base_url,
            bool(self.response_schema),
        )

    def _tool_context(self) -> str:
        if not self.tools:
            return ""
        tool_lines = []
        for tool in self.tools:
            name = getattr(tool, "__name__", "tool")
            doc = (getattr(tool, "__doc__", "") or "").strip().splitlines()
            summary = doc[0].strip() if doc else "No description."
            tool_lines.append(f"- {name}: {summary}")
        return (
            "\n\nAvailable local helper tools are described for context. "
            "When useful, reason with their behavior and return the requested final JSON/text:\n"
            + "\n".join(tool_lines)
        )

    def _build_prompt(self, task: str) -> str:
        parts = []
        if self.system_prompt:
            parts.append(f"System instructions:\n{self.system_prompt}")
        parts.append(self._tool_context())
        parts.append(f"Task:\n{task}")
        return "\n\n".join(part for part in parts if part)

    def run(self, task: str) -> str:
        import httpx  # noqa: PLC0415

        payload = {
            "model": self.model_name,
            "prompt": self._build_prompt(task),
            "stream": False,
            "options": {"temperature": self.temperature},
        }
        if self.response_schema:
            payload["format"] = self.response_schema
        try:
            response = httpx.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            return str(data.get("response", "")).strip()
        except Exception as exc:
            logger.warning(
                "[swarms_compat] Ollama falló en %s (%s): %s",
                self.agent_name,
                type(exc).__name__,
                exc,
            )
            raise


class Agent:
    """Wrapper compatible: usa Ollama directo para `ollama/...`; si no, delega a swarms."""

    def __init__(self, *args, **kwargs):
        model_name = kwargs.get("model_name")
        # response_schema es una extensión propia (no existe en swarms.Agent real);
        # solo se reenvía a _OllamaAgent, que es quien sabe pasarlo como `format`.
        response_schema = kwargs.pop("response_schema", None)
        if _is_ollama_model(model_name):
            self._delegate = _OllamaAgent(*args, response_schema=response_schema, **kwargs)
        elif SWARMS_AVAILABLE and _SwarmsAgent is not None:
            self._delegate = _SwarmsAgent(*args, **kwargs)
        else:
            self._delegate = _FallbackAgent(*args, **kwargs)

    def run(self, task: str) -> str:
        return self._delegate.run(task)


class SequentialWorkflow:
    """Wrapper compatible con swarms.SequentialWorkflow y fallback secuencial simple."""

    def __init__(self, *args, **kwargs):
        self.agents = kwargs.get("agents") or []
        self.name = kwargs.get("name", "sequential-workflow")
        if SWARMS_AVAILABLE and _SwarmsSequentialWorkflow is not None and not _all_ollama_agents(self.agents):
            self._delegate = _SwarmsSequentialWorkflow(*args, **kwargs)
        else:
            self._delegate = None

    def run(self, task: str) -> str:
        if self._delegate is not None:
            return self._delegate.run(task)
        result = task
        for agent in self.agents:
            result = agent.run(result)
        return result


class AgentRearrange:
    """Wrapper compatible con swarms.AgentRearrange y fallback por cadena simple."""

    def __init__(self, *args, **kwargs):
        self.agents = kwargs.get("agents") or []
        self.name = kwargs.get("name", "agent-rearrange")
        if SWARMS_AVAILABLE and _SwarmsAgentRearrange is not None and not _all_ollama_agents(self.agents):
            self._delegate = _SwarmsAgentRearrange(*args, **kwargs)
        else:
            self._delegate = None

    def run(self, task: str) -> str:
        if self._delegate is not None:
            return self._delegate.run(task)
        result = task
        outputs = []
        for agent in self.agents:
            result = agent.run(result)
            outputs.append(result)
        return "\n".join(outputs)


def _all_ollama_agents(agents: list) -> bool:
    return bool(agents) and all(isinstance(getattr(agent, "_delegate", None), _OllamaAgent) for agent in agents)


__all__ = ["Agent", "SequentialWorkflow", "AgentRearrange", "SWARMS_AVAILABLE"]
