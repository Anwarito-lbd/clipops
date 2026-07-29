"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/utils";
import { StatusBadge } from "@/components/status-badge";

type Camp = {
  id: string;
  name: string;
  brand: string | null;
  cpm: number | null;
  budget_remaining_pct: number | null;
  difficulty: string | null;
  required_clips: number;
  min_duration_sec: number;
  max_duration_sec: number;
  opportunity_score: number | null;
  expected_profit: number | null;
  operator_status: string;
  external_url: string | null;
  reject_reasons: string[];
};

export default function OperatorPage() {
  const [rows, setRows] = useState<Camp[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    setRows(await api("/api/operator/top3"));
  }

  useEffect(() => {
    load().catch((e) => setMsg(String(e)));
  }, []);

  async function approve(id: string) {
    const res = await api<{ next_steps: string[]; open_campaign_url: string | null; bot_can_join?: boolean }>(
      `/api/operator/discovered/${id}/approve`,
      { method: "POST", body: "{}" }
    );
    setMsg(
      (res.bot_can_join === false ? "JOIN NOW (you click) · " : "") +
        res.next_steps.join(" · ")
    );
    if (res.open_campaign_url) window.open(res.open_campaign_url, "_blank");
    await load();
  }

  async function reject(id: string) {
    await api(`/api/operator/discovered/${id}/reject`, {
      method: "POST",
      body: "{}",
    });
    await load();
  }

  async function pullScrapling() {
    setBusy(true);
    try {
      const res = await api<{
        scraped_count?: number;
        ingested?: number;
        next?: string;
        error?: string;
      }>("/api/operator/discover/scrapling", { method: "POST", body: "{}" });
      setMsg(
        res.error
          ? `Scrapling: ${res.error}`
          : `Scrapling scraped ${res.scraped_count ?? 0}, ingested ${res.ingested ?? 0}. ${res.next || ""}`
      );
      await load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function seedDemo() {
    await api("/api/operator/demo/seed-top3", { method: "POST", body: "{}" });
    setMsg("Demo top 3 seeded");
    await load();
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">Operator Mode</h1>
          <p className="text-sm text-muted-foreground">
            Best campaigns ranked. You approve; ClipOps notifies JOIN NOW — you
            click Join on CR. Extension or Scrapling pulls public campaigns.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            disabled={busy}
            onClick={pullScrapling}
            className="rounded-md border border-border px-3 py-1.5 text-xs"
          >
            {busy ? "Pulling…" : "Pull campaigns (Scrapling)"}
          </button>
          <button
            onClick={seedDemo}
            className="rounded-md border border-border px-3 py-1.5 text-xs"
          >
            Seed demo top 3
          </button>
        </div>
      </div>
      {msg && <p className="text-xs text-muted-foreground">{msg}</p>}
      <div className="grid gap-4 lg:grid-cols-3">
        {rows.map((c) => (
          <div key={c.id} className="rounded-lg border border-border bg-card p-4 space-y-3">
            <div className="flex justify-between gap-2">
              <div className="text-sm font-semibold">{c.name}</div>
              <StatusBadge status={c.operator_status} />
            </div>
            <div className="space-y-1 text-xs text-muted-foreground">
              <div>CPM: ${c.cpm ?? "—"}</div>
              <div>Remaining budget: {c.budget_remaining_pct ?? "—"}%</div>
              <div>Estimated difficulty: {c.difficulty}</div>
              <div>Required clips: {c.required_clips}</div>
              <div>
                Required duration: {c.min_duration_sec}–{c.max_duration_sec}s
              </div>
              <div className="text-foreground">
                Opportunity score: {c.opportunity_score?.toFixed?.(0) ?? "—"}/100
              </div>
              <div>EV / clip: ${c.expected_profit?.toFixed?.(2) ?? "—"}</div>
            </div>
            {!!c.reject_reasons?.length && (
              <ul className="list-disc pl-4 text-xs text-destructive">
                {c.reject_reasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            )}
            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => reject(c.id)}
                className="rounded-md border border-border px-3 py-1.5 text-xs"
              >
                Reject
              </button>
              <button
                onClick={() => approve(c.id)}
                className="rounded-md bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground"
              >
                Approve Campaign
              </button>
              {c.external_url && (
                <a
                  href={c.external_url}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-md border border-border px-3 py-1.5 text-xs"
                >
                  Open campaign
                </a>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
