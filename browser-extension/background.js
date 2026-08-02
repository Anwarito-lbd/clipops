chrome.runtime.onInstalled.addListener(() => {
  console.log("ClipOps Operator installed — local mode, manual gates enforced.");
});

async function readConfig() {
  const local = await chrome.storage.local.get({
    apiBase: "http://127.0.0.1:8000",
    token: "",
  });
  if (local.apiBase) return local;
  return chrome.storage.sync.get({
    apiBase: "http://127.0.0.1:8000",
    token: "",
  });
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "API_PROXY") {
    (async () => {
      try {
        const cfg = await readConfig();
        const headers = { "Content-Type": "application/json" };
        if (cfg.token) headers.Authorization = `Bearer ${cfg.token}`;
        const res = await fetch(`${cfg.apiBase}${msg.path}`, {
          method: msg.method || "GET",
          headers,
          body: msg.body ? JSON.stringify(msg.body) : undefined,
        });
        const data = await res.json().catch(() => ({}));
        sendResponse({ ok: res.ok, status: res.status, data });
      } catch (e) {
        sendResponse({ ok: false, error: String(e) });
      }
    })();
    return true;
  }
});
