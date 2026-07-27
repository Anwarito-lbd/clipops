"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/utils";
import { StatusBadge } from "@/components/status-badge";

type Campaign = {
  id: string;
  name: string;
  brand: string | null;
  score: number | null;
  expected_profit: number | null;
  is_recommended: boolean;
  reject_reasons: string[];
  status: string;
  cpm: number | null;
  external_url: string | null;
};

export default function CampaignsPage() {
  const [rows, setRows] = useState<Campaign[]>([]);
  const [brief, setBrief] = useState(
    `Summer Energy Drink Push
Brand: VoltPop
CPM: $8.50
Budget: $25,000 utilised 42%
Geo: US CA
Duration: 15-45 seconds
Required: #VoltPop #ContentRewards @voltpop
Disclosure: Paid partnership
CTA: Link in bio
`
  );
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function refresh() {
    setRows(await api<Campaign[]>("/api/campaigns"));
  }

  useEffect(() => {
    refresh().catch((e) => setMsg(String(e)));
  }, []);

  async function importBrief() {
    setBusy(true);
    setMsg(null);
    try {
      await api("/api/campaigns", {
        method: "POST",
        body: JSON.stringify({ raw_brief: brief }),
      });
      await refresh();
      setMsg("Campaign scored");
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Import failed");
    } finally {
      setBusy(false);
    }
  }

  async function markJoined(id: string) {
    try {
      await api(`/api/campaigns/${id}/join`, { method: "POST", body: "{}" });
      await refresh();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Join failed");
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">Campaigns</h1>
        <p className="text-sm text-muted-foreground">
          Paste a brief. EV uses approval × views/1000 × CPM × 0.93 − cost.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-lg border border-border bg-card p-4 space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Import brief
          </h2>
          <textarea
            className="h-56 w-full rounded-md border border-border bg-background p-3 font-mono text-xs"
            value={brief}
            onChange={(e) => setBrief(e.target.value)}
          />
          <button
            disabled={busy}
            onClick={importBrief}
            className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground disabled:opacity-50"
          >
            Score campaign
          </button>
          {msg && <p className="text-xs text-muted-foreground">{msg}</p>}
        </div>

        <div className="rounded-lg border border-border bg-card p-4">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Ranked
          </h2>
          <div className="mt-3 space-y-2">
            {rows.map((c) => (
              <div
                key={c.id}
                className="rounded-md border border-border p-3 space-y-2"
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="text-sm font-semibold">{c.name}</div>
                    <div className="text-xs text-muted-foreground">
                      {c.brand || "—"} · CPM {c.cpm ?? "—"} · EV{" "}
                      {c.expected_profit?.toFixed?.(2) ?? c.expected_profit}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-2xl font-bold">
                      {c.score?.toFixed?.(0) ?? "—"}
                    </div>
                    <StatusBadge status={c.status} />
                  </div>
                </div>
                {!c.is_recommended && (
                  <ul className="list-disc pl-4 text-xs text-destructive">
                    {c.reject_reasons.map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                )}
                <div className="flex flex-wrap gap-2">
                  {c.external_url && (
                    <a
                      className="rounded-md border border-border px-2 py-1 text-xs"
                      href={c.external_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open campaign
                    </a>
                  )}
                  {c.is_recommended && c.status !== "joined" && (
                    <button
                      className="rounded-md border border-border px-2 py-1 text-xs"
                      onClick={() => markJoined(c.id)}
                    >
                      Mark joined
                    </button>
                  )}
                </div>
              </div>
            ))}
            {!rows.length && (
              <p className="text-sm text-muted-foreground">No campaigns yet.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
