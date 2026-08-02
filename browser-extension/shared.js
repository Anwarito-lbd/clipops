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

function scaleMoney(num, suffix) {
  const value = parseFloat(String(num).replace(/,/g, ""));
  if (!suffix) return value;
  const s = String(suffix).toLowerCase();
  if (s === "k") return value * 1000;
  if (s === "m") return value * 1000000;
  return value;
}

// Mirrors packages/campaign_parser/parser.py. The amount must sit adjacent to the
// keyword — matching forward across prose used to capture the first stray number
// ("$2 CPM ... August 25th launch" -> 25, "$1 CPM ... $658/$10,000" -> 658).
const CPM_PATTERNS = [
  /[\$£€]\s*([\d]+(?:\.\d+)?)\s*(?:\/|per\s+)?\s*CPM\b/i,
  // Denominator must be an explicit 1000/1K — a bare "1" matches brief typos
  // like "earn $4 per 1 views" when the real rate is $3/1K.
  /[\$£€]\s*([\d]+(?:\.\d+)?)\s*(?:\/|per\s+)\s*(?:1[,.]?000|1\s*k)\b/i,
  /\bCPM\b\s*(?:of|is|:|=|-)\s*[\$£€]?\s*([\d]+(?:\.\d+)?)/i,
  /reward\s*rate\s*(?:of|is|:|=|-)\s*[\$£€]?\s*([\d]+(?:\.\d+)?)/i,
];

/** Every distinct rate in the text — more than one means merged campaign cards. */
function distinctRates(text) {
  const found = [];
  for (const pattern of CPM_PATTERNS) {
    const global = new RegExp(pattern.source, "gi");
    let m;
    while ((m = global.exec(String(text))) !== null) {
      const value = parseFloat(m[1]);
      if (value > 0 && value <= CPM_MAX && !found.includes(value)) found.push(value);
    }
  }
  return found.sort((a, b) => a - b);
}

/** True when one scraped card appears to hold more than one campaign. */
function looksLikeMultipleCampaigns(text) {
  if (distinctRates(text).length > 1) return true;
  return (String(text).match(/join\s+campaign/gi) || []).length > 1;
}

const BUDGET_PROGRESS =
  /[\$£€]\s*([\d,]+(?:\.\d+)?)\s*([km])?\s*\/\s*[\$£€]\s*([\d,]+(?:\.\d+)?)\s*([km])?/i;

const BUDGET_PATTERNS = [
  /[\$£€]?\s*([\d,]+(?:\.\d+)?)\s*([km])?\s*[\$£€]?\s*(?:total\s+)?budget\b/i,
  /\bbudget\b\s*(?:of|is|:|=|-)\s*[\$£€]?\s*([\d,]+(?:\.\d+)?)\s*([km])?/i,
];

// A rate outside this range is a parse artifact, not a real CPM.
const CPM_MAX = 100;

function extractCpm(text) {
  for (const pattern of CPM_PATTERNS) {
    const m = String(text).match(pattern);
    if (m) {
      const value = parseFloat(m[1]);
      if (value > 0 && value <= CPM_MAX) return value;
    }
  }
  return null;
}

/** Returns { total, utilised } — either may be null. */
function extractBudget(text) {
  const prog = String(text).match(BUDGET_PROGRESS);
  if (prog) {
    const used = scaleMoney(prog[1], prog[2]);
    const total = scaleMoney(prog[3], prog[4]);
    if (total > 0 && used <= total) return { total, utilised: used };
  }
  for (const pattern of BUDGET_PATTERNS) {
    const m = String(text).match(pattern);
    if (m) {
      const total = scaleMoney(m[1], m[2]);
      if (total > 0) return { total, utilised: null };
    }
  }
  return { total: null, utilised: null };
}

function parsePct(text) {
  const m = String(text).match(/(\d{1,3})\s*%/);
  return m ? parseFloat(m[1]) : null;
}
