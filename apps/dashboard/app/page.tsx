"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, setToken } from "@/lib/utils";
import { StatusBadge } from "@/components/status-badge";

type Home = {
  month_label: string;
  currency?: string;
  monthly_target: number;
  current_earnings: number;
  progress_pct: number;
  verified_views: number;
  approval_rate: number;
  avg_views_per_clip: number;
  effective_cpm: number;
  clips_produced?: number;
  clips_posted?: number;
  payout_ready?: number;
  forecast?: {
    projected_monthly_earnings: number;
    monthly_run_rate: number;
    required_clips_per_day: number;
    on_track: boolean;
    notes: string[];
    planning_cpm: number;
  };
  campaigns: Array<{
    id: string;
    name: string;
    opportunity_score: number | null;
    cpm: number | null;
    difficulty: string | null;
    budget_remaining_pct: number | null;
    operator_status: string;
  }>;
  today_accounts: Array<{
    label: string;
    done: number;
    target: number;
    complete: boolean;
  }>;
  clips_waiting_approval: number;
  production_queue: Array<{ title: string; status: string; at: string | null }>;
};

type GoLive = {
  score: number;
  target: number;
  next: Array<{ id: string; label: string; how: string }>;
  items: Array<{ id: string; label: string; done: boolean; how: string }>;
  note: string;
};

