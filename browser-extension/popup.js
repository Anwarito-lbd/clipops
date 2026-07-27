const logEl = document.getElementById("log");

function log(msg) {
  logEl.textContent = typeof msg === "string" ? msg : JSON.stringify(msg, null, 2);
}

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

async function sendTab(type) {
  const tab = await activeTab();
  if (!tab?.id) throw new Error("No active tab");
  return chrome.tabs.sendMessage(tab.id, { type });
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
    if (!res.ok) throw new Error(res.error || "scan failed");
    const push = await apiProxy("/api/operator/discover", "POST", {
      campaigns: res.campaigns,
      source: "browser_extension",
    });
    log(push.ok ? push.data : push);
  } catch (e) {
    log(String(e));
  }
};

document.getElementById("brief").onclick = async () => {
  try {
    const res = await sendTab("EXTRACT_BRIEF");
    const cfg = await chrome.storage.sync.get({ lastDiscoveredId: "" });
    if (!cfg.lastDiscoveredId) {
      // Ask API for latest top3 / approved item
      const list = await apiProxy("/api/operator/top3", "GET");
      const id = list.data?.[0]?.id;
      if (!id) throw new Error("No discovered campaign in ClipOps — scan first, then approve one.");
      await chrome.storage.sync.set({ lastDiscoveredId: id });
      cfg.lastDiscoveredId = id;
    }
    const push = await apiProxy("/api/operator/brief", "POST", {
      discovered_id: cfg.lastDiscoveredId,
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
