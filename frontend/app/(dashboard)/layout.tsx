"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, Package, FileText, BookOpen,
  DollarSign, Activity, LogOut,
} from "lucide-react";

const NAV = [
  { href: "/",             label: "Dashboard",    icon: LayoutDashboard },
  { href: "/packages",     label: "Paquetes",     icon: Package },
  { href: "/quotations",   label: "Cotizaciones", icon: FileText },
  { href: "/reservations", label: "Reservas",     icon: BookOpen },
  { href: "/finance",      label: "Finanzas",     icon: DollarSign },
  { href: "/monitoring",   label: "Monitoreo",    icon: Activity },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

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
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                  active
                    ? "bg-blue-50 text-blue-700 font-medium"
                    : "text-gray-600 hover:bg-gray-50"
                }`}
              >
                <Icon size={18} />
                {label}
              </Link>
            );
          })}
        </nav>
        <div className="p-4 border-t border-gray-100">
          <button className="flex items-center gap-2 text-sm text-gray-500 hover:text-red-600 w-full px-3 py-2 rounded-lg hover:bg-red-50 transition-colors">
            <LogOut size={16} />
            Cerrar sesión
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-y-auto bg-gray-50">{children}</main>
    </div>
  );
}
