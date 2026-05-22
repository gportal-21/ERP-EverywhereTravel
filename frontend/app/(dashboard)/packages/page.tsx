"use client";
import { useEffect, useState } from "react";
import { Package, Plus, Pencil, Trash2, Check, X, Search, MapPin, Clock, ChevronRight } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const authH = (): Record<string, string> => {
  const t = typeof window !== "undefined" ? localStorage.getItem("et_token") : null;
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (t) h["Authorization"] = `Bearer ${t}`;
  return h;
};

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
  const [toast, setToast]       = useState<{ msg: string; ok: boolean } | null>(null);
  const [showInactive, setShowInactive] = useState(false);

  const notify = (msg: string, ok = true) => { setToast({ msg, ok }); setTimeout(() => setToast(null), 3000); };

  const load = async () => {
    setLoading(true);
    const r = await fetch(`${API}/api/v1/packages/?include_inactive=${showInactive}`, { headers: authH() }).catch(() => null);
    if (r?.ok) setPackages((await r.json()).packages || []);
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
    const r = await fetch(`${API}/api/v1/packages/`, { method: "POST", headers: authH(), body: JSON.stringify(payload) }).catch(() => null);
    if (r?.ok) { notify("Paquete creado"); setForm({ ...BLANK }); setShowForm(false); load(); }
    else notify("Error al crear paquete", false);
    setSaving(false);
  };

  const saveEdit = async (id: string) => {
    const r = await fetch(`${API}/api/v1/packages/${id}`, { method: "PATCH", headers: authH(), body: JSON.stringify(editData) }).catch(() => null);
    if (r?.ok) { notify("Paquete actualizado"); setEditId(null); load(); }
    else notify("Error al actualizar", false);
  };

  const deactivate = async (id: string, name: string, active: boolean) => {
    const action = active ? "desactivar" : "activar";
    if (!confirm(`¿${action.charAt(0).toUpperCase() + action.slice(1)} "${name}"?`)) return;
    const r = await fetch(`${API}/api/v1/packages/${id}`, { method: "PATCH", headers: authH(), body: JSON.stringify({ is_active: !active }) }).catch(() => null);
    if (r?.ok) { notify(`Paquete ${action}do`); load(); }
    else notify(`Error al ${action}`, false);
  };

  const filtered = packages.filter(p => !search || p.name.toLowerCase().includes(search.toLowerCase()) || p.destination.toLowerCase().includes(search.toLowerCase()));

  const Field = ({ label, value, onChange, type = "text" }: any) => (
    <div>
      <label className="block text-xs font-medium text-gray-600 mb-1">{label}</label>
      <input type={type} defaultValue={value} onChange={e => onChange(e.target.value)}
        className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"/>
    </div>
  );

  return (
    <div className="p-6 space-y-5">
      {toast && (
        <div className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-xl shadow-lg text-sm font-medium flex items-center gap-2 ${toast.ok ? "bg-green-600 text-white" : "bg-red-600 text-white"}`}>
          {toast.ok ? <Check size={15}/> : <X size={15}/>}{toast.msg}
        </div>
      )}

      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold flex items-center gap-2"><Package size={22}/> Paquetes</h1>
        <div className="flex gap-2 items-center">
          <label className="flex items-center gap-1.5 text-sm text-gray-500 cursor-pointer">
            <input type="checkbox" checked={showInactive} onChange={e => setShowInactive(e.target.checked)} className="rounded"/>
            Ver inactivos
          </label>
          <button onClick={() => setShowForm(s => !s)}
            className="flex items-center gap-1.5 bg-blue-600 text-white px-3.5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors">
            <Plus size={14}/> Nuevo
          </button>
        </div>
      </div>

      <div className="relative">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"/>
        <input type="text" placeholder="Buscar paquete o destino…" value={search} onChange={e => setSearch(e.target.value)}
          className="w-full pl-9 pr-3 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"/>
      </div>

      {showForm && (
        <div className="bg-blue-50 border border-blue-100 rounded-xl p-5">
          <h2 className="font-semibold text-gray-800 mb-4">Nuevo Paquete</h2>
          <form onSubmit={saveNew} className="grid grid-cols-2 gap-3">
            {[
              { label: "Nombre *", key: "name", col: 2 },
              { label: "Destino *", key: "destination", col: 1 },
              { label: "Tipo", key: "package_type", col: 1, select: ["PREDEFINED", "CUSTOM"] },
              { label: "Precio base (S/.)", key: "base_price", col: 1, type: "number" },
              { label: "Duración (días)", key: "duration_days", col: 1, type: "number" },
              { label: "Descripción", key: "description", col: 2 },
              { label: "Incluye (separado por comas)", key: "includes", col: 2 },
              { label: "No incluye (separado por comas)", key: "excludes", col: 2 },
            ].map(({ label, key, col, type, select }: any) => (
              <div key={key} className={col === 2 ? "col-span-2" : ""}>
                <label className="block text-xs font-medium text-gray-600 mb-1">{label}</label>
                {select ? (
                  <select value={(form as any)[key]} onChange={e => setForm({...form, [key]: e.target.value})}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
                    {select.map((o: string) => <option key={o}>{o}</option>)}
                  </select>
                ) : (
                  <input type={type || "text"} value={(form as any)[key]} required={label.includes("*")}
                    onChange={e => setForm({...form, [key]: e.target.value})}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"/>
                )}
              </div>
            ))}
            <div className="col-span-2 flex gap-2 justify-end pt-1">
              <button type="button" onClick={() => setShowForm(false)} className="px-4 py-2 border rounded-lg text-sm text-gray-600 hover:bg-gray-50">Cancelar</button>
              <button type="submit" disabled={saving} className="px-5 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50">
                {saving ? "Guardando…" : "Crear Paquete"}
              </button>
            </div>
          </form>
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-12"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"/></div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map(p => (
            <div key={p.id} className={`bg-white rounded-xl shadow overflow-hidden group ${!p.is_active ? "opacity-60" : ""}`}>
              <div className={`h-1.5 ${p.package_type === "PREDEFINED" ? "bg-gradient-to-r from-blue-500 to-indigo-500" : "bg-gradient-to-r from-emerald-500 to-teal-500"}`}/>
              <div className="p-5">
                {editId === p.id ? (
                  <div className="space-y-2">
                    <Field label="Nombre" value={p.name} onChange={(v: string) => setEditData((d: any) => ({...d, name: v}))}/>
                    <Field label="Precio (S/.)" value={p.base_price} type="number" onChange={(v: string) => setEditData((d: any) => ({...d, base_price: Number(v)}))}/>
                    <Field label="Duración (días)" value={p.duration_days} type="number" onChange={(v: string) => setEditData((d: any) => ({...d, duration_days: Number(v)}))}/>
                    <Field label="Descripción" value={p.description || ""} onChange={(v: string) => setEditData((d: any) => ({...d, description: v}))}/>
                    <div className="flex gap-2 pt-1">
                      <button onClick={() => saveEdit(p.id)} className="flex-1 flex items-center justify-center gap-1 bg-green-500 text-white py-1.5 rounded-lg text-sm hover:bg-green-600"><Check size={13}/> Guardar</button>
                      <button onClick={() => setEditId(null)} className="flex-1 flex items-center justify-center gap-1 bg-gray-100 py-1.5 rounded-lg text-sm hover:bg-gray-200"><X size={13}/> Cancelar</button>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="flex items-start justify-between gap-2 mb-3">
                      <h2 className="font-semibold text-gray-800 text-sm leading-tight">{p.name}</h2>
                      <span className={`text-[10px] px-2 py-0.5 rounded-full font-semibold flex-shrink-0 ${p.is_active ? "bg-green-50 text-green-600" : "bg-gray-100 text-gray-500"}`}>
                        {p.is_active ? "Activo" : "Inactivo"}
                      </span>
                    </div>
                    <div className="space-y-1 text-xs text-gray-500 mb-4">
                      <div className="flex items-center gap-1.5"><MapPin size={11}/>{p.destination}</div>
                      {p.duration_days > 0 && <div className="flex items-center gap-1.5"><Clock size={11}/>{p.duration_days} días</div>}
                    </div>
                    <div className="flex items-center justify-between">
                      {parseFloat(p.base_price) > 0
                        ? <p className="text-lg font-bold text-gray-900">S/. {parseFloat(p.base_price).toLocaleString("es-PE")}</p>
                        : <p className="text-sm text-emerald-600 font-medium">A cotizar</p>}
                      <div className="flex gap-1">
                        <button onClick={() => { setEditId(p.id); setEditData({ name: p.name, base_price: p.base_price, duration_days: p.duration_days, description: p.description }); }}
                          className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"><Pencil size={13}/></button>
                        <button onClick={() => deactivate(p.id, p.name, p.is_active)}
                          className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"><Trash2 size={13}/></button>
                        <button onClick={() => window.location.href=`/quotations`}
                          className="flex items-center gap-1 bg-blue-600 text-white px-2.5 py-1.5 rounded-lg text-xs font-medium hover:bg-blue-700 transition-colors">
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
