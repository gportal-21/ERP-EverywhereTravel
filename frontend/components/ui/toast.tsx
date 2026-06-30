"use client";
import { CheckCircle, XCircle } from "lucide-react";

interface ToastProps {
  toast: { msg: string; ok: boolean } | null;
}

export function Toast({ toast }: ToastProps) {
  if (!toast) return null;

  return (
    <div
      className={`fixed top-4 right-4 z-50 max-w-sm px-4 py-3 rounded-xl shadow-lg text-sm font-medium flex items-center gap-2.5 animate-slide-in ${
        toast.ok
          ? "bg-emerald-600 text-white"
          : "bg-red-600 text-white"
      }`}
    >
      {toast.ok ? <CheckCircle size={16} /> : <XCircle size={16} />}
      <span className="leading-snug">{toast.msg}</span>
    </div>
  );
}
