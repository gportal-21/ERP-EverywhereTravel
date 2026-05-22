"use client";
import { useEffect, useState } from "react";
import { Users, Plus, RefreshCw, Mail, Phone, Pencil, Trash2, Check, X, Search } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const authH = (): Record<string, string> => {
  const t = typeof window !== "undefined" ? localStorage.getItem("et_token") : null;
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (t) h["Authorization"] = `Bearer ${t}`;
  return h;
};

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
  const [toast, setToast]       = useState<{ msg: string; ok: boolean } | null>(null);

  const notify = (msg: string, ok = true) => { setToast({ msg, ok }); setTimeout(() => setToast(null), 3000); };

  const load = async (q = search) => {
    setLoading(true);
    const params = q ? `?search=${encodeURIComponent(q)}` : "";
    const r = await fetch(`${API}/api/v1/clients/${params}`, { headers: authH() }).catch(() => null);
    if (r?.ok) setClients((await r.json()).clients || []);
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const save = async (e: React.FormEvent) => {
    e.preventDefault(); setSaving(true);
    const r = await fetch(`${API}/api/v1/clients/`, { method: "POST", headers: authH(), body: JSON.stringify(form) }).catch(() => null);
    if (r?.ok) { notify("Cliente creado"); setForm({ ...BLANK }); setShowForm(false); load(); }
    else notify("Error al crear cliente", false);
    setSaving(false);
  };

  const saveEdit = async (id: string) => {
    const r = await fetch(`${API}/api/v1/clients/${id}`, { method: "PATCH", headers: authH(), body: JSON.stringify(editData) }).catch(() => null);
    if (r?.ok) { notify("Cliente actualizado"); setEditId(null); load(); }
    else notify("Error al actualizar", false);
  };

  const del = async (id: string, name: string) => {
    if (!confirm(`¿Eliminar a "${name}"? Esta acción no se puede deshacer.`)) return;
    const r = await fetch(`${API}/api/v1/clients/${id}`, { method: "DELETE", headers: authH() }).catch(() => null);
    if (r?.ok) { notify("Cliente eliminado"); load(); }
    else notify("No se puede eliminar (tiene reservas asociadas)", false);
  };

  const filtered = clients.filter(c =>
    !search || c.full_name.toLowerCase().includes(search.toLowerCase()) || c.email.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="p-6 space-y-5">
      {toast && (
        <div className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-xl shadow-lg text-sm font-medium flex items-center gap-2 transition-all ${toast.ok ? "bg-green-600 text-white" : "bg-red-600 text-white"}`}>
          {toast.ok ? <Check size={15}/> : <X size={15}/>}{toast.msg}
        </div>
      )}

      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold flex items-center gap-2"><Users size={22}/> Clientes</h1>
        <div className="flex gap-2">
          <button onClick={() => load()} className="p-2 hover:bg-white rounded-lg border transition-colors">
            <RefreshCw size={14} className={loading ? "animate-spin text-blue-500" : "text-gray-400"}/>
          </button>
          <button onClick={() => { setShowForm(s => !s); setForm({ ...BLANK }); }}
            className="flex items-center gap-1.5 bg-blue-600 text-white px-3.5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors">
            <Plus size={14}/> Nuevo
          </button>
        </div>
      </div>

      {/* Búsqueda */}
      <div className="relative">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"/>
        <input type="text" placeholder="Buscar por nombre, email o documento…" value={search}
          onChange={e => { setSearch(e.target.value); load(e.target.value); }}
          className="w-full pl-9 pr-3 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"/>
      </div>

      {/* Formulario nuevo cliente */}
      {showForm && (
        <div className="bg-blue-50 border border-blue-100 rounded-xl p-5">
          <h2 className="font-semibold text-gray-800 mb-4">Nuevo Cliente</h2>
          <form onSubmit={save} className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <label className="block text-xs font-medium text-gray-600 mb-1">Nombre completo *</label>
              <input required type="text" value={form.full_name} onChange={e => setForm({...form, full_name: e.target.value})}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"/>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Email *</label>
              <input required type="email" value={form.email} onChange={e => setForm({...form, email: e.target.value})}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"/>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Teléfono</label>
              <input type="tel" value={form.phone} onChange={e => setForm({...form, phone: e.target.value})}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"/>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Tipo Doc.</label>
              <select value={form.document_type} onChange={e => setForm({...form, document_type: e.target.value})}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
                <option>DNI</option><option>PASAPORTE</option><option>CE</option><option>RUC</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">N° Documento</label>
              <input type="text" value={form.document_number} onChange={e => setForm({...form, document_number: e.target.value})}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"/>
            </div>
            <div className="col-span-2 flex gap-2 justify-end pt-1">
              <button type="button" onClick={() => setShowForm(false)} className="px-4 py-2 border rounded-lg text-sm text-gray-600 hover:bg-gray-50">Cancelar</button>
              <button type="submit" disabled={saving} className="px-5 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50">
                {saving ? "Guardando…" : "Guardar"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Lista */}
      <div className="bg-white rounded-xl shadow overflow-hidden">
        <div className="px-5 py-3 border-b bg-gray-50 flex items-center justify-between">
          <span className="text-sm text-gray-500">{filtered.length} clientes</span>
        </div>
        {loading ? (
          <div className="flex justify-center py-12"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"/></div>
        ) : filtered.length === 0 ? (
          <div className="text-center py-12 text-gray-400"><Users size={36} className="mx-auto mb-2 opacity-30"/><p className="text-sm">Sin clientes</p></div>
        ) : (
          <div className="divide-y divide-gray-50">
            {filtered.map(c => (
              <div key={c.id} className="flex items-center gap-4 px-5 py-3.5 hover:bg-gray-50 group transition-colors">
                <div className="w-9 h-9 rounded-full bg-gradient-to-br from-blue-400 to-indigo-500 flex items-center justify-center text-white text-sm font-semibold flex-shrink-0">
                  {c.full_name.charAt(0).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  {editId === c.id ? (
                    <div className="flex gap-2 items-center flex-wrap">
                      <input defaultValue={c.full_name} onChange={e => setEditData(d => ({...d, full_name: e.target.value}))}
                        className="border rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 w-40"/>
                      <input defaultValue={c.phone || ""} onChange={e => setEditData(d => ({...d, phone: e.target.value}))}
                        placeholder="Teléfono" className="border rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 w-32"/>
                      <button onClick={() => saveEdit(c.id)} className="p-1.5 bg-green-500 text-white rounded hover:bg-green-600"><Check size={13}/></button>
                      <button onClick={() => setEditId(null)} className="p-1.5 bg-gray-200 rounded hover:bg-gray-300"><X size={13}/></button>
                    </div>
                  ) : (
                    <>
                      <p className="text-sm font-medium text-gray-800 truncate">{c.full_name}</p>
                      <div className="flex items-center gap-3 mt-0.5">
                        <span className="flex items-center gap-1 text-xs text-gray-400"><Mail size={10}/>{c.email}</span>
                        {c.phone && <span className="flex items-center gap-1 text-xs text-gray-400"><Phone size={10}/>{c.phone}</span>}
                        {c.document_number && <span className="text-xs text-gray-400">{c.document_type}: {c.document_number}</span>}
                      </div>
                    </>
                  )}
                </div>
                {editId !== c.id && (
                  <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button onClick={() => { setEditId(c.id); setEditData({ full_name: c.full_name, phone: c.phone }); }}
                      className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors">
                      <Pencil size={14}/>
                    </button>
                    <button onClick={() => del(c.id, c.full_name)}
                      className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors">
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
