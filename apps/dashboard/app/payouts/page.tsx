"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/utils";

type Learning = {
  clip_count: number;
  ready_to_learn: boolean;
  recommendations: string[];
  cohorts: Array<{
    account: string;
    editing_style: string;
    clip_length_band: string;
    hook_type: string;
    avg_views: number;
    n: number;
  }>;
};

type Analytics = {
  earnings: { provisional_total: number; net_total: number; payout_ready_total: number };
  payouts_ready: number;
};

export default function PayoutsPage() {
  const [learning, setLearning] = useState<Learning | null>(null);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);

  useEffect(() => {
    Promise.all([
      api<Learning>("/api/operator/learning"),
      api<Analytics>("/api/operator/analytics"),
    ]).then(([l, a]) => {
      setLearning(l);
      setAnalytics(a);
    });
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">Payouts & learning</h1>
        <p className="text-sm text-muted-foreground">
          ClipOps opens cash-out; you confirm withdrawal. Performance feeds the
          learning engine after 50–100 clips.
        </p>
      </div>

      <div className="rounded-lg border border-border bg-card p-4">
        <div className="text-sm text-muted-foreground">Payout ready total</div>
        <div className="text-2xl font-bold">
          ${analytics?.earnings.payout_ready_total ?? 0}
        </div>
        <a
          className="mt-3 inline-flex rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground"
          href="https://www.contentrewards.com"
          target="_blank"
          rel="noreferrer"
        >
          Open Cash-out
        </a>
        <p className="mt-2 text-xs text-muted-foreground">
          You personally confirm the transfer (Whop after review).
        </p>
      </div>

      <div className="rounded-lg border border-border bg-card p-4 space-y-2">
        <h2 className="text-sm font-semibold">Learning engine</h2>
        <p className="text-xs text-muted-foreground">
          {learning?.clip_count ?? 0} clips recorded
          {learning?.ready_to_learn ? " — ready to adjust production" : ""}
        </p>
        <ul className="list-disc pl-4 text-sm">
          {(learning?.recommendations || []).map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
        <div className="overflow-auto pt-2">
          <table className="w-full text-left text-xs">
            <thead className="text-muted-foreground">
              <tr>
                <th className="py-1">Account</th>
                <th>Style</th>
                <th>Length</th>
                <th>Hook</th>
                <th>Avg views</th>
                <th>n</th>
              </tr>
            </thead>
            <tbody>
              {(learning?.cohorts || []).map((c, i) => (
                <tr key={i} className="border-t border-border">
                  <td className="py-1">{c.account}</td>
                  <td>{c.editing_style}</td>
                  <td>{c.clip_length_band}</td>
                  <td>{c.hook_type}</td>
                  <td>{c.avg_views}</td>
                  <td>{c.n}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
