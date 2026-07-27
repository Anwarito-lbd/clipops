"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/utils";

type N = {
  id: string;
  kind: string;
  title: string;
  body: string;
  action_url: string | null;
  action_label: string | null;
  read: boolean;
};

export default function NotificationsPage() {
  const [rows, setRows] = useState<N[]>([]);

  async function load() {
    setRows(await api("/api/operator/notifications"));
  }

  useEffect(() => {
    load().catch(() => undefined);
  }, []);

  async function markRead(id: string) {
    await api(`/api/operator/notifications/${id}/read`, {
      method: "POST",
      body: "{}",
    });
    await load();
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">Notifications</h1>
        <p className="text-sm text-muted-foreground">
          Approvals, revisions, payout-ready, submission-ready.
        </p>
      </div>
      <div className="space-y-2">
        {rows.map((n) => (
          <div
            key={n.id}
            className={`rounded-lg border border-border p-4 ${n.read ? "opacity-60" : "bg-card"}`}
          >
            <div className="text-sm font-semibold">{n.title}</div>
            <div className="text-xs text-muted-foreground">{n.body}</div>
            <div className="mt-2 flex gap-2">
              {n.action_url && (
                <a
                  className="rounded-md bg-primary px-2 py-1 text-xs font-medium text-primary-foreground"
                  href={n.action_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  {n.action_label || "Open"}
                </a>
              )}
              {!n.read && (
                <button
                  className="rounded-md border border-border px-2 py-1 text-xs"
                  onClick={() => markRead(n.id)}
                >
                  Mark read
                </button>
              )}
            </div>
          </div>
        ))}
        {!rows.length && (
          <p className="text-sm text-muted-foreground">No notifications yet.</p>
        )}
      </div>
    </div>
  );
}
