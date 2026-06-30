"use client";
import { useState, useCallback } from "react";

interface ToastState {
  msg: string;
  ok: boolean;
}

export function useToast() {
  const [toast, setToast] = useState<ToastState | null>(null);

  const notify = useCallback((msg: string, ok = true) => {
    setToast({ msg, ok });
    setTimeout(() => setToast(null), 3500);
  }, []);

  return { toast, notify };
}
