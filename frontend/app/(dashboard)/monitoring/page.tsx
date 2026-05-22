"use client";

import { useEffect, useState } from "react";
import { Activity, AlertOctagon, CheckCircle, XCircle } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function authHeaders(): HeadersInit {
  const token = typeof window !== "undefined" ? localStorage.getItem("et_token") : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export default function MonitoringPage() {
  const [health, setHealth] = useState<any>(null);
  const [circuits, setCircuits] = useState<any>(null);

  useEffect(() => {
    const load = () => {
      const headers = authHeaders();
      fetch(`${API}/api/v1/monitoring/health`, { headers }).then((r) => r.json()).then(setHealth).catch(() => {});
      fetch(`${API}/api/v1/monitoring/circuit-breakers`, { headers }).then((r) => r.json()).then(setCircuits).catch(() => {});
    };
    load();
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-xl font-bold flex items-center gap-2">
        <Activity size={22} /> Monitoreo del Sistema Multiagente
      </h1>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Heartbeats */}
        <div className="bg-white rounded-xl shadow p-5">
          <h2 className="font-semibold mb-4 text-gray-700">Heartbeats de Agentes</h2>
          <div className="space-y-2">
            {health &&
              Object.entries(health.agents as Record<string, string>).map(([agent, status]) => (
                <div key={agent} className="flex items-center justify-between p-2 rounded-lg bg-gray-50">
                  <div className="flex items-center gap-2">
                    {status === "HEALTHY"
                      ? <CheckCircle size={16} className="text-green-500" />
                      : <XCircle size={16} className="text-red-500" />
                    }
                    <span className="text-sm font-mono">{agent}</span>
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${
                    status === "HEALTHY" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
                  }`}>{status}</span>
                </div>
              ))}
          </div>
        </div>

        {/* Circuit Breakers */}
        <div className="bg-white rounded-xl shadow p-5">
          <h2 className="font-semibold mb-4 text-gray-700 flex items-center gap-2">
            <AlertOctagon size={18} /> Circuit Breakers
          </h2>
          <div className="space-y-2">
            {circuits &&
              Object.entries(circuits as Record<string, any>).map(([service, state]) => (
                <div key={service} className="flex items-center justify-between p-2 rounded-lg bg-gray-50">
                  <span className="text-sm font-mono">{service}</span>
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                    state.state === "CLOSED"
                      ? "bg-green-100 text-green-700"
                      : state.state === "OPEN"
                      ? "bg-red-100 text-red-700"
                      : "bg-yellow-100 text-yellow-700"
                  }`}>
                    {state.state}
                  </span>
                </div>
              ))}
          </div>
        </div>
      </div>
    </div>
  );
}
