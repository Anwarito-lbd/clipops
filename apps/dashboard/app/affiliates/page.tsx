"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/utils";

type Product = {
  id: string;
  name: string;
  product_url: string;
  affiliate_url: string;
  affiliate_tag: string | null;
  niche: string | null;
  talking_points: string[];
  disclosure: string;
};

type Account = {
  id: string;
  platform: string;
  display_name: string;
  handle: string;
};

export default function AffiliatesPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [tag, setTag] = useState("");
  const [niche, setNiche] = useState("gadgets");
  const [points, setPoints] = useState("great value, easy to use");
  const [bio, setBio] = useState("");
  const [pitch, setPitch] = useState("");
  const [selectedProduct, setSelectedProduct] = useState("");
  const [platform, setPlatform] = useState("twitter");

  async function load() {
    setProducts(await api("/api/affiliates/products"));
    setAccounts(await api("/api/accounts"));
  }

  useEffect(() => {
    load().catch((e) => setMsg(String(e)));
  }, []);

  async function addProduct() {
    if (!name || !url) {
      setMsg("Name and product URL required");
      return;
    }
    await api("/api/affiliates/products", {
      method: "POST",
      body: JSON.stringify({
        name,
        product_url: url,
        affiliate_tag: tag || null,
        niche,
        talking_points: points.split(",").map((s) => s.trim()).filter(Boolean),
      }),
    });
    setName("");
    setUrl("");
    setMsg("Product saved");
    await load();
  }

  async function makeBio() {
    const twitter = accounts.find((a) => a.platform === "twitter");
    const res = await api<{ bio: string }>("/api/affiliates/bio", {
      method: "POST",
      body: JSON.stringify({
        platform,
        social_account_id: twitter?.id,
        display_name: twitter?.display_name,
        niche,
        affiliate_product_id: selectedProduct || undefined,
      }),
    });
    setBio(res.bio);
    setMsg("Bio ready — paste into your profile");
  }

  async function makePitch() {
    if (!selectedProduct) {
      setMsg("Select a product first");
      return;
    }
    const res = await api<{ body: string; manual_gate: string }>("/api/affiliates/pitch", {
      method: "POST",
      body: JSON.stringify({ product_id: selectedProduct, platform }),
    });
    setPitch(res.body);
    setMsg(res.manual_gate);
  }

  async function scheduleAndFire() {
    if (!selectedProduct) {
      setMsg("Select a product first");
      return;
    }
    await api("/api/affiliates/schedules", {
      method: "POST",
      body: JSON.stringify({
        product_id: selectedProduct,
        platform,
        times_per_day: 2,
      }),
    });
    const res = await api<{ count: number; note: string }>(
      "/api/affiliates/schedules/run-due?force=true",
      {
        method: "POST",
        body: "{}",
      },
    );
    setMsg(`Fired ${res.count} PROMOTE NOW alert(s). ${res.note}`);
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">Affiliates</h1>
        <p className="text-sm text-muted-foreground">
          MoneyPrinterV2-inspired: store Amazon affiliate links, build bios, draft
          pitches, schedule promote reminders. You post — no Twitter browser bot,
          no cold email.
        </p>
      </div>
      {msg && <p className="text-xs text-muted-foreground">{msg}</p>}

      <div className="rounded-lg border border-border bg-card p-4 space-y-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Add affiliate product
        </h2>
        <div className="flex flex-wrap gap-2">
          <input
            className="rounded-md border border-border bg-background px-2 py-1.5 text-sm"
            placeholder="Product name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <input
            className="min-w-[220px] flex-1 rounded-md border border-border bg-background px-2 py-1.5 text-sm"
            placeholder="Amazon product URL"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
          <input
            className="rounded-md border border-border bg-background px-2 py-1.5 text-sm"
            placeholder="tag= your-20"
            value={tag}
            onChange={(e) => setTag(e.target.value)}
          />
          <input
            className="rounded-md border border-border bg-background px-2 py-1.5 text-sm"
            placeholder="niche"
            value={niche}
            onChange={(e) => setNiche(e.target.value)}
          />
          <input
            className="min-w-[180px] flex-1 rounded-md border border-border bg-background px-2 py-1.5 text-sm"
            placeholder="talking points (comma)"
            value={points}
            onChange={(e) => setPoints(e.target.value)}
          />
          <button
            onClick={addProduct}
            className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground"
          >
            Save
          </button>
        </div>
      </div>

      <div className="rounded-lg border border-border bg-card p-4 space-y-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Products
        </h2>
        {products.map((p) => (
          <label
            key={p.id}
            className="flex cursor-pointer items-start gap-2 border-t border-border pt-2 text-sm"
          >
            <input
              type="radio"
              name="product"
              checked={selectedProduct === p.id}
              onChange={() => setSelectedProduct(p.id)}
            />
            <span>
              <span className="font-medium">{p.name}</span>
              <div className="text-xs text-muted-foreground truncate max-w-xl">
                {p.affiliate_url}
              </div>
            </span>
          </label>
        ))}
        {!products.length && (
          <p className="text-xs text-muted-foreground">No products yet.</p>
        )}
      </div>

      <div className="flex flex-wrap gap-2 items-center">
        <select
          className="rounded-md border border-border bg-background px-2 py-1.5 text-sm"
          value={platform}
          onChange={(e) => setPlatform(e.target.value)}
        >
          <option value="twitter">X / Twitter</option>
          <option value="tiktok">TikTok</option>
          <option value="youtube">YouTube</option>
        </select>
        <button
          onClick={makeBio}
          className="rounded-md border border-border px-3 py-1.5 text-xs"
        >
          Build bio with affiliate link
        </button>
        <button
          onClick={makePitch}
          className="rounded-md border border-border px-3 py-1.5 text-xs"
        >
          Draft pitch
        </button>
        <button
          onClick={scheduleAndFire}
          className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground"
        >
          Schedule + fire PROMOTE NOW
        </button>
      </div>

      {bio && (
        <div className="rounded-lg border border-border bg-card p-4 space-y-2">
          <h2 className="text-sm font-semibold">Bio (paste into profile)</h2>
          <pre className="whitespace-pre-wrap text-sm">{bio}</pre>
          <button
            className="rounded-md border border-border px-2 py-1 text-xs"
            onClick={() => navigator.clipboard.writeText(bio)}
          >
            Copy bio
          </button>
        </div>
      )}

      {pitch && (
        <div className="rounded-lg border border-border bg-card p-4 space-y-2">
          <h2 className="text-sm font-semibold">Pitch (you post)</h2>
          <pre className="whitespace-pre-wrap text-sm">{pitch}</pre>
          <button
            className="rounded-md border border-border px-2 py-1 text-xs"
            onClick={() => navigator.clipboard.writeText(pitch)}
          >
            Copy pitch
          </button>
          <a
            className="ml-2 rounded-md border border-border px-2 py-1 text-xs"
            href={platform === "youtube" ? "https://studio.youtube.com" : platform === "tiktok" ? "https://www.tiktok.com" : "https://x.com"}
            target="_blank"
            rel="noreferrer"
          >
            Open {platform}
          </a>
        </div>
      )}
    </div>
  );
}
