"use client";

import { useEffect, useState } from "react";
import { API_URL, api, getToken } from "@/lib/utils";
import { StatusBadge } from "@/components/status-badge";

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

type Card = {
  campaign: string | null;
  account: string | null;
  ai_score: number | null;
  predicted_performance: string;
  expected_earnings: number | null;
  compliance_passed: boolean | null;
  transcript_engine: string | null;
  fabricated_transcript: boolean;
  video_path: string | null;
  preview_url: string | null;
  open_campaign: string | null;
  open_tiktok: string;
};

type Campaign = { id: string; name: string };

function PreviewPlayer({ previewUrl }: { previewUrl: string | null }) {
  const [src, setSrc] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;
    async function load() {
      setSrc(null);
      setErr(null);
      if (!previewUrl) return;
      try {
        const token = getToken();
        const res = await fetch(`${API_URL}${previewUrl}`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!res.ok) throw new Error(await res.text());
        const blob = await res.blob();
        if (cancelled) return;
        if (!blob.size) {
          setErr("Empty render");
          return;
        }
        objectUrl = URL.createObjectURL(blob);
        setSrc(objectUrl);
      } catch (e) {
        if (!cancelled) setErr(e instanceof Error ? e.message : "Preview failed");
      }
    }
    load();
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [previewUrl]);

  if (!previewUrl) {
    return (
      <div className="flex aspect-[9/16] max-h-64 items-center justify-center rounded-md bg-background text-xs text-muted-foreground">
        Preview after processing
      </div>
    );
  }
  if (err) {
    return (
      <div className="rounded-md bg-background p-2 text-[10px] text-muted-foreground">{err}</div>
    );
  }
  if (!src) {
    return (
      <div className="flex aspect-[9/16] max-h-64 items-center justify-center rounded-md bg-background text-xs text-muted-foreground">
        Loading preview…
      </div>
    );
  }
  return (
    <video
      src={src}
      controls
      playsInline
      className="max-h-72 w-full rounded-md bg-black object-contain"
    />
  );
}

export default function ReviewPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [campaignId, setCampaignId] = useState("");
  const [versions, setVersions] = useState<Version[]>([]);
  const [cards, setCards] = useState<Record<string, Card>>({});
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    api<Campaign[]>("/api/campaigns").then((c) => {
      setCampaigns(c);
      if (c[0]) setCampaignId(c[0].id);
    });
  }, []);

  async function refresh(id: string) {
    const vs = await api<Version[]>(`/api/campaigns/${id}/versions`);
    setVersions(vs);
    const map: Record<string, Card> = {};
    for (const v of vs) {
      try {
        map[v.id] = await api(`/api/versions/${v.id}/approval-card`);
      } catch {
        /* ignore */
      }
    }
    setCards(map);
  }

  useEffect(() => {
    if (campaignId) refresh(campaignId);
  }, [campaignId]);

  async function approve(id: string, overrideReason?: string) {
    try {
      await api(`/api/versions/${id}/approve`, {
        method: "POST",
        body: JSON.stringify(
          overrideReason ? { override_reason: overrideReason } : {}
        ),
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

  async function regenerate(id: string) {
    await api(`/api/versions/${id}/regenerate`, { method: "POST", body: "{}" });
    await refresh(campaignId);
    setMsg("Caption regenerated — review again");
  }

  async function copyPackage(v: Version, card?: Card) {
    const text = [
      v.caption || "",
      card?.account ? `Account: ${card.account}` : "",
      card?.campaign ? `Campaign: ${card.campaign}` : "",
    ]
      .filter(Boolean)
      .join("\n\n");
    await navigator.clipboard.writeText(text);
    setMsg("Caption package copied");
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">Approval queue</h1>
        <p className="text-sm text-muted-foreground">
          Preview the draft cut, then approve. Posting stays manual.
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
        {versions.map((v) => {
          const card = cards[v.id];
          return (
            <div key={v.id} className="rounded-lg border border-border bg-card p-4 space-y-2">
              <div className="flex items-center justify-between">
                <div className="text-sm font-semibold capitalize">{v.style}</div>
                <StatusBadge status={v.status} />
              </div>
              <PreviewPlayer previewUrl={card?.preview_url || null} />
              {card?.fabricated_transcript && (
                <div className="rounded-md border-2 border-red-500 bg-red-500/10 p-2 text-xs">
                  <div className="font-semibold text-red-500">
                    Placeholder captions — not real speech
                  </div>
                  <p className="mt-1 text-muted-foreground">
                    Speech recognition failed for this footage, so the caption
                    and on-screen hook are filler text. Do not submit this.
                    Check <code>/health</code> for <code>media.cuda</code>, then
                    reprocess the asset.
                  </p>
                </div>
              )}
              <div className="text-xs text-muted-foreground">
                {card?.account || "—"} · {v.duration_band}s · AI{" "}
                {card?.ai_score?.toFixed?.(0) ?? "—"} ·{" "}
                {card?.predicted_performance || "—"}
              </div>
              <div className="text-sm font-medium">{v.hook_text}</div>
              <pre className="max-h-32 overflow-auto whitespace-pre-wrap rounded-md bg-background p-2 font-mono text-xs text-muted-foreground">
                {v.caption}
              </pre>
              <div className="text-xs">
                Compliance:{" "}
                {card?.compliance_passed == null
                  ? "—"
                  : card.compliance_passed
                    ? "passed"
                    : "failed"}
                {card?.expected_earnings != null &&
                  ` · EV £${card.expected_earnings.toFixed(2)}`}
              </div>
              <div className="flex flex-wrap gap-2">
                {card?.fabricated_transcript ? (
                  <button
                    onClick={() => {
                      const reason = window.prompt(
                        "These captions are placeholder text, not real speech.\n\n" +
                          "Approving means posting a clip whose on-screen hook the " +
                          "speaker never said. Type a reason to override:"
                      );
                      if (reason && reason.trim()) approve(v.id, reason.trim());
                    }}
                    className="rounded-md border-2 border-red-500 px-2 py-1 text-xs font-medium text-red-500"
                  >
                    Approve anyway
                  </button>
                ) : (
                  <button
                    onClick={() => approve(v.id)}
                    className="rounded-md bg-primary px-2 py-1 text-xs font-medium text-primary-foreground"
                  >
                    Approve
                  </button>
                )}
                <button
                  onClick={() => reject(v.id)}
                  className="rounded-md border border-border px-2 py-1 text-xs"
                >
                  Reject
                </button>
                <button
                  onClick={() => regenerate(v.id)}
                  className="rounded-md border border-border px-2 py-1 text-xs"
                >
                  Regenerate
                </button>
                <button
                  onClick={() => copyPackage(v, card)}
                  className="rounded-md border border-border px-2 py-1 text-xs"
                >
                  Copy package
                </button>
                {card?.open_campaign && (
                  <a
                    className="rounded-md border border-border px-2 py-1 text-xs"
                    href={card.open_campaign}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open Campaign
                  </a>
                )}
                <a
                  className="rounded-md border border-border px-2 py-1 text-xs"
                  href={card?.open_tiktok || "https://www.tiktok.com"}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open TikTok
                </a>
              </div>
            </div>
          );
        })}
        {!versions.length && (
          <p className="text-sm text-muted-foreground">
            No versions yet — upload footage first.
          </p>
        )}
      </div>
    </div>
  );
}
