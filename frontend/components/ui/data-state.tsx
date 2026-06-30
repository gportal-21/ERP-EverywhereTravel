import { AlertTriangle, Database, RefreshCw } from "lucide-react";

interface DataStateProps {
  title: string;
  description?: string;
  kind?: "empty" | "error" | "placeholder";
  actionLabel?: string;
  onAction?: () => void;
}

export function DataState({
  title,
  description,
  kind = "empty",
  actionLabel,
  onAction,
}: DataStateProps) {
  const isError = kind === "error";
  const Icon = isError ? AlertTriangle : Database;
  const colors = isError
    ? "bg-red-50 text-red-600 border-red-100"
    : "bg-blue-50 text-blue-600 border-blue-100";

  return (
    <div className={`rounded-2xl border p-5 text-center ${colors}`}>
      <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-white/80">
        <Icon size={18} />
      </div>
      <p className="text-sm font-semibold">{title}</p>
      {description && <p className="mx-auto mt-1 max-w-sm text-xs opacity-80">{description}</p>}
      {onAction && actionLabel && (
        <button
          type="button"
          onClick={onAction}
          className="mt-4 inline-flex items-center gap-1.5 rounded-xl bg-white px-3 py-2 text-xs font-medium shadow-sm ring-1 ring-inset ring-black/5 hover:bg-gray-50"
        >
          <RefreshCw size={12} />
          {actionLabel}
        </button>
      )}
    </div>
  );
}
