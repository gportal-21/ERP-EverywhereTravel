"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  LayoutDashboard, Package, FileText, BookOpen,
  DollarSign, Activity, LogOut, User, Shield,
  ChevronRight, Users, Menu, X, Bell, CheckCircle,
} from "lucide-react";
import AuthGuard from "@/components/auth-guard";
import { useAuthStore } from "@/lib/auth-store";
import { WS } from "@/lib/fetch-api";

const NAV = [
  { href: "/",             label: "Dashboard",    icon: LayoutDashboard },
  { href: "/clients",      label: "Clientes",     icon: Users },
  { href: "/packages",     label: "Paquetes",     icon: Package },
  { href: "/quotations",   label: "Cotizaciones", icon: FileText },
  { href: "/reservations", label: "Reservas",     icon: BookOpen },
  { href: "/finance",      label: "Finanzas",     icon: DollarSign },
  { href: "/monitoring",   label: "Monitoreo",    icon: Activity },
];

const ROLE_LABELS: Record<string, string> = {
  admin: "Administrador",
  sales_agent: "Agente de Ventas",
  finance_agent: "Agente Financiero",
};

function DashboardContent({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuthStore();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [notifications, setNotifications] = useState<Array<{ id: number; type: string; message: string }>>([]);

  useEffect(() => {
    let ws: WebSocket | null = null;
    try {
      ws = new WebSocket(`${WS}/ws/system:alerts`);
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          const id = Date.now();
          setNotifications(prev => [
            { id, type: data.type || data.event || "Notification", message: data.message || data.type || "Evento completado" },
            ...prev,
          ].slice(0, 4));
          window.setTimeout(() => {
            setNotifications(prev => prev.filter(item => item.id !== id));
          }, 7000);
        } catch {}
      };
    } catch {}
    return () => { try { ws?.close(); } catch {} };
  }, []);

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  const roleLabel = user?.role ? ROLE_LABELS[user.role] || user.role : "";

  const currentPage = NAV.find(n => n.href === pathname);

  return (
    <div className="flex h-screen overflow-hidden">
      <div className="fixed right-4 top-4 z-[80] space-y-2 w-[min(360px,calc(100vw-2rem))]">
        {notifications.map(item => (
          <div key={item.id} className="bg-white border border-blue-100 shadow-lg rounded-xl p-3 flex items-start gap-2 animate-slide-in">
            <div className="w-8 h-8 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center flex-shrink-0">
              {item.type?.toLowerCase().includes("ready") ? <CheckCircle size={16} /> : <Bell size={16} />}
            </div>
            <div className="min-w-0">
              <p className="text-xs font-semibold text-gray-800">{item.type}</p>
              <p className="text-xs text-gray-600 leading-relaxed">{item.message}</p>
            </div>
          </div>
        ))}
      </div>
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-gray-900/50 z-40 lg:hidden animate-fade-in"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`
          fixed inset-y-0 left-0 z-50 w-72 bg-white border-r border-gray-200 flex flex-col
          transform transition-transform duration-300 ease-in-out
          lg:relative lg:translate-x-0 lg:w-64
          ${sidebarOpen ? "translate-x-0 shadow-2xl" : "-translate-x-full"}
        `}
      >
        <div className="p-6 border-b border-gray-100 flex items-center justify-between">
          <div>
            <h1 className="font-bold text-lg text-blue-700">Everywhere Travel</h1>
            <p className="text-xs text-gray-400 mt-0.5">Sistema Multiagente</p>
          </div>
          <button
            onClick={() => setSidebarOpen(false)}
            className="lg:hidden p-1.5 hover:bg-gray-100 rounded-lg transition-colors"
            aria-label="Cerrar menu"
          >
            <X size={18} className="text-gray-500" />
          </button>
        </div>

        <nav className="flex-1 p-3 space-y-0.5 overflow-y-auto scrollbar-thin">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                onClick={() => setSidebarOpen(false)}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-all duration-150 group ${
                  active
                    ? "bg-blue-50 text-blue-700 font-semibold"
                    : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
                }`}
              >
                <Icon size={18} className={active ? "text-blue-600" : "text-gray-400 group-hover:text-gray-600"} />
                <span className="flex-1">{label}</span>
                {active && <ChevronRight size={14} className="text-blue-400" />}
              </Link>
            );
          })}
        </nav>

        {/* User info + Logout */}
        <div className="p-3 border-t border-gray-100 space-y-1">
          {user && (
            <div className="flex items-center gap-3 px-3 py-2.5 rounded-xl bg-gray-50">
              <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shadow-sm flex-shrink-0">
                <User size={15} className="text-white" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-gray-800 truncate">{user.username}</p>
                <div className="flex items-center gap-1">
                  <Shield size={10} className="text-blue-500" />
                  <p className="text-xs text-gray-500 truncate">{roleLabel}</p>
                </div>
              </div>
            </div>
          )}
          <button
            id="logout-btn"
            onClick={handleLogout}
            className="flex items-center gap-2 text-sm text-gray-500 hover:text-red-600 w-full px-3 py-2.5 rounded-xl hover:bg-red-50 transition-all duration-150 group"
          >
            <LogOut size={16} className="group-hover:text-red-500 transition-colors" />
            Cerrar sesion
          </button>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Mobile top bar */}
        <header className="lg:hidden flex items-center gap-3 px-4 py-3 bg-white border-b border-gray-200 flex-shrink-0">
          <button
            onClick={() => setSidebarOpen(true)}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
            aria-label="Abrir menu"
          >
            <Menu size={20} className="text-gray-700" />
          </button>
          <div className="flex-1 min-w-0">
            <span className="font-bold text-blue-700 text-sm">Everywhere Travel</span>
            {currentPage && (
              <p className="text-xs text-gray-400 truncate">{currentPage.label}</p>
            )}
          </div>
          {user && (
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center flex-shrink-0">
              <User size={13} className="text-white" />
            </div>
          )}
        </header>

        <main className="flex-1 overflow-y-auto bg-gray-50 scrollbar-thin">{children}</main>
      </div>
    </div>
  );
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <DashboardContent>{children}</DashboardContent>
    </AuthGuard>
  );
}
