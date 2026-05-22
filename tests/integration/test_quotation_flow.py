"""
Tests de integración — Escenario A: Flujo completo de cotización.
Requiere API corriendo (pytest --integration).
"""
import pytest
import httpx
import uuid

BASE_URL = "http://localhost:8000"
pytestmark = pytest.mark.integration


@pytest.fixture
def client():
    return httpx.Client(base_url=BASE_URL, timeout=30)


@pytest.fixture
def sample_client_id(client):
    resp = client.post("/api/v1/clients", json={
        "full_name": "Test Usuario",
        "email": f"test_{uuid.uuid4().hex[:6]}@test.com",
    })
    assert resp.status_code == 200
    return resp.json()["id"]


class TestQuotationFlow:
    def test_submit_inquiry_creates_saga(self, client, sample_client_id):
        resp = client.post("/api/v1/inquiries", json={
            "client_id": sample_client_id,
            "destination": "Cusco",
            "start_date": "2026-08-01",
            "end_date": "2026-08-06",
            "budget_min": 1000,
            "budget_max": 3000,
            "traveler_count": 2,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "saga_id" in data
        assert data["status"] == "processing"

    def test_concurrent_quotations_independent(self, client, sample_client_id):
        """Dos cotizaciones simultáneas deben generar quote_ids diferentes."""
        import threading
        results = []

        def submit():
            r = client.post("/api/v1/inquiries", json={
                "client_id": sample_client_id,
                "destination": "Cancún",
                "start_date": "2026-09-01",
                "end_date": "2026-09-08",
                "budget_min": 2000,
                "budget_max": 5000,
                "traveler_count": 3,
            })
            results.append(r.json())

        threads = [threading.Thread(target=submit) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        saga_ids = [r.get("saga_id") for r in results]
        # Todas las sagas deben ser únicas (no hay colisión)
        assert len(set(saga_ids)) == len(saga_ids), "Saga IDs deben ser únicos"

    def test_package_search_returns_results(self, client):
        resp = client.get("/api/v1/packages/search", params={
            "destination": "Cusco",
            "budget_max": 5000,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "packages" in data


class TestReservationConflict:
    def test_duplicate_reservation_code_rejected(self, client, sample_client_id):
        """Dos reservas con el mismo código deben fallar la segunda."""
        code = f"ET-20260801-TESTA"
        payload = {
            "reservation_code": code,
            "quote_id": str(uuid.uuid4()),
            "client_id": sample_client_id,
            "travel_start": "2026-08-01T10:00:00+00:00",
            "travel_end": "2026-08-06T10:00:00+00:00",
            "traveler_count": 2,
        }
        r1 = client.post("/api/v1/reservations", json=payload)
        assert r1.status_code == 200

        r2 = client.post("/api/v1/reservations", json=payload)
        # Segunda reserva con mismo código debe fallar
        assert r2.status_code != 200 or r2.json().get("error") is not None


class TestFinanceFlow:
    def test_payment_schedule_low_amount(self):
        """Montos <= 1000 PEN deben tener pago único."""
        from agents.finance.agent import FinanceAgent
        from decimal import Decimal

        agent = FinanceAgent.__new__(FinanceAgent)
        schedule = agent._build_payment_schedule(
            Decimal("800"), "2026-08-01T00:00:00+00:00"
        )
        assert len(schedule) == 1
        assert schedule[0]["pct"] == 100

    def test_payment_schedule_high_amount(self):
        """Montos > 5000 PEN deben tener 3 cuotas."""
        from agents.finance.agent import FinanceAgent
        from decimal import Decimal

        agent = FinanceAgent.__new__(FinanceAgent)
        schedule = agent._build_payment_schedule(
            Decimal("7500"), "2026-08-01T00:00:00+00:00"
        )
        assert len(schedule) == 3
        pcts = [s["pct"] for s in schedule]
        assert pcts == [30, 40, 30]
        assert sum(pcts) == 100
