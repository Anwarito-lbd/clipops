/** Content script entry — wires scanner modules to the background worker. */

(function () {
  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    (async () => {
      try {
        if (msg.type === "SCAN_CAMPAIGNS") {
          sendResponse({ ok: true, campaigns: clipopsScanCampaigns() });
        } else if (msg.type === "EXTRACT_BRIEF") {
          sendResponse({
            ok: true,
            brief: clipopsExtractBrief(),
            assets: clipopsCollectAssets(),
          });
        } else if (msg.type === "HIGHLIGHT_SUBMIT") {
          sendResponse({ ok: true, ...clipopsHighlightSubmit() });
        } else if (msg.type === "ASSIST_SUBMISSION_PACKAGE") {
          sendResponse({
            ok: true,
            ...clipopsAssistSubmissionPackage(msg.package || {}),
          });
        } else if (msg.type === "WATCH_PAYOUT") {
          sendResponse({ ok: true, ...clipopsWatchPayout() });
        } else if (msg.type === "HIGHLIGHT_CASHOUT") {
          sendResponse({ ok: true, ...clipopsHighlightCashout() });
        } else {
          sendResponse({ ok: false, error: "unknown_type" });
        }
      } catch (e) {
        sendResponse({ ok: false, error: String(e) });
      }
    })();
    return true;
  });

  // Soft banner so the operator knows ClipOps is assisting — not auto-clicking
  if (!document.getElementById("clipops-operator-banner")) {
    const b = document.createElement("div");
    b.id = "clipops-operator-banner";
    b.textContent =
      "ClipOps Operator active — reads this tab only. Final Join / Post / Submit / Cash-out clicks are yours.";
    Object.assign(b.style, {
      position: "fixed",
      top: "0",
      left: "0",
      right: "0",
      zIndex: "2147483646",
      background: "rgba(20,24,31,0.92)",
      color: "#a8b0bd",
      font: "11px/1.4 sans-serif",
      padding: "6px 12px",
      borderBottom: "1px solid #2a3140",
    });
    document.documentElement.appendChild(b);
  }
})();
