import { cn } from "@/lib/utils";

const STATUS_CLASS: Record<string, string> = {
  scored: "text-success",
  joined: "text-success",
  active: "text-success",
  approved: "text-success",
  APPROVED: "text-success",
  EXPORTED: "text-success",
  PAID: "text-success",
  PAYOUT_READY: "text-warning",
  EARNING: "text-warning",
  UNDER_REVIEW: "text-warning",
  REVIEW_REQUIRED: "text-warning",
  rejected: "text-destructive",
  REJECTED: "text-destructive",
  FAILED: "text-destructive",
  draft: "text-muted-foreground",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border border-border px-2 py-0.5 text-xs font-medium",
        STATUS_CLASS[status] || "text-muted-foreground"
      )}
    >
      {status}
    </span>
  );
}
