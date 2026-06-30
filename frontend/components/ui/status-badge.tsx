const VARIANTS = {
  success: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  warning: "bg-amber-50 text-amber-700 ring-amber-600/20",
  error: "bg-red-50 text-red-700 ring-red-600/20",
  info: "bg-blue-50 text-blue-700 ring-blue-600/20",
  neutral: "bg-gray-100 text-gray-600 ring-gray-500/20",
  purple: "bg-purple-50 text-purple-700 ring-purple-600/20",
} as const;

interface StatusBadgeProps {
  variant: keyof typeof VARIANTS;
  children: React.ReactNode;
  icon?: React.ReactNode;
}

export function StatusBadge({ variant, children, icon }: StatusBadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full ring-1 ring-inset ${VARIANTS[variant]}`}
    >
      {icon}
      {children}
    </span>
  );
}
