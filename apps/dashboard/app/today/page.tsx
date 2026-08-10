"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/utils";

type Post = {
  clip_version_id: string;
  account_id: string;
  account_label: string;
  caption: string;
  hook_text: string | null;
  campaign_name: string | null;
};

type Sitting = {
  index: number;
  at_hour: number;
  label: string;
  state: "done" | "now" | "upcoming";
  posts: Post[];
};

type Awaiting = {
  post_id: string;
  tiktok_url: string | null;
  minutes_since_posted: number;
  overdue: boolean;
};

type Today = {
  sittings: Sitting[];
  sitting_count: number;
  ramping: boolean;
  days_active: number;
  capacity_today: number;
  scheduled: number;
  unscheduled: number;
  next_sitting_in_minutes: number | null;
  note: string;
  ready_count: number;
  awaiting_submission: Awaiting[];
  blocked: { clips_awaiting_approval: number; assets_failed: number };
};

export default function TodayPage() {
  const [data, setData] = useState<Today | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [urls, setUrls] = useState<Record<string, string>>({});

  async function refresh() {
    try {
      setData(await api<Today>("/api/operator/today"));
    } catch (e) {
      setMsg(String(e));
    }
  }
  useEffect(() => {
    refresh();
  }, []);

  async function copy(text: string, what: string) {
    await navigator.clipboard.writeText(text);
    setMsg(`${what} copied`);
  }

  async function markPosted(versionId: string) {
    const url = urls[versionId];
    if (!url) {
      setMsg("Paste the TikTok URL first — views only count once the link is submitted");
      return;
    }
    try {
      await api(`/api/versions/${versionId}/mark-posted`, {
        method: "POST",
        body: JSON.stringify({ tiktok_url: url }),
      });
      setMsg("Marked posted — now submit it to the campaign straight away");
      await refresh();
    } catch (e) {
      setMsg(String(e));
    }
  }

  if (!data) {
    return (
      <div className="p-6 text-sm text-muted-foreground">
        {msg || "Loading today…"}
      </div>
    );
  }

  const overdue = data.awaiting_submission.filter((a) => a.overdue);

  return (
    <div className="space-y-4 p-4">
      <div>
        <h1 className="text-lg font-semibold">Today</h1>
        <p className="text-xs text-muted-foreground">
          {data.note}
          {data.next_sitting_in_minutes != null &&
            ` · next sitting in ${Math.floor(data.next_sitting_in_minutes / 60)}h ${
              data.next_sitting_in_minutes % 60
            }m`}
        </p>
      </div>

      {/* The one backlog that costs money rather than just delaying it. */}
      {overdue.length > 0 && (
        <div className="rounded-lg border-2 border-red-500 bg-red-500/10 p-3">
          <div className="text-sm font-semibold text-red-500">
            {overdue.length} post{overdue.length > 1 ? "s" : ""} live but not submitted
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            Campaigns expect the link within about an hour of posting. Submit
            these on Content Rewards now — a late submission can be refused
            outright, which loses the whole clip.
          </p>
          <ul className="mt-2 space-y-1 text-xs">
            {overdue.map((a) => (
              <li key={a.post_id} className="flex items-center gap-2">
                <span className="text-red-500">
                  {Math.floor(a.minutes_since_posted / 60)}h ago
                </span>
                {a.tiktok_url && (
                  <a
                    className="underline"
                    href={a.tiktok_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {a.tiktok_url.slice(0, 48)}
                  </a>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
        <Stat label="Ready to post" value={data.ready_count} />
        <Stat label="Scheduled today" value={`${data.scheduled}/${data.capacity_today}`} />
        <Stat
          label="Awaiting approval"
          value={data.blocked.clips_awaiting_approval}
          warn={data.blocked.clips_awaiting_approval > 0}
        />
        <Stat
          label="Failed assets"
          value={data.blocked.assets_failed}
          warn={data.blocked.assets_failed > 0}
        />
      </div>

      {data.unscheduled > 0 && (
        <p className="text-xs text-amber-500">
          {data.unscheduled} approved clip(s) beyond today&apos;s capacity — they
          roll to tomorrow. Don&apos;t double-post to catch up; stacking posts
          inside the 3-hour window is the actual risk.
        </p>
      )}

      {data.sittings.map((s) => (
        <div
          key={s.index}
          className={`rounded-lg border p-3 ${
            s.state === "now" ? "border-primary" : "border-border"
          }`}
        >
          <div className="mb-2 flex items-center justify-between">
            <div className="text-sm font-semibold">
              Sitting {s.index} · {s.label}
            </div>
            <span
              className={`rounded px-2 py-0.5 text-[10px] uppercase ${
                s.state === "now"
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground"
              }`}
            >
              {s.state === "now" ? "post now" : s.state}
            </span>
          </div>

          {s.posts.length === 0 && (
            <p className="text-xs text-muted-foreground">
              No clips available for this sitting.
            </p>
          )}

          <div className="space-y-2">
            {s.posts.map((p) => (
              <div
                key={p.clip_version_id}
                className="rounded-md border border-border bg-card p-2"
              >
                <div className="flex items-center justify-between text-xs">
                  <span className="font-medium">{p.account_label}</span>
                  <span className="text-muted-foreground">
                    {p.campaign_name || "—"}
                  </span>
                </div>
                {p.hook_text && (
                  <div className="mt-1 text-sm font-medium">{p.hook_text}</div>
                )}
                <pre className="mt-1 max-h-20 overflow-auto whitespace-pre-wrap rounded bg-background p-1.5 font-mono text-[11px] text-muted-foreground">
                  {p.caption}
                </pre>
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  <button
                    onClick={() => copy(p.caption, "Caption")}
                    className="rounded border border-border px-2 py-1 text-[11px]"
                  >
                    Copy caption
                  </button>
                  <a
                    href="https://www.tiktok.com/upload"
                    target="_blank"
                    rel="noreferrer"
                    className="rounded border border-border px-2 py-1 text-[11px]"
                  >
                    Open TikTok
                  </a>
                  <input
                    value={urls[p.clip_version_id] || ""}
                    onChange={(e) =>
                      setUrls({ ...urls, [p.clip_version_id]: e.target.value })
                    }
                    placeholder="paste TikTok URL after posting"
                    className="min-w-[180px] flex-1 rounded border border-border bg-background px-2 py-1 text-[11px]"
                  />
                  <button
                    onClick={() => markPosted(p.clip_version_id)}
                    className="rounded bg-primary px-2 py-1 text-[11px] font-medium text-primary-foreground"
                  >
                    Mark posted
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}

      {msg && <p className="text-xs text-muted-foreground">{msg}</p>}
    </div>
  );
}

function Stat({
  label,
  value,
  warn,
}: {
  label: string;
  value: string | number;
  warn?: boolean;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-2">
      <div className="text-[10px] uppercase text-muted-foreground">{label}</div>
      <div className={`text-lg font-semibold ${warn ? "text-amber-500" : ""}`}>
        {value}
      </div>
    </div>
  );
}
