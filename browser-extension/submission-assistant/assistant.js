/** Submission assistant — highlight Submit; copy package fields; never click Submit. */

function clipopsHighlightSubmit() {
  const candidates = Array.from(
    document.querySelectorAll("button, a, [role='button'], input[type='submit']")
  );
  const submit = candidates.find((el) =>
    /submit|send for review|send submission/i.test(textOf(el))
  );
  if (!submit) {
    return { found: false };
  }
  submit.style.outline = "3px solid #3dd6c6";
  submit.style.boxShadow = "0 0 0 4px rgba(61,214,198,0.35)";
  const badge = document.createElement("div");
  badge.id = "clipops-submit-hint";
  badge.textContent =
    "ClipOps: Submit is highlighted — YOU click it. ClipOps will not auto-submit.";
  Object.assign(badge.style, {
    position: "fixed",
    bottom: "16px",
    right: "16px",
    zIndex: "2147483647",
    background: "#14181f",
    color: "#f2f4f7",
    border: "1px solid #2a3140",
    borderRadius: "8px",
    padding: "10px 12px",
    font: "12px/1.4 sans-serif",
    maxWidth: "280px",
  });
  document.getElementById("clipops-submit-hint")?.remove();
  document.body.appendChild(badge);
  submit.scrollIntoView({ behavior: "smooth", block: "center" });
  return { found: true, label: textOf(submit) };
}

/**
 * Copy a posting/submission package to clipboard and optionally fill visible text fields.
 * Never clicks Submit / Join / Cash-out.
 */
function clipopsAssistSubmissionPackage(pkg = {}) {
  const lines = [
    pkg.caption || "",
    pkg.tiktok_url ? `TikTok URL: ${pkg.tiktok_url}` : "",
    pkg.account ? `Account: ${pkg.account}` : "",
    pkg.campaign ? `Campaign: ${pkg.campaign}` : "",
    pkg.notes || "",
  ].filter(Boolean);
  const text = lines.join("\n\n").trim();
  const filled = [];

  if (text && navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(text).catch(() => {});
  }

  // Soft prefill: only empty textareas / url inputs that look like submission fields
  const fields = Array.from(
    document.querySelectorAll("textarea, input[type='text'], input[type='url'], input:not([type])")
  );
  for (const el of fields) {
    if (el.disabled || el.readOnly) continue;
    if ((el.value || "").trim()) continue;
    const label = (
      el.getAttribute("placeholder") ||
      el.getAttribute("name") ||
      el.getAttribute("aria-label") ||
      ""
    ).toLowerCase();
    if (pkg.tiktok_url && /url|link|tiktok|post/.test(label)) {
      el.value = pkg.tiktok_url;
      el.dispatchEvent(new Event("input", { bubbles: true }));
      filled.push("tiktok_url");
    } else if (pkg.caption && /caption|description|comment|note|message/.test(label)) {
      el.value = pkg.caption;
      el.dispatchEvent(new Event("input", { bubbles: true }));
      filled.push("caption");
    }
  }

  const hint = document.createElement("div");
  hint.id = "clipops-package-hint";
  hint.textContent = text
    ? `ClipOps copied package to clipboard${filled.length ? ` and filled: ${filled.join(", ")}` : ""}. Review, then YOU click Submit.`
    : "ClipOps: no package fields provided.";
  Object.assign(hint.style, {
    position: "fixed",
    bottom: "64px",
    right: "16px",
    zIndex: "2147483647",
    background: "#14181f",
    color: "#f2f4f7",
    border: "1px solid #2a3140",
    borderRadius: "8px",
    padding: "10px 12px",
    font: "12px/1.4 sans-serif",
    maxWidth: "300px",
  });
  document.getElementById("clipops-package-hint")?.remove();
  document.body.appendChild(hint);

  return { copied: Boolean(text), filled, submit_auto: false };
}
