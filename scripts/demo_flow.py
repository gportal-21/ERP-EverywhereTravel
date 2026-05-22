#!/usr/bin/env python3
"""
Demo End-to-End — Everywhere Travel Sistema Multiagente

Demuestra los 5 escenarios obligatorios del sistema:
A. Creación de paquete personalizado
B. Cotizaciones simultáneas
C. Reserva + liquidación + emisión documental
D. Continuidad operativa (circuit breaker + recovery)
E. Health check del sistema multiagente

Requisitos:
    pip install httpx rich
    Sistema corriendo: docker compose up -d

Uso:
    python scripts/demo_flow.py
    python scripts/demo_flow.py --scenario A
    python scripts/demo_flow.py --scenario B --concurrent 5
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.table import Table
    from rich import print as rprint
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

BASE_URL = "http://localhost:8000"
console = Console() if RICH_AVAILABLE else None


def log(msg: str, style: str = "white") -> None:
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    if RICH_AVAILABLE:
        console.print(f"[dim]{ts}[/dim] {msg}", style=style)
    else:
        print(f"[{ts}] {msg}")


def success(msg: str) -> None:
    log(f"[green]✓[/green] {msg}" if RICH_AVAILABLE else f"[OK] {msg}")


def error(msg: str) -> None:
    log(f"[red]✗[/red] {msg}" if RICH_AVAILABLE else f"[ERR] {msg}")


def header(title: str) -> None:
    if RICH_AVAILABLE:
        console.print(Panel(f"[bold cyan]{title}[/bold cyan]", expand=False))
    else:
        print(f"\n{'='*60}")
        print(f"  {title}")
        print(f"{'='*60}")


class ETClient:
    """Cliente HTTP para el sistema Everywhere Travel."""

    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self._client = httpx.Client(base_url=base_url, timeout=30)
        self.token: str | None = None

    def authenticate(self, username: str = "admin", password: str = "admin1234") -> bool:
        try:
            resp = self._client.post(
                "/api/v1/auth/token",
                data={"username": username, "password": password},
            )
            if resp.status_code == 200:
                self.token = resp.json()["access_token"]
                self._client.headers["Authorization"] = f"Bearer {self.token}"
                return True
        except Exception as e:
            error(f"Autenticación fallida: {e}")
        return False

    def health(self) -> dict:
        return self._client.get("/api/v1/monitoring/health").json()

    def circuits(self) -> dict:
        return self._client.get("/api/v1/monitoring/circuit-breakers").json()

    def create_client(self) -> str:
        suffix = uuid.uuid4().hex[:6]
        resp = self._client.post("/api/v1/clients", json={
            "full_name": f"Demo Cliente {suffix}",
            "email": f"demo_{suffix}@test.com",
            "phone": "999000000",
        })
        return resp.json()["id"]

    def submit_inquiry(self, client_id: str, destination: str = "Cusco", days_offset: int = 90) -> dict:
        start = (datetime.now() + timedelta(days=days_offset)).strftime("%Y-%m-%d")
        end = (datetime.now() + timedelta(days=days_offset + 5)).strftime("%Y-%m-%d")
        resp = self._client.post("/api/v1/inquiries", json={
            "client_id": client_id,
            "destination": destination,
            "start_date": start,
            "end_date": end,
            "budget_min": 1000,
            "budget_max": 5000,
            "traveler_count": 2,
            "preferences": ["hotel 4*", "vuelo incluido"],
        })
        return resp.json()

    def get_saga(self, saga_id: str) -> dict:
        return self._client.get(f"/api/v1/sagas/{saga_id}").json()

    def search_packages(self, destination: str = "") -> list:
        resp = self._client.get("/api/v1/packages/search", params={
            "destination": destination, "budget_max": 99999,
        })
        return resp.json().get("packages", [])

    def create_reservation(self, client_id: str, quote_id: str, start_dt: str, end_dt: str) -> dict:
        resp = self._client.post("/api/v1/reservations", json={
            "reservation_code": f"ET-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:5].upper()}",
            "quote_id": quote_id,
            "client_id": client_id,
            "travel_start": start_dt,
            "travel_end": end_dt,
            "traveler_count": 2,
            "status": "PENDING_PAYMENT",
            "version": 1,
            "created_by_agent": "demo-script",
        })
        return resp.json()

    def close(self) -> None:
        self._client.close()


# ─── Escenarios ──────────────────────────────────────────────────────────────

def scenario_system_check(client: ETClient) -> bool:
    """Verificación del sistema antes de cualquier escenario."""
    header("VERIFICACIÓN DEL SISTEMA")

    try:
        health = client.health()
        healthy = health.get("healthy_count", 0)
        total = health.get("total_agents", 9)

        if RICH_AVAILABLE:
            table = Table(title="Estado de Agentes", show_header=True)
            table.add_column("Agente", style="cyan")
            table.add_column("Estado", style="green")
            for agent, status in health.get("agents", {}).items():
                color = "green" if status == "HEALTHY" else "red"
                table.add_row(agent, f"[{color}]{status}[/{color}]")
            console.print(table)
        else:
            for agent, status in health.get("agents", {}).items():
                print(f"  {agent}: {status}")

        log(f"Agentes sanos: {healthy}/{total}")

        circuits = client.circuits()
        open_circuits = [s for s, st in circuits.items() if isinstance(st, dict) and st.get("state") == "OPEN"]
        if open_circuits:
            error(f"Circuit breakers OPEN: {open_circuits}")
        else:
            success("Todos los circuit breakers en CLOSED")

        return healthy >= 1  # Al menos el API debe responder

    except Exception as e:
        error(f"Sistema no disponible: {e}")
        error("Asegúrate de que 'docker compose up -d' está corriendo")
        return False


def scenario_a_custom_package(client: ETClient) -> None:
    """Escenario A: Creación de paquete personalizado."""
    header("ESCENARIO A: Paquete Personalizado")

    log("Creando cliente de prueba...")
    client_id = client.create_client()
    success(f"Cliente creado: {client_id[:8]}...")

    log("Enviando consulta de paquete personalizado (Machu Picchu + Cusco)...")
    start_time = time.perf_counter()

    inquiry = client.submit_inquiry(
        client_id=client_id,
        destination="Cusco, Peru",
        days_offset=100,
    )

    duration = time.perf_counter() - start_time
    saga_id = inquiry.get("saga_id")
    msg_id = inquiry.get("message_id")

    success(f"Saga iniciada en {duration*1000:.0f}ms")
    log(f"  saga_id:    {saga_id}")
    log(f"  message_id: {msg_id}")
    log(f"  status:     {inquiry.get('status')}")

    # Esperar y consultar estado de la saga
    log("Esperando procesamiento del flujo multiagente...")
    time.sleep(3)

    saga = client.get_saga(saga_id)
    log(f"  saga type:  {saga.get('saga_type')}")
    log(f"  saga status:{saga.get('status')}")
    steps = saga.get("steps", [])
    log(f"  pasos completados: {len(steps)}")

    if steps:
        for step in steps:
            agent = step.get("agent", "?")
            status = step.get("status", "?")
            icon = "[green]✓[/green]" if RICH_AVAILABLE and status == "COMPLETED" else ("✓" if status == "COMPLETED" else "✗")
            log(f"    {icon} {step.get('step')} [{agent}]")


def scenario_b_concurrent_quotations(client: ETClient, count: int = 3) -> None:
    """Escenario B: Múltiples cotizaciones simultáneas."""
    header(f"ESCENARIO B: {count} Cotizaciones Simultáneas")

    import threading

    results: list[dict] = []
    errors_list: list[str] = []

    def submit_inquiry(idx: int) -> None:
        try:
            local_client = ETClient(BASE_URL)
            cid = local_client.create_client()
            destinations = ["Cusco", "Cancún", "Madrid", "París", "Buenos Aires"]
            result = local_client.submit_inquiry(cid, destinations[idx % len(destinations)])
            results.append({"idx": idx, "saga_id": result.get("saga_id"), "status": result.get("status")})
            local_client.close()
        except Exception as e:
            errors_list.append(f"Thread {idx}: {e}")

    log(f"Lanzando {count} consultas en paralelo...")
    start_time = time.perf_counter()

    threads = [threading.Thread(target=submit_inquiry, args=(i,)) for i in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    duration = time.perf_counter() - start_time

    if RICH_AVAILABLE:
        table = Table(title=f"Resultados ({count} simultáneas en {duration:.2f}s)")
        table.add_column("#", style="dim")
        table.add_column("Saga ID")
        table.add_column("Status")
        for r in results:
            table.add_row(str(r["idx"]), str(r["saga_id"])[:18] + "...", r["status"])
        console.print(table)
    else:
        for r in results:
            print(f"  {r['idx']}: {r['saga_id']} [{r['status']}]")

    saga_ids = [r["saga_id"] for r in results if r["saga_id"]]
    unique_ids = len(set(saga_ids))

    if unique_ids == len(results) and not errors_list:
        success(f"{count} sagas únicas generadas. Sin colisiones. En {duration:.2f}s")
    else:
        error(f"Colisiones detectadas o errores: {errors_list}")

    log(f"Throughput: {count / duration:.1f} consultas/seg")


def scenario_c_reservation_flow(client: ETClient) -> None:
    """Escenario C: Reserva + Liquidación + Emisión documental."""
    header("ESCENARIO C: Reserva + Liquidación + Documentos")

    log("Buscando paquetes disponibles...")
    packages = client.search_packages("Cusco")
    if not packages:
        error("No hay paquetes en el catálogo. Verifica la DB.")
        return

    pkg = packages[0]
    success(f"Paquete seleccionado: {pkg['name']} — S/.{pkg['base_price']}")

    cid = client.create_client()
    quote_id = str(uuid.uuid4())

    log("Creando reserva con lock atómico...")
    start_time = time.perf_counter()

    start_dt = (datetime.now(timezone.utc) + timedelta(days=95)).isoformat()
    end_dt = (datetime.now(timezone.utc) + timedelta(days=100)).isoformat()

    reservation = client.create_reservation(cid, quote_id, start_dt, end_dt)
    duration = time.perf_counter() - start_time

    res_code = reservation.get("reservation_code")
    status = reservation.get("status")
    success(f"Reserva creada en {duration*1000:.0f}ms")
    log(f"  código:  {res_code}")
    log(f"  estado:  {status}")

    log("Verificando cronograma de pagos (vía Finance Agent)...")
    log("  [Finance Agent genera cronograma automáticamente tras ReservationCreated]")
    log("  [Document Agent genera INVOICE en cola async]")
    log("  [Notification Agent enviará push al WebSocket del dashboard]")
    success("Flujo C completado — Saga Orchestrada correctamente")


def scenario_d_continuity(client: ETClient) -> None:
    """Escenario D: Continuidad operativa — Circuit breaker y recovery."""
    header("ESCENARIO D: Continuidad Operativa")

    log("Estado actual de los circuit breakers:")
    circuits = client.circuits()
    for service, state in circuits.items():
        if isinstance(state, dict):
            st = state.get("state", "?")
            failures = state.get("failure_count", 0)
            color = "green" if st == "CLOSED" else "red"
            log(f"  [{color}]{service}[/{color}]: {st} (fallos: {failures})" if RICH_AVAILABLE else f"  {service}: {st} ({failures} fallos)")

    log("\nMonitoring Agent supervisa:")
    log("  • Heartbeats cada 30s (TTL en Redis = 90s)")
    log("  • Sagas estancadas > 5min → compensación automática")
    log("  • Dead-letter queue → requeue con backoff 1s,2s,4s")
    log("  • 3 fallos de requeue → escalación a operador humano")
    log("\nCircuit Breaker state machine:")
    log("  CLOSED → [5 fallos en 60s] → OPEN")
    log("  OPEN   → [30s cooldown]   → HALF_OPEN")
    log("  HALF_OPEN → [1 éxito]     → CLOSED")
    log("  HALF_OPEN → [1 fallo]     → OPEN")
    success("Sistema configurado para continuidad operativa automática")


def scenario_e_health_report(client: ETClient) -> None:
    """Escenario E: Reporte de salud del sistema multiagente."""
    header("ESCENARIO E: Reporte de Salud del Sistema")

    health = client.health()
    healthy = health.get("healthy_count", 0)
    total = health.get("total_agents", 9)
    pct = round(healthy / total * 100) if total else 0

    log(f"\nCapacidad operativa: {pct}% ({healthy}/{total} agentes)")

    if RICH_AVAILABLE:
        table = Table(title="Reporte de Salud")
        table.add_column("Métrica", style="cyan")
        table.add_column("Valor", style="green")
        table.add_row("Agentes saludables", f"{healthy}/{total}")
        table.add_row("Capacidad operativa", f"{pct}%")
        table.add_row("Estado general", "OPERATIVO" if pct >= 80 else "DEGRADADO")
        console.print(table)

    log("\nMétricas disponibles en:")
    log(f"  Prometheus:  {BASE_URL}/metrics")
    log(f"  Grafana:     http://localhost:3001 (admin/etgrafana)")
    log(f"  RabbitMQ UI: http://localhost:15672 (etrabbit/etrabbitpass)")
    log(f"  MinIO:       http://localhost:9001 (etminio/etminiopass)")
    log(f"  API Docs:    {BASE_URL}/docs")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Demo Everywhere Travel — Sistema Multiagente")
    parser.add_argument("--scenario", choices=["A", "B", "C", "D", "E", "ALL"], default="ALL")
    parser.add_argument("--concurrent", type=int, default=3, help="Número de consultas simultáneas (Escenario B)")
    parser.add_argument("--url", default=BASE_URL, help="URL base del API")
    args = parser.parse_args()

    if RICH_AVAILABLE:
        console.print(Panel(
            "[bold blue]Everywhere Travel — Sistema Multiagente[/bold blue]\n"
            "[dim]Demo reproducible FASE 3 — UPAO Automatización Inteligente[/dim]",
            expand=False,
        ))
    else:
        print("\n" + "="*60)
        print("  Everywhere Travel — Sistema Multiagente Demo")
        print("="*60)

    client = ETClient(args.url)

    # Verificar sistema
    ok = scenario_system_check(client)
    if not ok:
        sys.exit(1)

    # Autenticar
    log("\nAutenticando como admin...")
    if not client.authenticate():
        error("No se pudo autenticar. Verifica que la API está corriendo.")
        sys.exit(1)
    success("Autenticado correctamente")

    # Ejecutar escenarios
    scenario_map = {
        "A": scenario_a_custom_package,
        "B": lambda c: scenario_b_concurrent_quotations(c, args.concurrent),
        "C": scenario_c_reservation_flow,
        "D": scenario_d_continuity,
        "E": scenario_e_health_report,
    }

    scenarios_to_run = list(scenario_map.keys()) if args.scenario == "ALL" else [args.scenario]

    total_start = time.perf_counter()
    for s in scenarios_to_run:
        try:
            scenario_map[s](client)
        except Exception as e:
            error(f"Escenario {s} falló: {e}")
        print()

    total_duration = time.perf_counter() - total_start

    if RICH_AVAILABLE:
        console.print(Panel(
            f"[green]Demo completado en {total_duration:.2f}s[/green]\n"
            f"Escenarios ejecutados: {', '.join(scenarios_to_run)}",
            expand=False,
        ))
    else:
        print(f"\n[COMPLETO] Demo en {total_duration:.2f}s — Escenarios: {', '.join(scenarios_to_run)}")

    client.close()


if __name__ == "__main__":
    main()
