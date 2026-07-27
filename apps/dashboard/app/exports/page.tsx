"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/utils";

type Campaign = { id: string; name: string };
type Version = { id: string; style: string; status: string; caption: string | null };
type Render = {
  id: string;
  account_slot: number;
  package_dir: string | null;
  video_path: string | null;
  caption_path: string | null;
  status: string;
};

export default function ExportsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [campaignId, setCampaignId] = useState("");
  const [versions, setVersions] = useState<Version[]>([]);
  const [renders, setRenders] = useState<Record<string, Render[]>>({});
  const [tiktokUrl, setTiktokUrl] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    api<Campaign[]>("/api/campaigns").then((c) => {
      setCampaigns(c);
      if (c[0]) setCampaignId(c[0].id);
    });
  }, []);

  useEffect(() => {
    if (!campaignId) return;
    (async () => {
      const vs = await api<Version[]>(`/api/campaigns/${campaignId}/versions`);
      setVersions(vs);
      const map: Record<string, Render[]> = {};
      for (const v of vs) {
        map[v.id] = await api(`/api/versions/${v.id}/renders`);
      }
      setRenders(map);
    })();
  }, [campaignId]);

  async function copyCaption(caption: string | null) {
    if (!caption) return;
    await navigator.clipboard.writeText(caption);
    setMsg("Caption copied");
  }

  async function markPosted(versionId: string) {
    if (!tiktokUrl) {
      setMsg("Paste TikTok URL first");
      return;
    }
    const res = await api<{ post_id: string }>(`/api/versions/${versionId}/mark-posted`, {
      method: "POST",
      body: JSON.stringify({ tiktok_url: tiktokUrl }),
    });
    setMsg(`Marked posted · post ${res.post_id}`);
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">Exports</h1>
        <p className="text-sm text-muted-foreground">
          Download packages, copy captions, open TikTok yourself, then mark posted.
        </p>
      </div>

      <select
        className="rounded-md border border-border bg-background px-3 py-2 text-sm"
        value={campaignId}
        onChange={(e) => setCampaignId(e.target.value)}
      >
        {campaigns.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>

      <div className="flex flex-wrap gap-2">
        <a
          className="rounded-md border border-border px-3 py-1.5 text-sm"
          href="https://www.tiktok.com"
          target="_blank"
          rel="noreferrer"
        >
          Open TikTok
        </a>
        <input
          className="min-w-[280px] flex-1 rounded-md border border-border bg-background px-3 py-1.5 text-sm"
          placeholder="Paste TikTok post URL after you publish"
          value={tiktokUrl}
          onChange={(e) => setTiktokUrl(e.target.value)}
        />
      </div>
      {msg && <p className="text-xs text-muted-foreground">{msg}</p>}

      <div className="space-y-3">
        {versions.map((v) => (
          <div key={v.id} className="rounded-lg border border-border bg-card p-4 space-y-2">
            <div className="text-sm font-semibold capitalize">
              {v.style} · {v.status}
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                className="rounded-md border border-border px-2 py-1 text-xs"
                onClick={() => copyCaption(v.caption)}
              >
                Copy caption
              </button>
              <button
                className="rounded-md border border-border px-2 py-1 text-xs"
                onClick={() => markPosted(v.id)}
              >
                Mark as posted
              </button>
            </div>
            {(renders[v.id] || []).map((r) => (
              <div key={r.id} className="font-mono text-xs text-muted-foreground">
                account-{r.account_slot}: {r.package_dir || r.video_path || "pending"}
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
