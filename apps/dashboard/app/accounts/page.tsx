"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/utils";

type Account = {
  id: string;
  platform: string;
  handle: string;
  display_name: string;
  style: string | null;
  is_active: boolean;
  preferred_clip_length: string | null;
};

export default function AccountsPage() {
  const [rows, setRows] = useState<Account[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [handle, setHandle] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [platform, setPlatform] = useState("tiktok");
  const [style, setStyle] = useState("dramatic");

  async function load() {
    setRows(await api<Account[]>("/api/accounts"));
  }

  useEffect(() => {
    load().catch((e) => setMsg(String(e)));
  }, []);

  async function save() {
    if (!handle || !displayName) {
      setMsg("Handle and display name required");
      return;
    }
    await api("/api/accounts", {
      method: "POST",
      body: JSON.stringify({
        platform,
        handle,
        display_name: displayName,
        style: platform === "content_rewards" ? null : style,
        is_active: true,
      }),
    });
    setMsg("Saved");
    setHandle("");
    setDisplayName("");
    await load();
  }

  const tt = rows.filter((r) => r.platform === "tiktok");
  const yt = rows.filter((r) => r.platform === "youtube");
  const tw = rows.filter((r) => r.platform === "twitter" || r.platform === "x");
  const cr = rows.filter((r) => r.platform === "content_rewards");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">Accounts</h1>
        <p className="text-sm text-muted-foreground">
          Link 3 TikTok + 3 YouTube posting accounts, X for affiliate promo, and
          your Content Rewards identity. You still press Post — ClipOps packages
          and reminds.
        </p>
      </div>
      {msg && <p className="text-xs text-muted-foreground">{msg}</p>}

      <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-4">
        <Section title={`TikTok (${tt.length}/3)`} rows={tt} />
        <Section title={`YouTube (${yt.length}/3)`} rows={yt} />
        <Section title={`X / Twitter (${tw.length})`} rows={tw} />
        <Section title="Content Rewards" rows={cr} />
      </div>

      <div className="rounded-lg border border-border bg-card p-4 space-y-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Add / update account
        </h2>
        <div className="flex flex-wrap gap-2">
          <select
            className="rounded-md border border-border bg-background px-2 py-1.5 text-sm"
            value={platform}
            onChange={(e) => setPlatform(e.target.value)}
          >
            <option value="tiktok">tiktok</option>
            <option value="youtube">youtube</option>
            <option value="twitter">twitter / X</option>
            <option value="content_rewards">content_rewards</option>
          </select>
          <select
            className="rounded-md border border-border bg-background px-2 py-1.5 text-sm"
            value={style}
            onChange={(e) => setStyle(e.target.value)}
          >
            <option value="dramatic">dramatic</option>
            <option value="educational">educational</option>
            <option value="commentary">commentary</option>
          </select>
          <input
            className="rounded-md border border-border bg-background px-2 py-1.5 text-sm"
            placeholder="handle"
            value={handle}
            onChange={(e) => setHandle(e.target.value)}
          />
          <input
            className="min-w-[180px] flex-1 rounded-md border border-border bg-background px-2 py-1.5 text-sm"
            placeholder="display name"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
          />
          <button
            onClick={save}
            className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}

function Section({ title, rows }: { title: string; rows: Account[] }) {
  return (
    <div className="rounded-lg border border-border bg-card p-4 space-y-2">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </h2>
      {rows.map((r) => (
        <div key={r.id} className="border-t border-border pt-2 text-sm">
          <div className="font-medium">{r.display_name}</div>
          <div className="text-xs text-muted-foreground">
            @{r.handle} · {r.style || "—"} · {r.is_active ? "active" : "off"}
          </div>
        </div>
      ))}
      {!rows.length && (
        <p className="text-xs text-muted-foreground">None yet — seeded on API start.</p>
      )}
    </div>
  );
}
