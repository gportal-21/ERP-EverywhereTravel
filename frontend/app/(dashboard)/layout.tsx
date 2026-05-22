"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard, Package, FileText, BookOpen,
  DollarSign, Activity, LogOut, User, Shield, ChevronRight,
} from "lucide-react";
import AuthGuard from "@/components/auth-guard";
import { useAuthStore } from "@/lib/auth-store";

const NAV = [
  { href: "/",             label: "Dashboard",    icon: LayoutDashboard },
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

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  const roleLabel = user?.role ? ROLE_LABELS[user.role] || user.role : "";

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside className="w-64 bg-white border-r border-gray-200 flex flex-col">
        <div className="p-6 border-b border-gray-100">
          <h1 className="font-bold text-lg text-blue-700">Everywhere Travel</h1>
          <p className="text-xs text-gray-400 mt-0.5">Sistema Multiagente Interno</p>
        </div>
        <nav className="flex-1 p-4 space-y-1">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all duration-150 group ${
                  active
                    ? "bg-blue-50 text-blue-700 font-medium shadow-sm"
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
        <div className="p-4 border-t border-gray-100 space-y-3">
          {user && (
            <div className="flex items-center gap-3 px-3 py-2">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shadow-sm">
                <User size={14} className="text-white" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-800 truncate">{user.username}</p>
                <div className="flex items-center gap-1">
                  <Shield size={10} className="text-blue-500" />
                  <p className="text-[11px] text-gray-400 truncate">{roleLabel}</p>
                </div>
              </div>
            </div>
          )}
          <button
            id="logout-btn"
            onClick={handleLogout}
            className="flex items-center gap-2 text-sm text-gray-500 hover:text-red-600 w-full px-3 py-2.5 rounded-lg hover:bg-red-50 transition-all duration-150 group"
          >
            <LogOut size={16} className="group-hover:text-red-500 transition-colors" />
            Cerrar sesión
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-y-auto bg-gray-50">{children}</main>
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
