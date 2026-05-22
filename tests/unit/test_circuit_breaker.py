"""
Tests del Circuit Breaker.
Verifica transiciones CLOSED→OPEN→HALF_OPEN→CLOSED.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from core.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError, FAILURE_THRESHOLD


class FakeRedisStore:
    def __init__(self):
        self._state = {}
        self._failures = {}

    async def get_circuit_state(self, service):
        return self._state.get(service, {"state": "CLOSED", "failure_count": 0, "last_failure": None})

    async def set_circuit_state(self, service, state):
        self._state[service] = state

    async def increment_circuit_failures(self, service):
        self._failures[service] = self._failures.get(service, 0) + 1
        return self._failures[service]

    async def reset_circuit_failures(self, service):
        self._failures[service] = 0


@pytest.mark.asyncio
class TestCircuitBreaker:
    async def test_closed_state_allows_calls(self):
        redis = FakeRedisStore()
        cb = CircuitBreaker("test-service", redis)

        async def ok_func():
            return "success"

        result = await cb.call(ok_func)
        assert result == "success"

    async def test_open_after_threshold_failures(self):
        redis = FakeRedisStore()
        cb = CircuitBreaker("test-service", redis)

        async def failing_func():
            raise ValueError("Simulated failure")

        for _ in range(FAILURE_THRESHOLD):
            with pytest.raises(ValueError):
                await cb.call(failing_func)

        state = await redis.get_circuit_state("test-service")
        assert state["state"] == "OPEN"

    async def test_open_circuit_raises_without_calling(self):
        redis = FakeRedisStore()
        redis._state["test-service"] = {
            "state": "OPEN",
            "failure_count": 5,
            "last_failure": "2026-05-22T00:00:00+00:00",
        }
        cb = CircuitBreaker("test-service", redis)

        call_count = 0

        async def should_not_be_called():
            nonlocal call_count
            call_count += 1
            return "called"

        with pytest.raises(CircuitBreakerOpenError):
            await cb.call(should_not_be_called)

        assert call_count == 0, "La función no debe llamarse con el circuito OPEN"

    async def test_success_resets_circuit(self):
        redis = FakeRedisStore()
        redis._state["test-service"] = {
            "state": "HALF_OPEN",
            "failure_count": 3,
            "last_failure": "2026-05-22T00:00:00+00:00",
        }
        cb = CircuitBreaker("test-service", redis)

        async def success_func():
            return "ok"

        await cb.call(success_func)
        state = await redis.get_circuit_state("test-service")
        assert state["state"] == "CLOSED"
