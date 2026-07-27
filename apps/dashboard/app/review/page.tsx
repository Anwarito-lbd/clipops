"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/utils";
import { StatusBadge } from "@/components/status-badge";

type Campaign = { id: string; name: string };
type Version = {
  id: string;
  style: string;
  duration_band: string;
  hook_variant: number;
  subtitle_style: string;
  caption: string | null;
  hook_text: string | null;
  status: string;
};

export default function ReviewPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [campaignId, setCampaignId] = useState("");
  const [versions, setVersions] = useState<Version[]>([]);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    api<Campaign[]>("/api/campaigns").then((c) => {
      setCampaigns(c);
      if (c[0]) setCampaignId(c[0].id);
    });
  }, []);

  async function refresh(id: string) {
    setVersions(await api(`/api/campaigns/${id}/versions`));
  }

  useEffect(() => {
    if (campaignId) refresh(campaignId);
  }, [campaignId]);

  async function approve(id: string) {
    try {
      await api(`/api/versions/${id}/approve`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      await refresh(campaignId);
      setMsg("Approved — render queued");
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Approve failed");
    }
  }

  async function reject(id: string) {
    await api(`/api/versions/${id}/reject`, { method: "POST", body: "{}" });
    await refresh(campaignId);
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">Review</h1>
        <p className="text-sm text-muted-foreground">
          Three account-specific versions — approve only after compliance.
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
      {msg && <p className="text-xs text-muted-foreground">{msg}</p>}

      <div className="grid gap-3 lg:grid-cols-3">
        {versions.map((v) => (
          <div key={v.id} className="rounded-lg border border-border bg-card p-4 space-y-2">
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold capitalize">{v.style}</div>
              <StatusBadge status={v.status} />
            </div>
            <div className="text-xs text-muted-foreground">
              {v.duration_band}s · hook {v.hook_variant} · {v.subtitle_style}
            </div>
            <div className="text-sm font-medium">{v.hook_text}</div>
            <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded-md bg-background p-2 font-mono text-xs text-muted-foreground">
              {v.caption}
            </pre>
            <div className="flex gap-2">
              <button
                onClick={() => approve(v.id)}
                className="rounded-md bg-primary px-2 py-1 text-xs font-medium text-primary-foreground"
              >
                Approve
              </button>
              <button
                onClick={() => reject(v.id)}
                className="rounded-md border border-border px-2 py-1 text-xs"
              >
                Reject
              </button>
            </div>
          </div>
        ))}
        {!versions.length && (
          <p className="text-sm text-muted-foreground">
            No versions yet — upload footage first.
          </p>
        )}
      </div>
    </div>
  );
}
