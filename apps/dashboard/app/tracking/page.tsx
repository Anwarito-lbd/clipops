"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/utils";
import { StatusBadge } from "@/components/status-badge";

type Row = {
  post_id: string;
  tiktok_url: string | null;
  post_status: string;
  submission_id: string | null;
  submission_status: string | null;
  earnings_id: string | null;
  provisional_amount: number | null;
  net_amount: number | null;
  payout_id: string | null;
  payout_status: string | null;
  payout_ready: boolean;
};

export default function TrackingPage() {
  const [rows, setRows] = useState<Row[]>([]);
  const [amount, setAmount] = useState("12.50");
  const [msg, setMsg] = useState<string | null>(null);

  async function refresh() {
    setRows(await api("/api/tracking"));
  }

  useEffect(() => {
    refresh().catch((e) => setMsg(String(e)));
  }, []);

  async function markSubmitted(postId: string) {
    await api(`/api/posts/${postId}/mark-submitted`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    await refresh();
    setMsg("Marked submitted — continue review in Content Rewards manually");
  }

  async function setEarnings(submissionId: string, ready: boolean) {
    const res = await api<{ alert: string | null; payout_id: string | null }>(
      `/api/submissions/${submissionId}/earnings`,
      {
        method: "POST",
        body: JSON.stringify({
          provisional_amount: Number(amount),
          mark_payout_ready: ready,
        }),
      }
    );
    await refresh();
    setMsg(res.alert === "PAYOUT_READY" ? "Payout ready alert" : "Earnings updated");
  }

  async function markPaid(payoutId: string) {
    await api(`/api/payouts/${payoutId}/mark-received`, {
      method: "POST",
      body: JSON.stringify({ notes: "Cashed out manually" }),
    });
    await refresh();
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">Tracking</h1>
        <p className="text-sm text-muted-foreground">
          Paste links after you post/submit. 7% fee applied as ×0.93. Validation
          windows: 3-day views, 7-day review.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        <a
          className="rounded-md border border-border px-3 py-1.5 text-sm"
          href="https://www.contentrewards.com"
          target="_blank"
          rel="noreferrer"
        >
          Open Content Rewards submission page
        </a>
        <input
          className="rounded-md border border-border bg-background px-3 py-1.5 text-sm"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          placeholder="Provisional $"
        />
      </div>
      {msg && <p className="text-xs text-muted-foreground">{msg}</p>}

      <div className="overflow-auto rounded-lg border border-border">
        <table className="w-full text-left text-sm">
          <thead className="bg-card text-xs uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="px-3 py-2">Post</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Earnings</th>
              <th className="px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.post_id} className="border-t border-border">
                <td className="px-3 py-2">
                  <div className="max-w-xs truncate font-mono text-xs">
                    {r.tiktok_url || r.post_id}
                  </div>
                  {r.payout_ready && (
                    <span className="text-xs font-medium text-warning">
                      Payout ready
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 space-y-1">
                  <StatusBadge status={r.post_status} />
                  {r.submission_status && (
                    <StatusBadge status={r.submission_status} />
                  )}
                </td>
                <td className="px-3 py-2 text-xs">
                  {r.provisional_amount != null && (
                    <div>prov ${r.provisional_amount}</div>
                  )}
                  {r.net_amount != null && <div>net ${r.net_amount}</div>}
                </td>
                <td className="px-3 py-2">
                  <div className="flex flex-wrap gap-1">
                    {!r.submission_id && (
                      <button
                        className="rounded-md border border-border px-2 py-1 text-xs"
                        onClick={() => markSubmitted(r.post_id)}
                      >
                        Mark submitted
                      </button>
                    )}
                    {r.submission_id && (
                      <>
                        <button
                          className="rounded-md border border-border px-2 py-1 text-xs"
                          onClick={() => setEarnings(r.submission_id!, false)}
                        >
                          Update earnings
                        </button>
                        <button
                          className="rounded-md border border-border px-2 py-1 text-xs"
                          onClick={() => setEarnings(r.submission_id!, true)}
                        >
                          Mark payout ready
                        </button>
                      </>
                    )}
                    {r.payout_id && r.payout_status === "PAYOUT_READY" && (
                      <button
                        className="rounded-md bg-primary px-2 py-1 text-xs font-medium text-primary-foreground"
                        onClick={() => markPaid(r.payout_id!)}
                      >
                        Mark payout received
                      </button>
                    )}
                    {r.tiktok_url && (
                      <button
                        className="rounded-md border border-border px-2 py-1 text-xs"
                        onClick={() =>
                          navigator.clipboard.writeText(r.tiktok_url || "")
                        }
                      >
                        Copy submission URL
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!rows.length && (
          <p className="p-4 text-sm text-muted-foreground">No posts tracked yet.</p>
        )}
      </div>
    </div>
  );
}
