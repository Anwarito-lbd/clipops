"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/utils";
import { StatusBadge } from "@/components/status-badge";

type Campaign = { id: string; name: string; status: string };
type Asset = {
  id: string;
  campaign_id: string;
  filename: string;
  status: string;
  error_message?: string | null;
};

export default function AssetsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [campaignId, setCampaignId] = useState("");
  const [assets, setAssets] = useState<Asset[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    api<Campaign[]>("/api/campaigns").then((c) => {
      setCampaigns(c);
      if (c[0]) setCampaignId(c[0].id);
    });
  }, []);

  useEffect(() => {
    if (!campaignId) return;
    api<Asset[]>(`/api/campaigns/${campaignId}/assets`).then(setAssets);
  }, [campaignId]);

  async function upload() {
    if (!file || !campaignId) return;
    const fd = new FormData();
    fd.append("file", file);
    const token = localStorage.getItem("clipops_token");
    const res = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"}/api/campaigns/${campaignId}/assets`,
      {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: fd,
      }
    );
    if (!res.ok) {
      setMsg(await res.text());
      return;
    }
    setMsg("Uploaded — pipeline started (WhisperX → scenes → candidates)");
    setAssets(await api(`/api/campaigns/${campaignId}/assets`));
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">Assets</h1>
        <p className="text-sm text-muted-foreground">
          Upload approved campaign footage. Transcription uses WhisperX when
          available.
        </p>
      </div>

      <div className="rounded-lg border border-border bg-card p-4 space-y-3">
        <label className="text-xs text-muted-foreground">Campaign</label>
        <select
          className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
          value={campaignId}
          onChange={(e) => setCampaignId(e.target.value)}
        >
          {campaigns.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name} ({c.status})
            </option>
          ))}
        </select>
        <input
          type="file"
          accept="video/*"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
          className="block w-full text-sm"
        />
        <button
          onClick={upload}
          className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground"
        >
          Upload & analyse
        </button>
        {msg && <p className="text-xs text-muted-foreground">{msg}</p>}
      </div>

      <div className="space-y-2">
        {assets.map((a) => (
          <div
            key={a.id}
            className="flex items-center justify-between rounded-lg border border-border bg-card px-4 py-3"
          >
            <div>
              <div className="text-sm font-medium">{a.filename}</div>
              {a.error_message && (
                <div className="text-xs text-destructive">{a.error_message}</div>
              )}
            </div>
            <StatusBadge status={a.status} />
          </div>
        ))}
      </div>
    </div>
  );
}
