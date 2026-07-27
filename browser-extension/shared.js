/** Shared helpers for ClipOps Operator extension */

const DEFAULT_API = "http://127.0.0.1:8000";

async function getConfig() {
  const data = await chrome.storage.sync.get({
    apiBase: DEFAULT_API,
    token: "",
    autoScan: true,
  });
  return data;
}

async function api(path, options = {}) {
  const cfg = await getConfig();
  if (!cfg.token) {
    throw new Error("Set ClipOps API token in extension options (login first).");
  }
  const headers = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${cfg.token}`,
    ...(options.headers || {}),
  };
  const res = await fetch(`${cfg.apiBase}${path}`, { ...options, headers });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json();
}

function textOf(el) {
  return (el?.innerText || el?.textContent || "").trim();
}

function parseMoney(text) {
  const m = String(text).match(/\$?\s*([\d,]+(?:\.\d+)?)/);
  return m ? parseFloat(m[1].replace(/,/g, "")) : null;
}

function parsePct(text) {
  const m = String(text).match(/(\d{1,3})\s*%/);
  return m ? parseFloat(m[1]) : null;
}
