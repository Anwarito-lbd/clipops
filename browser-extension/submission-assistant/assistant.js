/** Submission assistant — highlight Submit; never click it. */

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
