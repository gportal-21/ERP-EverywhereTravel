"use client";

import { useEffect, useState } from "react";
import { Activity, CheckCircle, AlertTriangle, FileText, TrendingUp } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const WS = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

function authHeaders(): HeadersInit {
  const token = typeof window !== "undefined" ? localStorage.getItem("et_token") : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

interface SystemHealth {
  agents: Record<string, string>;
  healthy_count: number;
  total_agents: number;
}

interface Alert {
  type: string;
  message: string;
  timestamp: string;
}

export default function DashboardPage() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [sagas, setSagas] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadData = async () => {
      const headers = authHeaders();
      try {
        const [healthData, sagasData] = await Promise.all([
          fetch(`${API}/api/v1/monitoring/health`, { headers }).then((r) => r.ok ? r.json() : null),
          fetch(`${API}/api/v1/sagas?status=RUNNING`, { headers }).then((r) => r.ok ? r.json() : { sagas: [] }),
        ]);
        if (healthData) setHealth(healthData);
        setSagas(sagasData?.sagas || []);
      } catch (_) {}
      setLoading(false);
    };
    loadData();

    // WebSocket para alertas en tiempo real
    let ws: WebSocket;
    try {
      ws = new WebSocket(`${WS}/ws/system:alerts`);
      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          setAlerts((prev) => [
            { type: data.type, message: data.message || data.type, timestamp: new Date().toISOString() },
            ...prev.slice(0, 9),
          ]);
        } catch (_) {}
      };
    } catch (_) {}

    const interval = setInterval(async () => {
      try {
        const r = await fetch(`${API}/api/v1/monitoring/health`, { headers: authHeaders() });
        if (r.ok) setHealth(await r.json());
      } catch (_) {}
    }, 15000);

    return () => {
      try { ws?.close(); } catch (_) {}
      clearInterval(interval);
    };
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600" />
      </div>
    );
  }

  const healthPct = health
    ? Math.round((health.healthy_count / health.total_agents) * 100)
    : 0;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Dashboard — Everywhere Travel</h1>
        <span className="text-sm text-gray-500">Sistema Multiagente v1.0</span>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <StatCard
          icon={<Activity className="text-blue-500" />}
          label="Agentes Activos"
          value={`${health?.healthy_count ?? "—"}/${health?.total_agents ?? 9}`}
          sub={`${healthPct}% saludables`}
          color="blue"
        />
        <StatCard
          icon={<TrendingUp className="text-green-500" />}
          label="Sagas en Curso"
          value={sagas.length}
          sub="flujos activos"
          color="green"
        />
        <StatCard
          icon={<AlertTriangle className="text-yellow-500" />}
          label="Alertas"
          value={alerts.length}
          sub="últimas 10"
          color="yellow"
        />
        <StatCard
          icon={<CheckCircle className="text-purple-500" />}
          label="Sistema"
          value={healthPct >= 80 ? "OPERATIVO" : "DEGRADADO"}
          sub={`${healthPct}% capacidad`}
          color={healthPct >= 80 ? "purple" : "red"}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Estado de Agentes */}
        <div className="bg-white rounded-xl shadow p-5">
          <h2 className="font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <Activity size={18} /> Estado de Agentes
          </h2>
          <div className="space-y-2">
            {health &&
              Object.entries(health.agents).map(([agent, status]) => (
                <div key={agent} className="flex items-center justify-between py-2 border-b border-gray-50">
                  <span className="text-sm font-mono text-gray-600">{agent}</span>
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                      status === "HEALTHY"
                        ? "bg-green-100 text-green-700"
                        : "bg-yellow-100 text-yellow-700"
                    }`}
                  >
                    {status}
                  </span>
                </div>
              ))}
          </div>
        </div>

        {/* Alertas en tiempo real */}
        <div className="bg-white rounded-xl shadow p-5">
          <h2 className="font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <AlertTriangle size={18} /> Alertas en Tiempo Real
          </h2>
          {alerts.length === 0 ? (
            <p className="text-gray-400 text-sm text-center py-8">Sin alertas activas</p>
          ) : (
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {alerts.map((a, i) => (
                <div key={i} className="flex items-start gap-3 p-2 bg-yellow-50 rounded-lg">
                  <AlertTriangle size={14} className="text-yellow-500 mt-0.5 flex-shrink-0" />
                  <div>
                    <p className="text-xs font-medium text-gray-700">{a.type}</p>
                    <p className="text-xs text-gray-500">{a.message}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Sagas activas */}
      <div className="bg-white rounded-xl shadow p-5">
        <h2 className="font-semibold text-gray-700 mb-4 flex items-center gap-2">
          <FileText size={18} /> Sagas en Ejecución
        </h2>
        {sagas.length === 0 ? (
          <p className="text-gray-400 text-sm text-center py-6">Sin sagas en curso</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b">
                  <th className="pb-2 font-medium">Saga ID</th>
                  <th className="pb-2 font-medium">Tipo</th>
                  <th className="pb-2 font-medium">Pasos</th>
                  <th className="pb-2 font-medium">Estado</th>
                </tr>
              </thead>
              <tbody>
                {sagas.slice(0, 10).map((saga) => (
                  <tr key={saga.saga_id} className="border-b border-gray-50">
                    <td className="py-2 font-mono text-xs text-gray-500">
                      {saga.saga_id?.slice(0, 8)}...
                    </td>
                    <td className="py-2">{saga.saga_type}</td>
                    <td className="py-2">{saga.steps?.length ?? 0}</td>
                    <td className="py-2">
                      <span className="px-2 py-0.5 bg-blue-100 text-blue-700 text-xs rounded-full">
                        {saga.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({ icon, label, value, sub, color }: any) {
  return (
    <div className="bg-white rounded-xl shadow p-5">
      <div className="flex items-center justify-between mb-3">
        <span className="text-gray-500 text-sm">{label}</span>
        {icon}
      </div>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
      <p className="text-xs text-gray-400 mt-1">{sub}</p>
    </div>
  );
}
