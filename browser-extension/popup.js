const logEl = document.getElementById("log");

function log(msg) {
  logEl.textContent = typeof msg === "string" ? msg : JSON.stringify(msg, null, 2);
}

async function getStored() {
  const local = await chrome.storage.local.get({
    apiBase: "http://127.0.0.1:8000",
    lastDiscoveredId: "",
  });
  if (local.apiBase) return local;
  return chrome.storage.sync.get({
    apiBase: "http://127.0.0.1:8000",
    lastDiscoveredId: "",
  });
}

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

async function sendTab(type) {
  const tab = await activeTab();
  if (!tab?.id) throw new Error("No active tab");
  try {
    return await chrome.tabs.sendMessage(tab.id, { type });
  } catch (e) {
    throw new Error(
      "No ClipOps content script on this tab. Open a Content Rewards page first, then retry. " +
        String(e)
    );
  }
}

async function apiProxy(path, method, body) {
  return chrome.runtime.sendMessage({
    type: "API_PROXY",
    path,
    method,
    body,
  });
}

document.getElementById("scan").onclick = async () => {
  try {
    const res = await sendTab("SCAN_CAMPAIGNS");
    if (!res?.ok) throw new Error(res?.error || "scan failed");
    const n = (res.campaigns || []).length;
    if (!n) {
      log(
        "Scan found 0 campaigns on this page. Open the CR campaign list, or paste the brief in Operator Mode."
      );
      return;
    }
    const push = await apiProxy("/api/operator/discover", "POST", {
      campaigns: res.campaigns,
      source: "browser_extension",
    });
    log(
      push.ok
        ? `Scanned ${n} → ingested. Open http://localhost:3000/operator`
        : push
    );
  } catch (e) {
    log(String(e));
  }
};

document.getElementById("brief").onclick = async () => {
  try {
    const res = await sendTab("EXTRACT_BRIEF");
    const cfg = await getStored();
    let id = cfg.lastDiscoveredId;
    if (!id) {
      const list = await apiProxy("/api/operator/top3", "GET");
      id = list.data?.[0]?.id;
      if (!id) throw new Error("No discovered campaign — scan first, then approve one.");
      await chrome.storage.local.set({ lastDiscoveredId: id });
      await chrome.storage.sync.set({ lastDiscoveredId: id });
    }
    // Prefer the brief extractor's classified resources over the bare asset
    // list — it finds "Resources" cards pointing at Drive/Dropbox, which is
    // where footage actually lives.
    const found = res.brief.resources || [];
    const urls = found.length ? found.map((r) => r.url) : res.assets || [];
    const push = await apiProxy("/api/operator/brief", "POST", {
      discovered_id: id,
      brief_text: res.brief.brief_text,
      asset_urls: urls,
      external_url: res.brief.external_url,
    });
    const hosts = found.filter((r) => r.kind === "file_host" || r.kind === "direct_media");
    log(
      (push.ok ? "Brief saved. " : JSON.stringify(push) + " ") +
        `${urls.length} link(s) found` +
        (hosts.length
          ? ` — footage likely at: ${hosts.slice(0, 3).map((h) => h.url).join(", ")}`
          : " — no footage host detected, check the Resources link manually")
    );
  } catch (e) {
    log(String(e));
  }
};

/**
 * Pull briefs from every open campaign tab in one pass.
 *
 * The discover-page scan only sees campaign cards, which carry no hashtags,
 * duration limits or disclosure wording. Those live on each campaign's own
 * page, so producing clips from card data alone means enforcing invented
 * rules. Opening the campaigns you care about in tabs and running this once
 * captures the real requirements without visiting them one at a time.
 */
document.getElementById("briefAll").onclick = async () => {
  try {
    const tabs = await chrome.tabs.query({
      url: ["https://*.contentrewards.com/*", "https://contentrewards.com/*", "https://*.whop.com/*"],
    });
    if (!tabs.length) {
      log("No Content Rewards tabs open. Open each campaign you want in its own tab, then retry.");
      return;
    }

    const lines = [];
    let ok = 0;
    for (const tab of tabs) {
      let res;
      try {
        res = await chrome.tabs.sendMessage(tab.id, { type: "EXTRACT_BRIEF" });
      } catch {
        lines.push(`skip  ${(tab.title || tab.url || "").slice(0, 44)} — no content script`);
        continue;
      }
      const brief = res?.brief;
      if (!brief?.brief_text) {
        lines.push(`skip  ${(tab.title || "").slice(0, 44)} — no text captured`);
        continue;
      }
      // A length check cannot tell these apart: the discover feed is far LONGER
      // than any single campaign page. The reliable signal is how many "Join
      // Campaign" buttons the page has - a feed has one per listing.
      const joins = (brief.brief_text.match(/join\s+campaign/gi) || []).length;
      if (joins > 1) {
        lines.push(
          `skip  ${(tab.title || "").slice(0, 40)} — feed page (${joins} campaigns), not a brief`
        );
        continue;
      }

      // Match this page to a discovered campaign by its URL.
      const found = await apiProxy(
        `/api/operator/discovered/by-url?url=${encodeURIComponent(brief.external_url)}`,
        "GET"
      );
      const id = found?.data?.id;
      if (!id) {
        lines.push(`skip  ${(tab.title || "").slice(0, 44)} — not in ClipOps, scan first`);
        continue;
      }

      const resources = brief.resources || [];
      const push = await apiProxy("/api/operator/brief", "POST", {
        discovered_id: id,
        brief_text: brief.brief_text,
        asset_urls: resources.map((r) => r.url),
        external_url: brief.external_url,
      });
      const hosts = resources.filter(
        (r) => r.kind === "file_host" || r.kind === "direct_media"
      );
      lines.push(
        `${push.ok ? "OK   " : "FAIL "} ${(tab.title || "").slice(0, 40)} — ` +
          `${resources.length} link(s), ${hosts.length} footage host(s)`
      );
      if (push.ok) ok++;
    }
    log(`${ok}/${tabs.length} briefs saved\n\n` + lines.join("\n"));
  } catch (e) {
    log(String(e));
  }
};

document.getElementById("submit").onclick = async () => {
  log(await sendTab("HIGHLIGHT_SUBMIT"));
};

document.getElementById("package").onclick = async () => {
  try {
    const tab = await activeTab();
    if (!tab?.id) throw new Error("No active tab");
    const text = await navigator.clipboard.readText().catch(() => "");
    const pkg = {
      caption: text || "",
      notes: "Paste caption/TikTok URL from ClipOps Exports if clipboard empty.",
    };
    const res = await chrome.tabs.sendMessage(tab.id, {
      type: "ASSIST_SUBMISSION_PACKAGE",
      package: pkg,
    });
    log(res);
  } catch (e) {
    log(String(e));
  }
};

document.getElementById("payout").onclick = async () => {
  try {
    const res = await sendTab("WATCH_PAYOUT");
    if (res.ready && res.amount) {
      const push = await apiProxy("/api/operator/payout-watch", "POST", {
        amount: res.amount,
        currency: res.currency || "USD",
        cashout_url: res.cashout_url,
      });
      log(push);
    } else {
      log(res);
    }
  } catch (e) {
    log(String(e));
  }
};

document.getElementById("cashout").onclick = async () => {
  log(await sendTab("HIGHLIGHT_CASHOUT"));
};
