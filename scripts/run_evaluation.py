#!/usr/bin/env python3
"""
Run Evaluation — Everywhere Travel Sistema Multiagente

Corre el golden set (tests/evaluation/golden_set.py) contra la capa de
salida estructurada (core/structured_output.py) e imprime un reporte.
Es la evaluación local que sustituye a LangSmith (no se usa, ver
docs/architecture.md sección de evaluación).

No requiere Ollama ni servicios corriendo — evalúa la capa de parseo/validación,
no llamadas LLM en vivo (para eso, ver "Evaluación end-to-end" en
docs/architecture.md, que usa scripts/demo_flow.py + agent_interaction_logs).

Uso:
    python scripts/run_evaluation.py
    python scripts/run_evaluation.py --json   # salida en JSON para CI
"""
from __future__ import annotations

import argparse
import json
import sys

from core.structured_output import parse_structured_output
from tests.evaluation.golden_set import GOLDEN_CASES


def run() -> list[dict]:
    results = []
    for case in GOLDEN_CASES:
        result = parse_structured_output(case.raw_output, case.model)
        passed = (result is not None) == case.expect_valid
        field_mismatches = []

        if passed and result is not None and case.expected_fields:
            for field, expected in case.expected_fields.items():
                actual = getattr(result, field)
                if actual != expected:
                    passed = False
                    field_mismatches.append(f"{field}: esperado={expected!r} obtenido={actual!r}")

        results.append({
            "id": case.id,
            "agent": case.agent,
            "description": case.description,
            "expect_valid": case.expect_valid,
            "got_valid": result is not None,
            "passed": passed,
            "field_mismatches": field_mismatches,
        })
    return results


def print_report(results: list[dict]) -> None:
    print(f"{'ID':<18} {'Agente':<20} {'Resultado':<6} Descripción")
    print("-" * 90)
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"{r['id']:<18} {r['agent']:<20} {status:<6} {r['description']}")
        for mismatch in r["field_mismatches"]:
            print(f"{'':<45} -> {mismatch}")

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    pct = (passed / total * 100) if total else 0.0
    print("-" * 90)
    print(f"Total: {passed}/{total} casos pasaron ({pct:.1f}%)")

    by_agent: dict[str, list[dict]] = {}
    for r in results:
        by_agent.setdefault(r["agent"], []).append(r)
    print("\nPor agente:")
    for agent, cases in by_agent.items():
        agent_passed = sum(1 for c in cases if c["passed"])
        print(f"  {agent:<20} {agent_passed}/{len(cases)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Corre el golden set de evaluación local")
    parser.add_argument("--json", action="store_true", help="Salida en JSON (para CI)")
    args = parser.parse_args()

    results = run()

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        print_report(results)

    failed = sum(1 for r in results if not r["passed"])
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
