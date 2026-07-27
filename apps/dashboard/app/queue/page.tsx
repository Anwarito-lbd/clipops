"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/utils";

type Pkg = {
  clip_version_id: string;
  account_slot: number;
  account_label: string;
  style: string;
  video_path: string | null;
  caption: string;
  disclosure_included: boolean;
  hashtags: string[];
  compliance_passed: number;
  compliance_total: number;
  duplicate_safe: boolean;
  open_tiktok: string;
  manual_gate: string;
};

export default function QueuePage() {
  const [rows, setRows] = useState<Pkg[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [tiktokUrl, setTiktokUrl] = useState("");

  useEffect(() => {
    api<Pkg[]>("/api/operator/queue")
      .then(setRows)
      .catch((e) => setMsg(String(e)));
  }, []);

  async function copy(text: string) {
    await navigator.clipboard.writeText(text);
    setMsg("Caption copied");
  }

  async function markPosted(versionId: string) {
    if (!tiktokUrl) {
      setMsg("Paste TikTok URL after you post");
      return;
    }
    await api(`/api/versions/${versionId}/mark-posted`, {
      method: "POST",
      body: JSON.stringify({ tiktok_url: tiktokUrl }),
    });
    setMsg("Marked posted — learning record created");
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">Posting queue</h1>
        <p className="text-sm text-muted-foreground">
          Packages ready. You click TikTok&apos;s Post. Best 3–5 clips assigned
          across accounts (not 3 clones of every candidate).
        </p>
      </div>
      <input
        className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
        placeholder="Paste TikTok URL after posting"
        value={tiktokUrl}
        onChange={(e) => setTiktokUrl(e.target.value)}
      />
      {msg && <p className="text-xs text-muted-foreground">{msg}</p>}
      <div className="grid gap-3 lg:grid-cols-3">
        {rows.map((p) => (
          <div key={p.clip_version_id} className="rounded-lg border border-border bg-card p-4 space-y-2">
            <div className="text-sm font-semibold">{p.account_label}</div>
            <div className="text-xs text-muted-foreground capitalize">
              {p.style} · compliance {p.compliance_passed}/{p.compliance_total}
              {p.duplicate_safe ? "" : " · DUPLICATE RISK"}
            </div>
            <div className="text-xs">
              Disclosure: {p.disclosure_included ? "included" : "check"}
            </div>
            <div className="text-xs">{p.hashtags.join(" ") || "—"}</div>
            <pre className="max-h-28 overflow-auto whitespace-pre-wrap rounded bg-background p-2 text-xs text-muted-foreground">
              {p.caption}
            </pre>
            <div className="font-mono text-[10px] text-muted-foreground truncate">
              {p.video_path || "render pending"}
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                className="rounded-md border border-border px-2 py-1 text-xs"
                onClick={() => copy(p.caption)}
              >
                Copy Caption
              </button>
              <a
                className="rounded-md border border-border px-2 py-1 text-xs"
                href={p.open_tiktok}
                target="_blank"
                rel="noreferrer"
              >
                Open TikTok
              </a>
              <button
                className="rounded-md bg-primary px-2 py-1 text-xs font-medium text-primary-foreground"
                onClick={() => markPosted(p.clip_version_id)}
              >
                Mark posted
              </button>
            </div>
            <p className="text-[10px] text-muted-foreground">{p.manual_gate}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
