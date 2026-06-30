"use client";
import { useEffect, useState } from "react";
import { Users, Plus, RefreshCw, Mail, Phone, Pencil, Trash2, Check, X, Search } from "lucide-react";
import { API, authHeaders, fetchJson } from "@/lib/fetch-api";
import { useToast } from "@/hooks/use-toast";
import { Toast } from "@/components/ui/toast";
import { PageHeader } from "@/components/ui/page-header";
import { EmptyState } from "@/components/ui/empty-state";
import { TableSkeleton } from "@/components/ui/skeleton";
import { DataState } from "@/components/ui/data-state";

interface Client { id: string; full_name: string; email: string; phone?: string; document_type?: string; document_number?: string }

const BLANK = { full_name: "", email: "", phone: "", document_type: "DNI", document_number: "" };

export default function ClientsPage() {
  const [clients, setClients] = useState<Client[]>([]);
  const [loading, setLoading]   = useState(true);
  const [search, setSearch]     = useState("");
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving]     = useState(false);
  const [form, setForm]         = useState({ ...BLANK });
  const [editId, setEditId]     = useState<string | null>(null);
  const [editData, setEditData] = useState<Partial<Client>>({});
  const [loadError, setLoadError] = useState("");
  const { toast, notify } = useToast();

  const load = async (q = search) => {
    setLoading(true);
    setLoadError("");
    const params = q ? `?search=${encodeURIComponent(q)}` : "";
    const { data, error } = await fetchJson<{ clients: Client[] }>(`${API}/api/v1/clients/${params}`, { headers: authHeaders() });
    if (data) setClients(Array.isArray(data.clients) ? data.clients : []);
    if (error) setLoadError(error);
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const save = async (e: React.FormEvent) => {
    e.preventDefault(); setSaving(true);
    const { error } = await fetchJson(`${API}/api/v1/clients/`, { method: "POST", headers: authHeaders(), body: JSON.stringify(form) });
    if (!error) { notify("Cliente creado"); setForm({ ...BLANK }); setShowForm(false); load(); }
    else notify(error, false);
    setSaving(false);
  };

  const saveEdit = async (id: string) => {
    const { error } = await fetchJson(`${API}/api/v1/clients/${id}`, { method: "PATCH", headers: authHeaders(), body: JSON.stringify(editData) });
    if (!error) { notify("Cliente actualizado"); setEditId(null); load(); }
    else notify(error, false);
  };

  const del = async (id: string, name: string) => {
    if (!confirm(`Eliminar a "${name}"? Esta accion no se puede deshacer.`)) return;
    const { error } = await fetchJson(`${API}/api/v1/clients/${id}`, { method: "DELETE", headers: authHeaders() });
    if (!error) { notify("Cliente eliminado"); load(); }
    else notify(error, false);
  };

  const filtered = clients.filter(c =>
    !search || c.full_name.toLowerCase().includes(search.toLowerCase()) || c.email.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="p-4 sm:p-6 space-y-5">
      <Toast toast={toast} />

      <PageHeader
        icon={<Users size={20} />}
        title="Clientes"
        actions={
          <div className="flex gap-2">
            <button
              onClick={() => load()}
              className="p-2.5 hover:bg-white rounded-xl border border-gray-200 transition-colors"
              aria-label="Refrescar lista"
            >
              <RefreshCw size={14} className={loading ? "animate-spin text-blue-500" : "text-gray-400"}/>
            </button>
            <button
              onClick={() => { setShowForm(s => !s); setForm({ ...BLANK }); }}
              className="flex items-center gap-1.5 bg-blue-600 text-white px-4 py-2.5 rounded-xl text-sm font-medium hover:bg-blue-700 transition-colors shadow-sm"
            >
              <Plus size={14}/> Nuevo
            </button>
          </div>
        }
      />

      {/* Search */}
      <div className="relative">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"/>
        <input
          type="text"
          placeholder="Buscar por nombre, email o documento..."
          value={search}
          onChange={e => { setSearch(e.target.value); load(e.target.value); }}
          className="w-full pl-10 pr-4 py-2.5 bg-white border border-gray-200 rounded-xl text-sm focus:border-blue-500 transition-colors"
        />
      </div>

      {/* New client form */}
      {showForm && (
        <div className="bg-blue-50/50 border border-blue-100 rounded-2xl p-5 sm:p-6 animate-fade-in">
          <h2 className="font-semibold text-gray-800 mb-4 text-sm">Nuevo Cliente</h2>
          <form onSubmit={save} className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="sm:col-span-2">
              <label className="block text-xs font-medium text-gray-600 mb-1.5">Nombre completo *</label>
              <input required type="text" value={form.full_name} onChange={e => setForm({...form, full_name: e.target.value})}
                className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:border-blue-500 bg-white transition-colors"/>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1.5">Email *</label>
              <input required type="email" value={form.email} onChange={e => setForm({...form, email: e.target.value})}
                className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:border-blue-500 bg-white transition-colors"/>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1.5">Telefono</label>
              <input type="tel" value={form.phone} onChange={e => setForm({...form, phone: e.target.value})}
                className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:border-blue-500 bg-white transition-colors"/>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1.5">Tipo Doc.</label>
              <select value={form.document_type} onChange={e => setForm({...form, document_type: e.target.value})}
                className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:border-blue-500 bg-white transition-colors">
                <option>DNI</option><option>PASAPORTE</option><option>CE</option><option>RUC</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1.5">N. Documento</label>
              <input type="text" value={form.document_number} onChange={e => setForm({...form, document_number: e.target.value})}
                className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:border-blue-500 bg-white transition-colors"/>
            </div>
            <div className="sm:col-span-2 flex gap-2 justify-end pt-2">
              <button type="button" onClick={() => setShowForm(false)} className="px-4 py-2.5 border border-gray-200 rounded-xl text-sm text-gray-600 hover:bg-white transition-colors">Cancelar</button>
              <button type="submit" disabled={saving} className="px-5 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-sm">
                {saving ? "Guardando..." : "Guardar"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Client list */}
      <div className="bg-white rounded-2xl shadow-sm ring-1 ring-gray-100 overflow-hidden">
        <div className="px-5 py-3 border-b border-gray-100 bg-gray-50/50 flex items-center justify-between">
          <span className="text-sm text-gray-500">{filtered.length} clientes</span>
        </div>
        {loading ? (
          <TableSkeleton rows={5} />
        ) : loadError ? (
          <div className="p-5">
            <DataState kind="error" title="No se pudieron cargar los clientes" description={loadError} actionLabel="Reintentar" onAction={() => load()} />
          </div>
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={<Users size={32} />}
            title="Sin clientes"
            description="Agrega tu primer cliente usando el boton Nuevo."
          />
        ) : (
          <div className="divide-y divide-gray-50">
            {filtered.map(c => (
              <div key={c.id} className="flex items-center gap-4 px-5 py-3.5 hover:bg-gray-50/50 group transition-colors">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-400 to-indigo-500 flex items-center justify-center text-white text-sm font-bold flex-shrink-0 shadow-sm">
                  {c.full_name.charAt(0).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  {editId === c.id ? (
                    <div className="flex gap-2 items-center flex-wrap">
                      <input defaultValue={c.full_name} onChange={e => setEditData(d => ({...d, full_name: e.target.value}))}
                        className="border border-gray-200 rounded-lg px-2.5 py-1.5 text-sm focus:border-blue-500 w-40"/>
                      <input defaultValue={c.phone || ""} onChange={e => setEditData(d => ({...d, phone: e.target.value}))}
                        placeholder="Telefono" className="border border-gray-200 rounded-lg px-2.5 py-1.5 text-sm focus:border-blue-500 w-32"/>
                      <button onClick={() => saveEdit(c.id)} className="p-1.5 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 transition-colors" aria-label="Guardar"><Check size={13}/></button>
                      <button onClick={() => setEditId(null)} className="p-1.5 bg-gray-200 rounded-lg hover:bg-gray-300 transition-colors" aria-label="Cancelar"><X size={13}/></button>
                    </div>
                  ) : (
                    <>
                      <p className="text-sm font-semibold text-gray-800 truncate">{c.full_name}</p>
                      <div className="flex items-center gap-3 mt-0.5 flex-wrap">
                        <span className="flex items-center gap-1 text-xs text-gray-500"><Mail size={11}/>{c.email}</span>
                        {c.phone && <span className="flex items-center gap-1 text-xs text-gray-500"><Phone size={11}/>{c.phone}</span>}
                        {c.document_number && <span className="text-xs text-gray-500">{c.document_type}: {c.document_number}</span>}
                      </div>
                    </>
                  )}
                </div>
                {editId !== c.id && (
                  <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      onClick={() => { setEditId(c.id); setEditData({ full_name: c.full_name, phone: c.phone }); }}
                      className="p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                      aria-label={`Editar ${c.full_name}`}
                    >
                      <Pencil size={14}/>
                    </button>
                    <button
                      onClick={() => del(c.id, c.full_name)}
                      className="p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                      aria-label={`Eliminar ${c.full_name}`}
                    >
                      <Trash2 size={14}/>
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
