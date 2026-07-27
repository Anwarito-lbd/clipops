/**
 * Remotion template registry for ClipOps account styles.
 * dramatic / educational / commentary compositions render animated captions,
 * progress bars, hooks, and logos over FFmpeg base cuts.
 */
const express = require("express");

const app = express();
app.use(express.json({ limit: "2mb" }));

const STYLES = ["dramatic", "educational", "commentary"];

app.get("/health", (_req, res) => {
  res.json({ ok: true, templates: STYLES });
});

app.post("/render", async (req, res) => {
  const { style, hookText, caption, inputVideo, outputPath } = req.body || {};
  if (!STYLES.includes(style)) {
    return res.status(400).json({ error: "unknown_style" });
  }
  // Phase 1: acknowledge job; wire @remotion/renderer when compositions are filled in.
  res.json({
    queued: true,
    style,
    hookText,
    caption,
    inputVideo,
    outputPath,
    note: "Use templates/{style}/Composition.tsx with Remotion CLI for full caption burn-in",
  });
});

const port = process.env.PORT || 3100;
app.listen(port, () => {
  console.log(`ClipOps Remotion service on :${port}`);
});
