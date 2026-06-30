"use client";

import { useEffect, useState } from "react";
import { Activity, AlertOctagon, CheckCircle, XCircle, RefreshCw, Wifi, WifiOff, Shield } from "lucide-react";
import { API, authHeaders, fetchJson } from "@/lib/fetch-api";
import { PageHeader } from "@/components/ui/page-header";
import { StatusBadge } from "@/components/ui/status-badge";
import { Skeleton } from "@/components/ui/skeleton";
import { DataState } from "@/components/ui/data-state";

export default function MonitoringPage() {
  const [health, setHealth] = useState<any>(null);
  const [circuits, setCircuits] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [loadError, setLoadError] = useState("");

  const load = () => {
    const headers = authHeaders();
    setLoadError("");
    Promise.all([
      fetchJson<any>(`${API}/api/v1/monitoring/health`, { headers }),
      fetchJson<any>(`${API}/api/v1/monitoring/circuit-breakers`, { headers }),
    ]).then(([h, c]) => {
      if (h.data) setHealth(h.data);
      if (c.data) setCircuits(c.data);
      if (h.error || c.error) setLoadError(h.error || c.error || "No se pudo cargar monitoreo");
      setLastUpdate(new Date());
      setLoading(false);
    }).catch(() => {
      setLoadError("No se pudo conectar con monitoreo");
      setLoading(false);
    });
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, []);

  const healthyCount = health?.healthy_count ?? 0;
  const totalAgents = health?.total_agents ?? 0;
  const healthPct = totalAgents > 0 ? Math.round((healthyCount / totalAgents) * 100) : 0;

  const circuitEntries = circuits ? Object.entries(circuits as Record<string, any>) : [];
  const closedCount = circuitEntries.filter(([, s]) => s.state === "CLOSED").length;
  const openCount = circuitEntries.filter(([, s]) => s.state === "OPEN").length;

  return (
    <div className="p-4 sm:p-6 space-y-6">
      <PageHeader
        icon={<Activity size={20} />}
        title="Monitoreo del Sistema"
        subtitle="Estado en tiempo real del sistema multiagente"
        actions={
          <div className="flex items-center gap-3">
            {lastUpdate && (
              <span className="text-xs text-gray-400 hidden sm:inline">
                Actualizado: {lastUpdate.toLocaleTimeString("es-PE")}
              </span>
            )}
            <button
              onClick={load}
              className="p-2.5 hover:bg-white rounded-xl border border-gray-200 transition-colors"
              aria-label="Refrescar"
            >
              <RefreshCw size={14} className={loading ? "animate-spin text-blue-500" : "text-gray-400"} />
            </button>
          </div>
        }
      />

      {loadError && (
        <DataState kind="error" title="Monitoreo parcialmente no disponible" description={loadError} actionLabel="Reintentar" onAction={load} />
      )}

      {/* Overview cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <OverviewCard
          label="Agentes activos"
          value={loading ? null : `${healthyCount}/${totalAgents}`}
          sub={loading ? null : `${healthPct}% operativo`}
          variant={healthPct >= 80 ? "success" : healthPct >= 50 ? "warning" : "error"}
        />
        <OverviewCard
          label="Circuit Breakers"
          value={loading ? null : `${closedCount}/${circuitEntries.length}`}
          sub={loading ? null : openCount > 0 ? `${openCount} abierto${openCount > 1 ? "s" : ""}` : "Todos cerrados"}
          variant={openCount === 0 ? "success" : "error"}
        />
        <OverviewCard
          label="Estado general"
          value={loading ? null : (healthPct >= 80 && openCount === 0 ? "OK" : "Degradado")}
          sub={loading ? null : "Sistema multiagente"}
          variant={healthPct >= 80 && openCount === 0 ? "success" : "warning"}
        />
        <OverviewCard
          label="Intervalo"
          value="10s"
          sub="Auto-refresco"
          variant="info"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Agent Heartbeats */}
        <div className="bg-white rounded-2xl shadow-sm ring-1 ring-gray-100 p-5">
          <h2 className="font-semibold text-gray-800 mb-4 flex items-center gap-2 text-sm">
            <Wifi size={15} className="text-blue-500" />
            Heartbeats de Agentes
          </h2>
          {loading ? (
            <div className="space-y-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="flex items-center justify-between p-3 rounded-xl bg-gray-50">
                  <Skeleton className="h-4 w-32" />
                  <Skeleton className="h-5 w-20 rounded-full" />
                </div>
              ))}
            </div>
          ) : health ? (
            <div className="space-y-2">
              {/* Summary bar */}
              <div className="mb-4">
                <div className="flex justify-between text-xs text-gray-500 mb-1.5">
                  <span>Salud del sistema</span>
                  <span className="font-medium">{healthPct}%</span>
                </div>
                <div className="h-2.5 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${
                      healthPct >= 80 ? "bg-emerald-500" : healthPct >= 50 ? "bg-amber-400" : "bg-red-500"
                    }`}
                    style={{ width: `${healthPct}%` }}
                  />
                </div>
              </div>

              {Object.entries(health.agents as Record<string, string>).map(([agent, status]) => {
                const isHealthy = status === "HEALTHY";
                return (
                  <div
                    key={agent}
                    className={`flex items-center justify-between p-3 rounded-xl transition-colors ${
                      isHealthy ? "bg-gray-50 hover:bg-gray-100" : "bg-red-50/50 hover:bg-red-50"
                    }`}
                  >
                    <div className="flex items-center gap-2.5">
                      {isHealthy
                        ? <CheckCircle size={16} className="text-emerald-500" />
                        : <XCircle size={16} className="text-red-500" />
                      }
                      <span className="text-sm font-mono text-gray-700">{agent}</span>
                    </div>
                    <StatusBadge variant={isHealthy ? "success" : "error"}>
                      {status}
                    </StatusBadge>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="text-center py-8">
              <WifiOff size={32} className="mx-auto text-gray-300 mb-2" />
              <p className="text-sm text-gray-400">No se pudo obtener el estado de los agentes</p>
            </div>
          )}
        </div>

        {/* Circuit Breakers */}
        <div className="bg-white rounded-2xl shadow-sm ring-1 ring-gray-100 p-5">
          <h2 className="font-semibold text-gray-800 mb-4 flex items-center gap-2 text-sm">
            <Shield size={15} className="text-purple-500" />
            Circuit Breakers
          </h2>
          {loading ? (
            <div className="space-y-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="flex items-center justify-between p-3 rounded-xl bg-gray-50">
                  <Skeleton className="h-4 w-36" />
                  <Skeleton className="h-5 w-20 rounded-full" />
                </div>
              ))}
            </div>
          ) : circuitEntries.length > 0 ? (
            <div className="space-y-2">
              {/* Legend */}
              <div className="flex flex-wrap gap-3 mb-4 text-xs text-gray-500">
                <span className="flex items-center gap-1">
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" /> CLOSED (normal)
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2.5 h-2.5 rounded-full bg-amber-500" /> HALF_OPEN (probando)
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2.5 h-2.5 rounded-full bg-red-500" /> OPEN (cortado)
                </span>
              </div>

              {circuitEntries.map(([service, state]) => {
                const variant = state.state === "CLOSED" ? "success"
                  : state.state === "OPEN" ? "error"
                  : "warning";
                return (
                  <div
                    key={service}
                    className={`flex items-center justify-between p-3 rounded-xl transition-colors ${
                      state.state === "CLOSED" ? "bg-gray-50 hover:bg-gray-100" :
                      state.state === "OPEN" ? "bg-red-50/50 hover:bg-red-50" :
                      "bg-amber-50/50 hover:bg-amber-50"
                    }`}
                  >
                    <div className="flex items-center gap-2.5">
                      <AlertOctagon size={16} className={
                        state.state === "CLOSED" ? "text-emerald-500" :
                        state.state === "OPEN" ? "text-red-500" : "text-amber-500"
                      } />
                      <span className="text-sm font-mono text-gray-700">{service}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      {state.failure_count > 0 && (
                        <span className="text-xs text-gray-400">
                          {state.failure_count} fallos
                        </span>
                      )}
                      <StatusBadge variant={variant as any}>
                        {state.state}
                      </StatusBadge>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="text-center py-8">
              <AlertOctagon size={32} className="mx-auto text-gray-300 mb-2" />
              <p className="text-sm text-gray-400">No hay circuit breakers registrados</p>
            </div>
          )}
        </div>
      </div>

      {/* Info footer */}
      <div className="bg-blue-50/50 border border-blue-100 rounded-2xl p-4 flex items-start gap-3">
        <Activity size={16} className="text-blue-500 mt-0.5 flex-shrink-0" />
        <div className="text-xs text-blue-700 space-y-1">
          <p className="font-medium">Sobre el monitoreo</p>
          <p className="text-blue-600">
            Los heartbeats se verifican cada 10 segundos. Un agente se marca como UNHEALTHY si no responde
            en 3 ciclos consecutivos. Los circuit breakers protegen al sistema de cascadas de fallos:
            cuando un servicio externo falla repetidamente, el circuito se "abre" y las peticiones
            se rechazan inmediatamente hasta que el servicio se recupere.
          </p>
        </div>
      </div>
    </div>
  );
}

function OverviewCard({ label, value, sub, variant }: {
  label: string;
  value: string | null;
  sub: string | null;
  variant: "success" | "warning" | "error" | "info";
}) {
  const colors = {
    success: "ring-emerald-100 bg-emerald-50/30",
    warning: "ring-amber-100 bg-amber-50/30",
    error: "ring-red-100 bg-red-50/30",
    info: "ring-blue-100 bg-blue-50/30",
  };
  const textColors = {
    success: "text-emerald-700",
    warning: "text-amber-700",
    error: "text-red-700",
    info: "text-blue-700",
  };

  return (
    <div className={`rounded-2xl p-4 ring-1 ${colors[variant]}`}>
      <p className="text-xs text-gray-500 font-medium mb-1">{label}</p>
      {value === null ? (
        <Skeleton className="h-7 w-16 mb-1" />
      ) : (
        <p className={`text-2xl font-bold ${textColors[variant]}`}>{value}</p>
      )}
      {sub === null ? (
        <Skeleton className="h-3 w-20 mt-1" />
      ) : (
        <p className={`text-xs mt-0.5 ${textColors[variant]} opacity-70`}>{sub}</p>
      )}
    </div>
  );
}
