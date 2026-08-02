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
  const [brief, setBrief] = useState("");
  const [briefUrl, setBriefUrl] = useState("");

  async function load() {
    setRows(await api("/api/operator/top3"));
  }

  useEffect(() => {
    load().catch((e) => setMsg(String(e)));
  }, []);

  async function approve(id: string) {
    const res = await api<{ next_steps: string[]; open_campaign_url: string | null }>(
      `/api/operator/discovered/${id}/approve`,
      { method: "POST", body: "{}" }
    );
    setMsg(res.next_steps.join(" · "));
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

  async function clearDemo() {
    const res = await api<{ removed_discovered: number; next: string }>(
      "/api/operator/clear-demo",
      { method: "POST", body: "{}" }
    );
    setMsg(`Cleared ${res.removed_discovered} demo row(s). ${res.next}`);
    await load();
  }

  async function pasteBrief() {
    const res = await api<{ top3: Array<{ name: string; score: number }> }>(
      "/api/operator/paste-brief",
      {
        method: "POST",
        body: JSON.stringify({
          brief_text: brief,
          external_url: briefUrl || undefined,
        }),
      }
    );
    setMsg(
      `Ingested. Top: ${(res.top3 || []).map((t) => `${t.name} (${t.score})`).join(", ") || "ranked"}`
    );
    setBrief("");
    await load();
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">Operator Mode</h1>
        <p className="text-sm text-muted-foreground">
          Real Content Rewards only. Scan with the extension (or paste a brief).
          You approve; you click Join.
        </p>
      </div>

      <div className="rounded-lg border border-border bg-card p-4 space-y-2 text-sm">
        <div className="font-semibold">Get real campaigns</div>
        <ol className="list-decimal space-y-1 pl-5 text-muted-foreground">
          <li>
            Chrome → <code className="text-xs">chrome://extensions</code> → Load
            unpacked → <code className="text-xs">clipops/browser-extension</code>
          </li>
          <li>
            Open <strong>Content Rewards</strong> while logged in (campaign list)
          </li>
          <li>
            Click extension → <strong>Scan campaigns → ClipOps</strong>
          </li>
          <li>Refresh this page — top 3 ranked appear below</li>
        </ol>
        <div className="flex flex-wrap gap-2 pt-2">
          <button
            onClick={() => load()}
            className="rounded-md border border-border px-3 py-1.5 text-xs"
          >
            Refresh top 3
          </button>
          <button
            onClick={clearDemo}
            className="rounded-md border border-border px-3 py-1.5 text-xs"
          >
            Clear demo data
          </button>
          <a
            className="rounded-md border border-border px-3 py-1.5 text-xs"
            href="https://www.contentrewards.com"
            target="_blank"
            rel="noreferrer"
          >
            Open Content Rewards
          </a>
        </div>
      </div>

      <div className="rounded-lg border border-border bg-card p-4 space-y-2">
        <div className="text-sm font-semibold">Paste brief (if scan misses DOM)</div>
        <p className="text-xs text-muted-foreground">
          Copy the campaign page text from CR and paste here — ClipOps ranks it
          the same way.
        </p>
        <input
          className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-xs"
          placeholder="Campaign URL (optional)"
          value={briefUrl}
          onChange={(e) => setBriefUrl(e.target.value)}
        />
        <textarea
          className="min-h-[120px] w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-xs"
          placeholder="Paste full campaign brief: name, CPM, budget, geo, hashtags, disclosure…"
          value={brief}
          onChange={(e) => setBrief(e.target.value)}
        />
        <button
          onClick={pasteBrief}
          disabled={brief.trim().length < 20}
          className="rounded-md bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground disabled:opacity-40"
        >
          Rank pasted campaign
        </button>
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
        {!rows.length && (
          <p className="text-sm text-muted-foreground lg:col-span-3">
            No real campaigns yet — scan with the extension or paste a CR brief
            above.
          </p>
        )}
      </div>
    </div>
  );
}
