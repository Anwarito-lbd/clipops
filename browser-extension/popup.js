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
    const push = await apiProxy("/api/operator/brief", "POST", {
      discovered_id: id,
      brief_text: res.brief.brief_text,
      asset_urls: res.assets,
      external_url: res.brief.external_url,
    });
    log(push.ok ? push.data : push);
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
