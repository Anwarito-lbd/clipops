/** Payout watcher — detect ready balances on CR/Whop cash-out pages. */

function clipopsWatchPayout() {
  const text = document.body.innerText || "";
  const ready =
    /ready for (withdrawal|payout)|available to (withdraw|cash out)|payout ready/i.test(
      text
    );
  const amountMatch =
    text.match(/(?:£|\$|USD|CAD)\s*([\d,]+(?:\.\d{2})?)/) ||
    text.match(/([\d,]+(?:\.\d{2})?)\s*(?:USD|CAD|GBP)/i);
  const amount = amountMatch
    ? parseFloat(amountMatch[1].replace(/,/g, ""))
    : null;

  let cashout = null;
  document.querySelectorAll("a[href], button").forEach((el) => {
    if (/cash.?out|withdraw|payout/i.test(textOf(el) + (el.href || ""))) {
      cashout = el.href || location.href;
    }
  });

  return {
    ready,
    amount,
    currency: /£|GBP/i.test(text) ? "GBP" : "USD",
    cashout_url: cashout || location.href,
  };
}

function clipopsHighlightCashout() {
  const candidates = Array.from(
    document.querySelectorAll("button, a, [role='button']")
  );
  const btn = candidates.find((el) =>
    /cash.?out|withdraw|get paid/i.test(textOf(el))
  );
  if (!btn) return { found: false };
  btn.style.outline = "3px solid #e8b84a";
  const badge = document.createElement("div");
  badge.id = "clipops-cashout-hint";
  badge.textContent =
    "ClipOps: Cash-out is highlighted — YOU confirm the transfer.";
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
  document.getElementById("clipops-cashout-hint")?.remove();
  document.body.appendChild(badge);
  return { found: true };
}
