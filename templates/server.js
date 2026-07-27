/**
 * ClipOps Remotion render service — real caption overlay burns onto base cuts.
 * POST /render { style, hookText, caption, inputVideo, outputPath }
 * Returns { rendered_path } when the file exists so FFmpeg pipeline can prefer it.
 */
const { execFileSync } = require("child_process");
const path = require("path");
const fs = require("fs");
const express = require("express");
const { bundle } = require("@remotion/bundler");
const { renderMedia, selectComposition, getVideoMetadata } = require("@remotion/renderer");

const STYLES = {
  dramatic: "Dramatic",
  educational: "Educational",
  commentary: "Commentary",
};

const port = Number(process.env.PORT || 3100);
const publicBase = process.env.REMOTION_PUBLIC_URL || `http://127.0.0.1:${port}`;

const app = express();
app.use(express.json({ limit: "4mb" }));

let bundleLocationPromise = null;

function getBundle() {
  if (!bundleLocationPromise) {
    const entry = path.join(__dirname, "src", "index.ts");
    bundleLocationPromise = bundle({
      entryPoint: entry,
      webpackOverride: (config) => config,
    }).catch((err) => {
      bundleLocationPromise = null;
      throw err;
    });
  }
  return bundleLocationPromise;
}

function probeDurationSeconds(filePath) {
  try {
    const out = execFileSync(
      "ffprobe",
      [
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        filePath,
      ],
      { encoding: "utf8" }
    );
    const n = parseFloat(String(out).trim());
    return Number.isFinite(n) ? n : null;
  } catch {
    return null;
  }
}

/** Remotion OffthreadVideo only accepts http(s) — proxy local files. */
app.get("/local-file", (req, res) => {
  const raw = String(req.query.path || "");
  if (!raw) return res.status(400).send("path required");
  let target;
  try {
    target = path.resolve(raw);
  } catch {
    return res.status(400).send("bad path");
  }
  if (!fs.existsSync(target) || !fs.statSync(target).isFile()) {
    return res.status(404).send("not found");
  }
  const ext = path.extname(target).toLowerCase();
  if (![".mp4", ".webm", ".mov", ".mkv", ".m4v"].includes(ext)) {
    return res.status(400).send("unsupported type");
  }
  return res.sendFile(target);
});

function httpVideoUrl(absPath) {
  return `${publicBase}/local-file?path=${encodeURIComponent(path.resolve(absPath))}`;
}

app.get("/health", async (_req, res) => {
  try {
    await getBundle();
    res.json({ ok: true, templates: Object.keys(STYLES), bundled: true });
  } catch (e) {
    res.status(500).json({ ok: false, error: String(e) });
  }
});

app.post("/render", async (req, res) => {
  const started = Date.now();
  try {
    const { style, hookText, caption, inputVideo, outputPath } = req.body || {};
    const compositionId = STYLES[style];
    if (!compositionId) {
      return res.status(400).json({ error: "unknown_style", allowed: Object.keys(STYLES) });
    }
    if (!inputVideo || !outputPath) {
      return res.status(400).json({ error: "inputVideo_and_outputPath_required" });
    }
    if (!fs.existsSync(inputVideo)) {
      return res.status(400).json({ error: "input_video_missing", inputVideo });
    }

    const out = path.resolve(outputPath);
    fs.mkdirSync(path.dirname(out), { recursive: true });

    const serveUrl = await getBundle();
    const videoSrc = httpVideoUrl(inputVideo);

    let fps = 30;
    let seconds = probeDurationSeconds(inputVideo) || 20;
    try {
      const meta = await getVideoMetadata(videoSrc);
      fps = meta.fps || fps;
      if (meta.durationInSeconds) seconds = meta.durationInSeconds;
    } catch (metaErr) {
      console.warn("getVideoMetadata fallback", metaErr);
    }
    const durationInFrames = Math.max(15, Math.round(seconds * fps));

    const inputProps = {
      styleName: style,
      hookText: hookText || "",
      caption: caption || "",
      videoSrc,
    };

    const composition = await selectComposition({
      serveUrl,
      id: compositionId,
      inputProps,
    });

    await renderMedia({
      composition: {
        ...composition,
        durationInFrames,
        fps,
        width: 1080,
        height: 1920,
      },
      serveUrl,
      codec: "h264",
      outputLocation: out,
      inputProps,
      overwrite: true,
    });

    if (!fs.existsSync(out) || fs.statSync(out).size === 0) {
      return res.status(500).json({ error: "render_produced_empty_file", outputPath: out });
    }

    return res.json({
      queued: false,
      rendered_path: out,
      style,
      durationInFrames,
      fps,
      elapsed_ms: Date.now() - started,
    });
  } catch (e) {
    console.error("Remotion render failed", e);
    return res.status(500).json({
      error: "render_failed",
      detail: String(e && e.message ? e.message : e),
    });
  }
});

app.listen(port, () => {
  console.log(`ClipOps Remotion render service on :${port}`);
  getBundle()
    .then(() => console.log("Remotion bundle ready"))
    .catch((e) => console.error("Bundle warm-up failed", e));
});
