"use client";
import { useEffect, useState } from "react";
import { Package } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function authHeaders(): HeadersInit {
  const token = typeof window !== "undefined" ? localStorage.getItem("et_token") : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export default function PackagesPage() {
  const [packages, setPackages] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API}/api/v1/packages/`, { headers: authHeaders() })
      .then((r) => r.json())
      .then((d) => { setPackages(d.packages || []); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-xl font-bold flex items-center gap-2">
        <Package size={22} /> Paquetes Turísticos
      </h1>
      {loading ? (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600" />
        </div>
      ) : packages.length === 0 ? (
        <p className="text-gray-400 text-center py-12">Sin paquetes disponibles</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {packages.map((pkg) => (
            <div key={pkg.id} className="bg-white rounded-xl shadow p-5 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs px-2 py-0.5 bg-blue-100 text-blue-700 rounded-full">
                  {pkg.package_type}
                </span>
                <span className="font-bold text-gray-900">
                  S/. {parseFloat(pkg.base_price).toFixed(2)}
                </span>
              </div>
              <h2 className="font-semibold text-gray-800">{pkg.name}</h2>
              <p className="text-sm text-gray-500">{pkg.destination}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
