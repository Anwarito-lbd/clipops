"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Bell,
  Clapperboard,
  FolderUp,
  LayoutDashboard,
  LineChart,
  ListOrdered,
  Package,
  ShieldAlert,
  Sparkles,
  Users,
  Wallet,
  Link2,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Home $1K", icon: LayoutDashboard },
  { href: "/operator", label: "Operator", icon: Sparkles },
  { href: "/accounts", label: "Accounts", icon: Users },
  { href: "/affiliates", label: "Affiliates", icon: Link2 },
  { href: "/campaigns", label: "Campaigns", icon: Clapperboard },
  { href: "/assets", label: "Assets", icon: FolderUp },
  { href: "/review", label: "Review", icon: ShieldAlert },
  { href: "/queue", label: "Posting queue", icon: ListOrdered },
  { href: "/exports", label: "Exports", icon: Package },
  { href: "/tracking", label: "Tracking", icon: LineChart },
  { href: "/payouts", label: "Payouts / Learn", icon: Wallet },
  { href: "/notifications", label: "Alerts", icon: Bell },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="flex h-screen w-56 shrink-0 flex-col border-r border-border bg-card">
      <div className="border-b border-border px-4 py-4">
        <div className="text-xl font-bold tracking-tight">ClipOps</div>
        <p className="mt-1 text-xs text-muted-foreground">
          Operator Mode · you confirm finals
        </p>
      </div>
      <nav className="flex flex-1 flex-col gap-0.5 overflow-auto p-2">
        {NAV.map((item) => {
          const Icon = item.icon;
          const active =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-accent text-accent-foreground font-medium"
                  : "text-muted-foreground hover:bg-accent/60 hover:text-foreground"
              )}
            >
              <Icon size={16} />
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="border-t border-border p-3 text-xs text-muted-foreground">
        ~85–90% automated · no posting bots
      </div>
    </aside>
  );
}