export default function HomePage() {
  const [home, setHome] = useState<Home | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState("operator@clipops.local");
  const [password, setPassword] = useState("");
  const [goLive, setGoLive] = useState<GoLive | null>(null);
  const [stack, setStack] = useState<{
    readiness_pct?: number;
    remotion?: boolean;
    redis?: boolean;
    cuda?: boolean;
    whisperx?: boolean;
    celery_eager?: boolean;
    diarization_ready?: boolean;
    mode?: string;
    device_name?: string | null;
  } | null>(null);

  async function loadStack() {
    try {
      const h = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"}/health`
      ).then((r) => r.json());
      setStack(h.media || null);
    } catch {
      setStack(null);
    }
  }

  async function load() {
    try {
      setHome(await api<Home>("/api/operator/home"));
      setGoLive(await api<GoLive>("/api/operator/readiness"));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    }
  }

  async function login() {
    const res = await api<{ access_token: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setToken(res.access_token);
    await load();
  }

  async function seed() {
    await api("/api/operator/demo/seed-top3", { method: "POST", body: "{}" });
    await load();
  }

  async function approve(id: string) {
    await api(`/api/operator/discovered/${id}/approve`, {
      method: "POST",
      body: "{}",
    });
    await load();
  }

  useEffect(() => {
    loadStack();
    load().catch(() => undefined);
  }, []);

  const bar = Math.min(100, home?.progress_pct || 0);

  return (
    <div className="mx-auto max-w-3xl space-y-4 font-mono">
      <div className="rounded-lg border border-border bg-card p-4">
        <div className="flex items-baseline justify-between">
          <h1 className="text-xl font-bold tracking-widest">CLIPOPS</h1>
          <span className="text-xs text-muted-foreground">
            {home?.month_label || "—"}
          </span>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          Approve → post → submit → cash out. No CR/TikTok bots.
        </p>
      </div>

      {stack && (
        <div className="rounded-lg border border-border bg-card p-4 space-y-2 text-xs">
          <div className="flex items-center justify-between">
            <span className="font-semibold uppercase tracking-wide text-muted-foreground">
              Stack readiness
            </span>
            <span>{stack.readiness_pct ?? "—"}%</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-secondary">
            <div
              className="h-full bg-primary"
              style={{ width: `${stack.readiness_pct ?? 0}%` }}
            />
          </div>
          <div className="grid grid-cols-2 gap-1 sm:grid-cols-3">
            <span>
              CUDA {stack.cuda ? "✓" : "✗"} {stack.device_name || ""}
            </span>
            <span>WhisperX {stack.whisperx ? "✓" : "✗"}</span>
            <span>Remotion {stack.remotion ? "✓" : "✗"}</span>
            <span>Redis {stack.redis ? "✓" : "✗"}</span>
            <span>Mode {stack.mode || "—"}</span>
            <span>Diarize {stack.diarization_ready ? "✓" : "—"}</span>
          </div>
        </div>
      )}

      {goLive && (
        <div className="rounded-lg border border-border bg-card p-4 space-y-2 text-xs">
          <div className="flex items-center justify-between">
            <span className="font-semibold uppercase tracking-wide text-muted-foreground">
              Go-live score (→ {goLive.target}%)
            </span>
            <span className="text-sm font-bold">{goLive.score}%</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-secondary">
            <div
              className="h-full bg-primary"
              style={{ width: `${goLive.score}%` }}
            />
          </div>
          <p className="text-muted-foreground">{goLive.note}</p>
          {goLive.next.length > 0 ? (
            <ol className="list-decimal space-y-1 pl-4">
              {goLive.next.map((n) => (
                <li key={n.id}>
                  <span className="font-medium text-foreground">{n.label}</span>
                  <div className="text-muted-foreground">{n.how}</div>
                </li>
              ))}
            </ol>
          ) : (
            <p className="text-success">All go-live steps complete.</p>
          )}
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-border bg-card p-4 space-y-2">
          <p className="text-sm text-destructive">Sign in to load Operator Mode</p>
          <p className="text-[10px] text-muted-foreground">
            Password from rotate_secrets.py (not changeme after rotation).
          </p>
          <div className="flex flex-wrap gap-2">
            <input
              className="rounded-md border border-border bg-background px-3 py-1.5 text-sm"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <input
              type="password"
              className="rounded-md border border-border bg-background px-3 py-1.5 text-sm"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="password"
            />
            <button
              onClick={login}
              className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground"
            >
              Sign in
            </button>
          </div>
        </div>
      )}

      {home && (
        <>
          <div className="rounded-lg border border-border bg-card p-4 space-y-3">
            <Row
              label="MONTHLY TARGET"
              value={`${home.currency === "GBP" ? "£" : "$"}${home.monthly_target.toLocaleString()}`}
            />
            <Row
              label="CURRENT EARNINGS"
              value={`${home.currency === "GBP" ? "£" : "$"}${home.current_earnings.toLocaleString()}`}
            />
            <Row label="PROGRESS" value={`${home.progress_pct}%`} />
            <div className="h-2 w-full overflow-hidden rounded-full bg-secondary">
              <div
                className="h-full bg-primary transition-all"
                style={{ width: `${bar}%` }}
              />
            </div>
            <div className="grid grid-cols-2 gap-2 pt-2 text-sm sm:grid-cols-4">
              <Mini label="VERIFIED VIEWS" value={home.verified_views.toLocaleString()} />
              <Mini label="APPROVAL RATE" value={`${home.approval_rate}%`} />
              <Mini label="AVG VIEWS/CLIP" value={String(home.avg_views_per_clip)} />
              <Mini
                label="CURRENT CPM"
                value={`${home.currency === "GBP" ? "£" : "$"}${home.effective_cpm}`}
              />
            </div>
            <div className="grid grid-cols-3 gap-2 text-sm">
              <Mini label="PRODUCED" value={String(home.clips_produced ?? 0)} />
              <Mini label="POSTED" value={String(home.clips_posted ?? 0)} />
              <Mini
                label="PAYOUT READY"
                value={`${home.currency === "GBP" ? "£" : "$"}${home.payout_ready ?? 0}`}
              />
            </div>
            {home.forecast && (
              <div className="border-t border-border pt-3 text-xs space-y-1">
                <div className="font-semibold uppercase tracking-wide text-muted-foreground">
                  Forecast (planning)
                </div>
                <div>
                  Run-rate{" "}
                  {home.currency === "GBP" ? "£" : "$"}
                  {home.forecast.monthly_run_rate} → projected{" "}
                  {home.currency === "GBP" ? "£" : "$"}
                  {home.forecast.projected_monthly_earnings}
                </div>
                <div>
                  Need ~{home.forecast.required_clips_per_day} posts/day @ £
                  {home.forecast.planning_cpm} CPM ·{" "}
                  {home.forecast.on_track ? "on track" : "behind pace"}
                </div>
              </div>
            )}
          </div>

          <div className="rounded-lg border border-border bg-card p-4 space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                Campaigns
              </h2>
              <button
                onClick={seed}
                className="rounded-md border border-border px-2 py-1 text-xs"
              >
                Seed demo top 3
              </button>
            </div>
            {home.campaigns.map((c, i) => (
              <div
                key={c.id}
                className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3"
              >
                <div>
                  <span
                    className={`mr-2 inline-block h-2 w-2 rounded-full ${
                      i < 2 ? "bg-success" : "bg-warning"
                    }`}
                  />
                  <span className="text-sm font-medium">{c.name}</span>
                  <div className="text-xs text-muted-foreground">
                    SCORE {c.opportunity_score?.toFixed?.(0) ?? "—"} · $
                    {c.cpm ?? "—"} CPM · {c.difficulty} ·{" "}
                    {c.budget_remaining_pct ?? "—"}% budget left
                  </div>
                </div>
                {c.operator_status === "top3" && (
                  <button
                    onClick={() => approve(c.id)}
                    className="rounded-md bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground"
                  >
                    Approve Campaign
                  </button>
                )}
                <StatusBadge status={c.operator_status} />
              </div>
            ))}
            {!home.campaigns.length && (
              <p className="text-sm text-muted-foreground">
                No ranked campaigns — use the browser extension or Seed demo.
              </p>
            )}
          </div>

          <div className="rounded-lg border border-border bg-card p-4 space-y-2">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Today
            </h2>
            {home.today_accounts.map((a) => (
              <div key={a.label} className="flex justify-between text-sm">
                <span>{a.label}</span>
                <span>
                  {a.done}/{a.target} clips {a.complete ? "✓" : ""}
                </span>
              </div>
            ))}
            <p className="pt-2 text-sm text-warning">
              {home.clips_waiting_approval} clips waiting for approval
            </p>
            <div className="flex gap-2 pt-1">
              <Link className="text-xs underline" href="/review">
                Review
              </Link>
              <Link className="text-xs underline" href="/queue">
                Posting queue
              </Link>
              <Link className="text-xs underline" href="/operator">
                Operator
              </Link>
            </div>
          </div>

          <div className="rounded-lg border border-border bg-card p-4 space-y-2">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Production queue
            </h2>
            {home.production_queue.map((e, idx) => (
              <div key={idx} className="flex gap-3 text-xs">
                <span
                  className={
                    e.status === "action_required"
                      ? "text-warning"
                      : "text-success"
                  }
                >
                  {e.status === "action_required" ? "!" : "+"}
                </span>
                <span>{e.title}</span>
              </div>
            ))}
            {!home.production_queue.length && (
              <p className="text-xs text-muted-foreground">
                Events appear after asset analyse / render.
              </p>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-bold">{value}</span>
    </div>
  );
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] text-muted-foreground">{label}</div>
      <div className="text-sm font-bold">{value}</div>
    </div>
  );
}
