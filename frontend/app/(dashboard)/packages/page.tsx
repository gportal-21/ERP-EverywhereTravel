"use client";
import { useEffect, useState } from "react";
import { Package, Plus, Pencil, Trash2, Check, X, Search, MapPin, Clock, ChevronRight } from "lucide-react";
import { API, authHeaders, fetchJson, money } from "@/lib/fetch-api";
import { useToast } from "@/hooks/use-toast";
import { Toast } from "@/components/ui/toast";
import { PageHeader } from "@/components/ui/page-header";
import { EmptyState } from "@/components/ui/empty-state";
import { CardGridSkeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/status-badge";
import { DataState } from "@/components/ui/data-state";

const BLANK = { name: "", destination: "", description: "", base_price: 0, duration_days: 0, package_type: "PREDEFINED", currency: "PEN", includes: "", excludes: "" };

export default function PackagesPage() {
  const [packages, setPackages] = useState<any[]>([]);
  const [loading, setLoading]   = useState(true);
  const [search, setSearch]     = useState("");
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving]     = useState(false);
  const [form, setForm]         = useState({ ...BLANK });
  const [editId, setEditId]     = useState<string | null>(null);
  const [editData, setEditData] = useState<any>({});
  const [showInactive, setShowInactive] = useState(false);
  const [loadError, setLoadError] = useState("");
  const { toast, notify } = useToast();

  const load = async () => {
    setLoading(true);
    setLoadError("");
    const { data, error } = await fetchJson<{ packages: any[] }>(`${API}/api/v1/packages/?include_inactive=${showInactive}`, { headers: authHeaders() });
    if (data) setPackages(Array.isArray(data.packages) ? data.packages : []);
    if (error) setLoadError(error);
    setLoading(false);
  };

  useEffect(() => { load(); }, [showInactive]);

  const saveNew = async (e: React.FormEvent) => {
    e.preventDefault(); setSaving(true);
    const payload = {
      ...form,
      base_price: Number(form.base_price),
      duration_days: Number(form.duration_days),
      includes: form.includes ? form.includes.split(",").map((s: string) => s.trim()).filter(Boolean) : [],
      excludes: form.excludes ? form.excludes.split(",").map((s: string) => s.trim()).filter(Boolean) : [],
    };
    const { error } = await fetchJson(`${API}/api/v1/packages/`, { method: "POST", headers: authHeaders(), body: JSON.stringify(payload) });
    if (!error) { notify("Paquete creado"); setForm({ ...BLANK }); setShowForm(false); load(); }
    else notify(error, false);
    setSaving(false);
  };

  const saveEdit = async (id: string) => {
    const { error } = await fetchJson(`${API}/api/v1/packages/${id}`, { method: "PATCH", headers: authHeaders(), body: JSON.stringify(editData) });
    if (!error) { notify("Paquete actualizado"); setEditId(null); load(); }
    else notify(error, false);
  };

  const deactivate = async (id: string, name: string, active: boolean) => {
    const action = active ? "desactivar" : "activar";
    if (!confirm(`${action.charAt(0).toUpperCase() + action.slice(1)} "${name}"?`)) return;
    const { error } = await fetchJson(`${API}/api/v1/packages/${id}`, { method: "PATCH", headers: authHeaders(), body: JSON.stringify({ is_active: !active }) });
    if (!error) { notify(`Paquete ${action}do`); load(); }
    else notify(error, false);
  };

  const filtered = packages.filter(p => !search || p.name.toLowerCase().includes(search.toLowerCase()) || p.destination.toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="p-4 sm:p-6 space-y-5">
      <Toast toast={toast} />

      <PageHeader
        icon={<Package size={20} />}
        title="Paquetes"
        actions={
          <div className="flex gap-2 items-center">
            <label className="flex items-center gap-1.5 text-sm text-gray-500 cursor-pointer select-none">
              <input type="checkbox" checked={showInactive} onChange={e => setShowInactive(e.target.checked)} className="rounded border-gray-300"/>
              Inactivos
            </label>
            <button onClick={() => setShowForm(s => !s)}
              className="flex items-center gap-1.5 bg-blue-600 text-white px-4 py-2.5 rounded-xl text-sm font-medium hover:bg-blue-700 transition-colors shadow-sm">
              <Plus size={14}/> Nuevo
            </button>
          </div>
        }
      />

      <div className="relative">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"/>
        <input type="text" placeholder="Buscar paquete o destino..." value={search} onChange={e => setSearch(e.target.value)}
          className="w-full pl-10 pr-4 py-2.5 bg-white border border-gray-200 rounded-xl text-sm focus:border-blue-500 transition-colors"/>
      </div>

      {showForm && (
        <div className="bg-blue-50/50 border border-blue-100 rounded-2xl p-5 sm:p-6 animate-fade-in">
          <h2 className="font-semibold text-gray-800 mb-4 text-sm">Nuevo Paquete</h2>
          <form onSubmit={saveNew} className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {[
              { label: "Nombre *", key: "name", col: 2 },
              { label: "Destino *", key: "destination", col: 1 },
              { label: "Tipo", key: "package_type", col: 1, select: ["PREDEFINED", "CUSTOM"] },
              { label: "Precio base (S/.)", key: "base_price", col: 1, type: "number" },
              { label: "Duracion (dias)", key: "duration_days", col: 1, type: "number" },
              { label: "Descripcion", key: "description", col: 2 },
              { label: "Incluye (separado por comas)", key: "includes", col: 2 },
              { label: "No incluye (separado por comas)", key: "excludes", col: 2 },
            ].map(({ label, key, col, type, select }: any) => (
              <div key={key} className={col === 2 ? "sm:col-span-2" : ""}>
                <label className="block text-xs font-medium text-gray-600 mb-1.5">{label}</label>
                {select ? (
                  <select value={(form as any)[key]} onChange={e => setForm({...form, [key]: e.target.value})}
                    className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:border-blue-500 bg-white transition-colors">
                    {select.map((o: string) => <option key={o}>{o}</option>)}
                  </select>
                ) : (
                  <input type={type || "text"} value={(form as any)[key]} required={label.includes("*")}
                    onChange={e => setForm({...form, [key]: e.target.value})}
                    className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:border-blue-500 bg-white transition-colors"/>
                )}
              </div>
            ))}
            <div className="sm:col-span-2 flex gap-2 justify-end pt-2">
              <button type="button" onClick={() => setShowForm(false)} className="px-4 py-2.5 border border-gray-200 rounded-xl text-sm text-gray-600 hover:bg-white transition-colors">Cancelar</button>
              <button type="submit" disabled={saving} className="px-5 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-sm">
                {saving ? "Guardando..." : "Crear Paquete"}
              </button>
            </div>
          </form>
        </div>
      )}

      {loading ? (
        <CardGridSkeleton count={6} />
      ) : loadError ? (
        <DataState kind="error" title="No se pudieron cargar los paquetes" description={loadError} actionLabel="Reintentar" onAction={load} />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={<Package size={32} />}
          title="Sin paquetes"
          description="Crea tu primer paquete turistico."
          action={
            <button onClick={() => setShowForm(true)} className="inline-flex items-center gap-1.5 bg-blue-600 text-white px-4 py-2.5 rounded-xl text-sm font-medium hover:bg-blue-700 shadow-sm">
              <Plus size={14}/> Nuevo Paquete
            </button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map(p => (
            <div key={p.id} className={`bg-white rounded-2xl shadow-sm ring-1 ring-gray-100 overflow-hidden group transition-all hover:shadow-md ${!p.is_active ? "opacity-60" : ""}`}>
              <div className={`h-1.5 ${p.package_type === "PREDEFINED" ? "bg-gradient-to-r from-blue-500 to-indigo-500" : "bg-gradient-to-r from-emerald-500 to-teal-500"}`}/>
              <div className="p-5">
                {editId === p.id ? (
                  <div className="space-y-2.5">
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Nombre</label>
                      <input defaultValue={p.name} onChange={e => setEditData((d: any) => ({...d, name: e.target.value}))}
                        className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:border-blue-500"/>
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Precio (S/.)</label>
                      <input type="number" defaultValue={p.base_price} onChange={e => setEditData((d: any) => ({...d, base_price: Number(e.target.value)}))}
                        className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:border-blue-500"/>
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Duracion (dias)</label>
                      <input type="number" defaultValue={p.duration_days} onChange={e => setEditData((d: any) => ({...d, duration_days: Number(e.target.value)}))}
                        className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:border-blue-500"/>
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Descripcion</label>
                      <input defaultValue={p.description || ""} onChange={e => setEditData((d: any) => ({...d, description: e.target.value}))}
                        className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:border-blue-500"/>
                    </div>
                    <div className="flex gap-2 pt-1">
                      <button onClick={() => saveEdit(p.id)} className="flex-1 flex items-center justify-center gap-1 bg-emerald-500 text-white py-2 rounded-xl text-sm hover:bg-emerald-600 transition-colors"><Check size={13}/> Guardar</button>
                      <button onClick={() => setEditId(null)} className="flex-1 flex items-center justify-center gap-1 bg-gray-100 py-2 rounded-xl text-sm hover:bg-gray-200 transition-colors"><X size={13}/> Cancelar</button>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="flex items-start justify-between gap-2 mb-3">
                      <h2 className="font-semibold text-gray-800 text-sm leading-tight">{p.name}</h2>
                      <StatusBadge variant={p.is_active ? "success" : "neutral"}>
                        {p.is_active ? "Activo" : "Inactivo"}
                      </StatusBadge>
                    </div>
                    <div className="space-y-1.5 text-xs text-gray-500 mb-4">
                      <div className="flex items-center gap-1.5"><MapPin size={12}/>{p.destination}</div>
                      {p.duration_days > 0 && <div className="flex items-center gap-1.5"><Clock size={12}/>{p.duration_days} dias</div>}
                    </div>
                    <div className="flex items-center justify-between">
                      {parseFloat(p.base_price) > 0
                        ? <p className="text-lg font-bold text-gray-900">{money(p.base_price)}</p>
                        : <p className="text-sm text-emerald-600 font-medium">A cotizar</p>}
                      <div className="flex gap-1">
                        <button
                          onClick={() => { setEditId(p.id); setEditData({ name: p.name, base_price: p.base_price, duration_days: p.duration_days, description: p.description }); }}
                          className="p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                          aria-label={`Editar ${p.name}`}
                        >
                          <Pencil size={13}/>
                        </button>
                        <button
                          onClick={() => deactivate(p.id, p.name, p.is_active)}
                          className="p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                          aria-label={`${p.is_active ? "Desactivar" : "Activar"} ${p.name}`}
                        >
                          <Trash2 size={13}/>
                        </button>
                        <button
                          onClick={() => window.location.href="/quotations"}
                          className="flex items-center gap-1 bg-blue-600 text-white px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-blue-700 transition-colors"
                        >
                          Cotizar<ChevronRight size={11}/>
                        </button>
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
