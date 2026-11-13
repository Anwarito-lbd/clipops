const state = {
  health: null,
  sessions: [],
  session: null,
  activeClipId: null,
  previewMode: "source",
  activeItab: "transcript",
  safeZoneOn: true,
};

const $ = (id) => document.getElementById(id);

function showBanner(msg) {
  const el = $("status-banner");
  if (!msg) {
    el.classList.add("hidden");
    el.textContent = "";
    return;
  }
  el.textContent = msg;
  el.classList.remove("hidden");
}

function fmtTimecode(sec) {
  const s = Math.max(0, Number(sec) || 0);
  const mins = Math.floor(s / 60);
  const rem = s - mins * 60;
  return `${String(mins).padStart(2, "0")}:${rem.toFixed(2).padStart(5, "0")}`;
}

function escHtml(str) {
  return String(str ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `HTTP ${res.status}`);
  }
  return res.json();
}

function decisionPill(decision) {
  const d = (decision || "PENDING").toUpperCase();
  if (d === "APPROVED") return `<span class="pill pill-green">APPROVED</span>`;
  if (d === "REJECTED") return `<span class="pill pill-red">REJECTED</span>`;
  return `<span class="pill pill-amber">PENDING</span>`;
}

function activeClip() {
  if (!state.session || !state.session.clips) return null;
  return state.session.clips.find((c) => c.clip_id === state.activeClipId) || state.session.clips[0] || null;
}

function renderHealth() {
  const e = state.health?.engines || {};
  const pills = [
    { label: "FFmpeg", ok: e.ffmpeg },
    { label: "PySceneDetect", ok: e.pyscenedetect },
    {
      label: e.whisperx ? "WhisperX" : e.faster_whisper ? "faster-whisper" : "ASR Fallback",
      ok: e.whisperx || e.faster_whisper,
    },
    { label: e.remotion ? "Remotion" : "Remotion (opt)", ok: e.remotion },
  ];
  $("engine-pills").innerHTML = pills
    .map((p) => `<span class="engine-pill ${p.ok ? "ok" : "warn"}">${p.ok ? "●" : "○"} ${p.label}</span>`)
    .join("");
}

function renderStepper() {
  const s = state.session;
  const steps = s?.steps || {};
  const map = {
    probe: s ? `${s.probe?.duration_sec || 0}s · ${s.probe?.width || "?"}x${s.probe?.height || "?"}` : "Waiting",
    transcribe: steps.transcribe ? `${s.transcript?.engine || "ok"} (${(s.transcript?.segments || []).length} segs)` : "Waiting",
    scenes: steps.scenes ? `${s.scenes?.engine || "ok"} (${(s.scenes?.scenes || []).length} cuts)` : "Waiting",
    score: steps.score ? `${(s.clips || []).length} ranked` : "Waiting",
    render: steps.render ? `${Object.keys(s.renders || {}).length} rendered` : "Dry-run ready",
  };
  document.querySelectorAll(".step").forEach((el) => {
    const key = el.dataset.step;
    el.classList.toggle("done", Boolean(steps[key]));
    const meta = $("meta-" + key);
    if (meta) meta.textContent = map[key] || "Waiting";
  });
}

function renderSessionsDropdown() {
  const sel = $("session-select");
  if (!state.sessions.length) {
    sel.innerHTML = `<option value="">No sessions yet</option>`;
    return;
  }
  sel.innerHTML = state.sessions
    .map(
      (s) =>
        `<option value="${s.session_id}" ${state.session?.session_id === s.session_id ? "selected" : ""}>${
          escHtml(s.title || s.session_id)
        }</option>`
    )
    .join("");
}

function renderProbeAndClips() {
  const s = state.session;
  if (!s) {
    $("probe-card").innerHTML = "No active session.";
    $("clip-count").textContent = "0 cuts";
    $("clip-list").innerHTML = "";
    return;
  }
  const p = s.probe || {};
  $("probe-card").innerHTML = `
    <div><strong>${escHtml(p.filename || "source.mp4")}</strong></div>
    <div>${p.duration_sec}s · ${p.width}×${p.height} @ ${p.fps || "?"}fps</div>
    <div>${p.video_codec || "?"} / ${p.audio_codec || "?"} · ${(p.bytes / 1024).toFixed(1)} KB</div>
  `;

  const clips = s.clips || [];
  $("clip-count").textContent = `${clips.length} cuts`;
  $("clip-list").innerHTML = clips
    .map((c) => {
      const active = c.clip_id === state.activeClipId ? "active" : "";
      const hasRender = Boolean(s.renders?.[c.clip_id]?.ok);
      const wpm = c.retention_pacing?.wpm ?? "?";
      return `
        <div class="clip-card ${active}" data-clip="${c.clip_id}">
          <div class="clip-top">
            <span class="clip-title">#${c.rank} · ${c.start_sec}s–${c.end_sec}s</span>
            <span class="pill pill-cyan">${c.total_score}</span>
          </div>
          <div class="clip-excerpt">${escHtml(c.transcript_excerpt)}</div>
          <div class="clip-tags">
            ${decisionPill(c.decision)}
            <span class="pill">${c.hook_type}</span>
            <span class="pill">${wpm} wpm</span>
            ${hasRender ? `<span class="pill pill-green">9:16 MP4</span>` : ""}
          </div>
        </div>
      `;
    })
    .join("");

  document.querySelectorAll(".clip-card").forEach((el) => {
    el.addEventListener("click", () => {
      state.activeClipId = el.dataset.clip;
      renderAll();
      const clip = activeClip();
      const video = $("video-player");
      if (clip && video && state.previewMode === "source") {
        video.currentTime = Number(clip.start_sec || 0);
        syncPlayhead();
      }
    });
  });
}

function renderWaveAndHookCurve(s, totalDur) {
  const waveTrack = $("wave-hook-track");
  const bins = (s.probe?.waveform && s.probe.waveform.length ? s.probe.waveform : new Array(64).fill(0.28));
  const w = 1000;
  const h = 46;
  const barW = w / bins.length;

  const barsSvg = bins
    .map((v, i) => {
      const bh = Math.max(3, v * (h - 8));
      const x = i * barW + 1;
      const y = (h - bh) / 2;
      return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${Math.max(2, barW - 2.5).toFixed(1)}" height="${bh.toFixed(1)}" rx="1" fill="rgba(56,189,248,0.42)" />`;
    })
    .join("");

  // Build smooth SVG polyline for candidate hook & total score curve across time
  const clips = s.clips || [];
  let curveSvg = "";
  if (clips.length) {
    const pts = [];
    const sorted = [...clips].sort((a, b) => a.start_sec - b.start_sec);
    sorted.forEach((c) => {
      const midT = Math.min(totalDur, Math.max(0, (Number(c.start_sec) + Number(c.end_sec)) / 2));
      const score = Number(c.rank_report?.hook_score ?? c.total_score ?? 50);
      const px = (midT / totalDur) * w;
      const py = h - 5 - (Math.max(0, Math.min(100, score)) / 100) * (h - 10);
      pts.push({ x: px, y: py, score });
    });
    if (pts.length === 1) {
      pts.unshift({ x: 0, y: pts[0].y, score: pts[0].score });
      pts.push({ x: w, y: pts[0].y, score: pts[0].score });
    } else {
      pts.unshift({ x: 0, y: pts[0].y, score: pts[0].score });
      pts.push({ x: w, y: pts[pts.length - 1].y, score: pts[pts.length - 1].score });
    }
    const linePoints = pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
    const dots = pts
      .slice(1, -1)
      .map((p) => `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="4" fill="#f59e0b" stroke="#06090f" stroke-width="1.5" />`)
      .join("");
    curveSvg = `
      <polyline fill="none" stroke="#f59e0b" stroke-width="2" points="${linePoints}" />
      ${dots}
    `;
  }

  waveTrack.innerHTML = `<svg class="wave-svg" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">${barsSvg}${curveSvg}</svg>`;
}

function renderTimeline(s, clip) {
  const totalDur = Math.max(0.5, Number(s.probe?.duration_sec || 24));
  $("timeline-duration").textContent = `${totalDur.toFixed(2)}s`;

  // Ruler ticks
  const tickCount = 5;
  const ticks = [];
  for (let i = 0; i <= tickCount; i += 1) {
    const pct = (i / tickCount) * 100;
    const t = ((i / tickCount) * totalDur).toFixed(1);
    ticks.push(`<span class="ruler-tick" style="left:${pct.toFixed(1)}%">${t}s</span>`);
  }
  $("timeline-ruler").innerHTML = ticks.join("");

  // V1 Scenes
  const scenes = s.scenes?.scenes || [];
  $("scene-timeline").innerHTML = scenes.length
    ? scenes
        .map((sc, i) => {
          const span = Math.max(0.5, sc.end_sec - sc.start_sec);
          const pct = (span / totalDur) * 100;
          const isSel =
            clip &&
            Math.abs(sc.start_sec - clip.start_sec) < 0.35 &&
            Math.abs(sc.end_sec - clip.end_sec) < 0.35;
          return `<div class="scene-seg ${isSel ? "selected" : ""}" style="width:${pct.toFixed(2)}%" data-start="${sc.start_sec}" title="Jump to Scene ${i + 1}">S${i + 1} (${sc.start_sec}–${sc.end_sec}s)</div>`;
        })
        .join("")
    : `<div class="muted" style="padding:3px 6px;font-size:10px">Run Step 3 (PySceneDetect)</div>`;

  // A1 Audio + Hook Curve
  renderWaveAndHookCurve(s, totalDur);

  // T1 Active Cut Span
  if (clip) {
    const leftPct = Math.max(0, Math.min(100, (clip.start_sec / totalDur) * 100));
    const widthPct = Math.max(3, Math.min(100 - leftPct, ((clip.end_sec - clip.start_sec) / totalDur) * 100));
    const rej = clip.decision === "REJECTED" ? "rejected" : "";
    $("cut-span-track").innerHTML = `
      <div class="cut-span-bar ${rej}" style="left:${leftPct.toFixed(2)}%;width:${widthPct.toFixed(2)}%">
        <span>[IN ${clip.start_sec}s</span>
        <span>${clip.clip_id} (${clip.duration_sec}s)</span>
        <span>OUT ${clip.end_sec}s]</span>
      </div>
    `;
  } else {
    $("cut-span-track").innerHTML = "";
  }
}

function renderStage() {
  const s = state.session;
  const clip = activeClip();
  const video = $("video-player");
  const empty = $("video-empty");
  const overlay = $("safezone-overlay");

  if (!s) {
    video.style.display = "none";
    empty.style.display = "block";
    overlay.classList.add("hidden");
    $("scene-timeline").innerHTML = "";
    $("wave-hook-track").innerHTML = "";
    $("cut-span-track").innerHTML = "";
    $("timeline-duration").textContent = "0.0s";
    $("timecode-hud").textContent = "00:00.00 / 00:00.00";
    $("active-clip-badge").textContent = "No cut selected";
    return;
  }

  empty.style.display = "none";
  video.style.display = "block";

  const renderedUrl = clip ? s.renders?.[clip.clip_id]?.video_url : null;
  const showingRendered = state.previewMode === "rendered" && Boolean(renderedUrl);
  const targetUrl = showingRendered ? renderedUrl : s.source_media_url;
  if (video.dataset.src !== targetUrl) {
    video.src = targetUrl;
    video.dataset.src = targetUrl;
  }

  overlay.classList.toggle("hidden", !state.safeZoneOn);
  overlay.classList.toggle("mode-rendered", showingRendered);
  $("btn-safezone").classList.toggle("active", state.safeZoneOn);
  $("btn-safezone").textContent = `9:16 Safe Guides: ${state.safeZoneOn ? "ON" : "OFF"}`;

  renderTimeline(s, clip);

  if (clip) {
    $("active-clip-badge").textContent = `${clip.clip_id} · ${clip.rank_report?.predicted_performance || "MEDIUM"}`;
    $("inp-start").value = clip.start_sec;
    $("inp-end").value = clip.end_sec;
    $("inp-style").value = clip.style;
    $("inp-band").value = clip.duration_band;
    $("inp-hook").value = clip.hook_text || "";
  } else {
    $("active-clip-badge").textContent = "Run Step 4 to rank cuts";
  }
  syncPlayhead();
}

function renderInspector() {
  const s = state.session;
  const clip = activeClip();

  if (!s?.transcript) {
    $("tab-transcript").innerHTML = `<div class="muted">Run Step 2 (WhisperX / ASR) to inspect segments and word-level timestamps.</div>`;
  } else {
    const tr = s.transcript;
    const words = (tr.word_segments || []).slice(0, 96);
    $("tab-transcript").innerHTML = `
      <div class="kv-grid">
        <div class="kv"><div class="k">ASR Engine</div><div class="v">${escHtml(tr.engine || "asr")}</div></div>
        <div class="kv"><div class="k">Words Aligned</div><div class="v">${(tr.word_segments || []).length}</div></div>
      </div>
      ${(tr.segments || [])
        .map(
          (seg, idx) => `
          <div class="segment-item" data-seg-idx="${idx}" data-start="${Number(seg.start).toFixed(2)}" data-end="${Number(seg.end).toFixed(2)}">
            <div class="seg-time">${Number(seg.start).toFixed(2)}s – ${Number(seg.end).toFixed(2)}s · ${escHtml(seg.speaker || "SPEAKER_0")}</div>
            <div>${escHtml(seg.text)}</div>
          </div>`
        )
        .join("")}
      <div class="segment-item">
        <div class="seg-time">Interactive Word Timestamps (click any word to seek)</div>
        <div class="word-cloud">
          ${words
            .map(
              (w) =>
                `<span class="word-chip" data-start="${Number(w.start).toFixed(2)}" data-end="${Number(w.end).toFixed(2)}" title="${Number(w.start).toFixed(2)}s">${escHtml(w.word)}</span>`
            )
            .join("")}
        </div>
      </div>
    `;

    document.querySelectorAll("#tab-transcript [data-start]").forEach((el) => {
      el.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const video = $("video-player");
        if (video && state.previewMode === "source") {
          video.currentTime = Number(el.dataset.start || 0);
          syncPlayhead();
        }
      });
    });
  }

  if (!clip) {
    $("tab-scoring").innerHTML = `<div class="muted">Select or rank a candidate cut to inspect hook &amp; retention pacing scores.</div>`;
  } else {
    const r = clip.rank_report || {};
    const p = clip.retention_pacing || {};
    const dims = [
      ["Hook Opening", r.hook_score],
      ["Curiosity", r.curiosity_score],
      ["Conflict/Surprise", r.conflict_score],
      ["Emotion", r.emotion_score],
      ["Payoff", r.payoff_score],
      ["Clarity", r.clarity_score],
      ["Campaign Fit", r.campaign_fit],
    ];
    $("tab-scoring").innerHTML = `
      <div class="kv-grid">
        <div class="kv"><div class="k">Composite Score</div><div class="v">${clip.total_score}</div></div>
        <div class="kv"><div class="k">Pacing (${p.pacing_label || "N/A"})</div><div class="v">${p.wpm || 0} WPM</div></div>
        <div class="kv"><div class="k">3s Hook Density</div><div class="v">${p.hook_window_words_3s || 0} words</div></div>
        <div class="kv"><div class="k">Dead-Air Ratio</div><div class="v">${((p.dead_air_ratio || 0) * 100).toFixed(1)}%</div></div>
      </div>
      <div class="segment-item">
        <div class="seg-time">7-Dimension Hook Breakdown · ${escHtml(clip.hook_type)}</div>
        ${dims
          .map(
            ([label, val]) => `
            <div class="meter-row">
              <span class="meter-label">${label}</span>
              <div class="meter-bar"><div class="meter-fill" style="width:${Math.min(100, Number(val || 0))}%"></div></div>
              <span class="meter-val">${Number(val || 0).toFixed(0)}</span>
            </div>`
          )
          .join("")}
      </div>
      <div class="segment-item">
        <div class="seg-time">Generated Platform Caption</div>
        <pre class="code-box">${escHtml(clip.caption || "")}</pre>
      </div>
    `;
  }

  if (!clip) {
    $("tab-filtergraph").innerHTML = `<div class="muted">Select a cut and click Dry-Run Filtergraph [D] or Approve Cut [A].</div>`;
  } else {
    const dry = s.dry_runs?.[clip.clip_id];
    const ren = s.renders?.[clip.clip_id];
    const comp = clip.compliance || dry?.compliance_preview;
    $("tab-filtergraph").innerHTML = `
      <div class="kv-grid">
        <div class="kv"><div class="k">Approval Gate</div><div class="v">${clip.decision}</div></div>
        <div class="kv"><div class="k">Compliance</div><div class="v">${comp ? (comp.passed ? "PASS" : "FAIL") : "Pending"}</div></div>
      </div>
      ${
        comp
          ? `<div class="segment-item">
               <div class="seg-time">Compliance Checks (human_approval_manual_publish)</div>
               ${(comp.checks || [])
                 .map((c) => `<div>${c.passed ? "✓" : "✗"} <strong>${escHtml(c.label || c.key || "check")}</strong>: ${escHtml(c.detail)}</div>`)
                 .join("")}
             </div>`
          : ""
      }
      ${
        dry
          ? `<div class="segment-item">
               <div class="seg-time">FFmpeg Dry-Run Command Preview</div>
               <pre class="code-box">${escHtml(dry.command_preview)}</pre>
             </div>
             <div class="segment-item">
               <div class="seg-time">Remotion Props (Optional Compositor)</div>
               <pre class="code-box">${escHtml(JSON.stringify(dry.remotion_payload, null, 2))}</pre>
             </div>`
          : `<div class="muted">Click <strong>Dry-Run Filtergraph [D]</strong> to preview exact FFmpeg args without rendering.</div>`
      }
      ${
        ren
          ? `<div class="segment-item">
               <div class="seg-time">Rendered Local Output</div>
               <div>Path: <span class="mono">${escHtml(ren.video_path)}</span></div>
               <div>Size: <span class="mono">${((ren.probe?.bytes || 0) / 1024).toFixed(1)} KB</span> · SHA-256: <span class="mono">${(ren.sha256 || "").slice(0, 16)}…</span></div>
             </div>`
          : ""
      }
    `;
  }
}

function syncPlayhead() {
  const video = $("video-player");
  const s = state.session;
  if (!video || !s) return;
  const totalDur = Math.max(0.5, Number(video.duration || s.probe?.duration_sec || 24));
  const cur = Number(video.currentTime || 0);
  $("timecode-hud").textContent = `${fmtTimecode(cur)} / ${fmtTimecode(totalDur)}`;

  // Position playhead inside the track-lane area (offset past 84px track-tag + 6px gap)
  const timeline = $("nle-timeline");
  const lane = $("scene-timeline");
  if (timeline && lane) {
    const tlRect = timeline.getBoundingClientRect();
    const laneRect = lane.getBoundingClientRect();
    if (tlRect.width > 0 && laneRect.width > 0) {
      const ratio = Math.max(0, Math.min(1, cur / totalDur));
      const leftPx = (laneRect.left - tlRect.left) + ratio * laneRect.width;
      $("playhead-line").style.left = `${leftPx.toFixed(1)}px`;
    }
  }

  // Live highlight spoken word chip & active transcript segment during playback
  if (state.previewMode === "source") {
    document.querySelectorAll("#tab-transcript .word-chip").forEach((el) => {
      const ws = Number(el.dataset.start);
      const we = Number(el.dataset.end);
      el.classList.toggle("spoken", cur >= ws && cur <= we + 0.12);
    });
    document.querySelectorAll("#tab-transcript .segment-item[data-seg-idx]").forEach((el) => {
      const ss = Number(el.dataset.start);
      const se = Number(el.dataset.end);
      el.classList.toggle("active-seg", cur >= ss && cur <= se);
    });
  }
}

function renderAll() {
  renderHealth();
  renderStepper();
  renderSessionsDropdown();
  renderProbeAndClips();
  renderStage();
  renderInspector();
}

async function refreshSessions(selectId = null) {
  state.sessions = await api("/api/studio/sessions");
  const target = selectId || state.session?.session_id || state.sessions[0]?.session_id;
  if (target) {
    state.session = await api(`/api/studio/sessions/${target}`);
    if (!state.activeClipId || !state.session.clips?.some((c) => c.clip_id === state.activeClipId)) {
      state.activeClipId = state.session.clips?.[0]?.clip_id || null;
    }
  }
  renderAll();
}

async function runAction(label, fn) {
  showBanner(label);
  try {
    await fn();
    showBanner("");
  } catch (err) {
    showBanner(`Error: ${err.message}`);
  }
}

function readCutInputs() {
  return {
    start_sec: Number($("inp-start").value),
    end_sec: Number($("inp-end").value),
    style: $("inp-style").value,
    duration_band: $("inp-band").value,
    hook_text: $("inp-hook").value,
  };
}

function togglePlay() {
  const video = $("video-player");
  if (!video || !state.session) return;
  if (video.paused) {
    video.play().catch(() => {});
    $("btn-play").textContent = "Pause";
  } else {
    video.pause();
    $("btn-play").textContent = "Play";
  }
}

function stepVideo(deltaSec) {
  const video = $("video-player");
  if (!video || !state.session) return;
  video.currentTime = Math.max(0, Math.min(video.duration || 999, video.currentTime + deltaSec));
  syncPlayhead();
}

function bindEvents() {
  $("btn-example").addEventListener("click", () =>
    runAction("Loading 16:9 Spoken Podcast Example (faster-whisper + PySceneDetect)...", async () => {
      const sess = await api("/api/studio/sessions/example", {
        method: "POST",
        body: JSON.stringify({ auto_run: true }),
      });
      state.session = sess;
      state.activeClipId = sess.clips?.[0]?.clip_id || null;
      state.previewMode = "source";
      await refreshSessions(sess.session_id);
    })
  );

  $("btn-demo").addEventListener("click", () =>
    runAction("Synthesizing 24s demo & running ASR + PySceneDetect + Hook scoring...", async () => {
      const sess = await api("/api/studio/sessions/demo", {
        method: "POST",
        body: JSON.stringify({ auto_run: true }),
      });
      state.session = sess;
      state.activeClipId = sess.clips?.[0]?.clip_id || null;
      state.previewMode = "source";
      await refreshSessions(sess.session_id);
    })
  );

  $("btn-open-modal").addEventListener("click", () => $("open-modal").classList.remove("hidden"));
  $("btn-modal-cancel").addEventListener("click", () => $("open-modal").classList.add("hidden"));
  $("btn-modal-open").addEventListener("click", () =>
    runAction("Probing local video...", async () => {
      const videoPath = $("modal-video-path").value.trim();
      const campaign = $("modal-campaign").value.trim() || "Creator Showcase";
      const sess = await api("/api/studio/sessions/open", {
        method: "POST",
        body: JSON.stringify({ video_path: videoPath, campaign_name: campaign }),
      });
      $("open-modal").classList.add("hidden");
      state.session = sess;
      state.activeClipId = null;
      state.previewMode = "source";
      await refreshSessions(sess.session_id);
    })
  );

  $("session-select").addEventListener("change", async (e) => {
    const sid = e.target.value;
    if (!sid) return;
    state.session = await api(`/api/studio/sessions/${sid}`);
    state.activeClipId = state.session.clips?.[0]?.clip_id || null;
    state.previewMode = "source";
    renderAll();
  });

  $("btn-step-transcribe").addEventListener("click", () => {
    if (!state.session) return;
    runAction("Step 2: Running WhisperX / faster-whisper transcription...", async () => {
      state.session = await api(`/api/studio/sessions/${state.session.session_id}/transcribe`, {
        method: "POST",
        body: JSON.stringify({ model: "tiny", device: "cpu", compute_type: "int8" }),
      });
      renderAll();
    });
  });

  $("btn-step-scenes").addEventListener("click", () => {
    if (!state.session) return;
    const detector = $("detector-select").value;
    runAction(`Step 3: Running PySceneDetect (${detector})...`, async () => {
      state.session = await api(`/api/studio/sessions/${state.session.session_id}/scenes`, {
        method: "POST",
        body: JSON.stringify({ detector }),
      });
      renderAll();
    });
  });

  $("btn-step-score").addEventListener("click", () => {
    if (!state.session) return;
    runAction("Step 4: Computing hook & retention pacing scores...", async () => {
      state.session = await api(`/api/studio/sessions/${state.session.session_id}/score`, {
        method: "POST",
        body: JSON.stringify({ preferred_length_band: $("inp-band").value }),
      });
      state.activeClipId = state.session.clips?.[0]?.clip_id || null;
      renderAll();
    });
  });

  $("btn-safezone").addEventListener("click", () => {
    state.safeZoneOn = !state.safeZoneOn;
    renderStage();
  });

  $("btn-play").addEventListener("click", togglePlay);
  $("btn-back").addEventListener("click", () => stepVideo(-1.5));
  $("btn-fwd").addEventListener("click", () => stepVideo(1.5));
  $("btn-jump-cut").addEventListener("click", () => {
    const clip = activeClip();
    const video = $("video-player");
    if (clip && video) {
      video.currentTime = Number(clip.start_sec || 0);
      syncPlayhead();
    }
  });
  $("btn-set-in").addEventListener("click", () => {
    const video = $("video-player");
    if (video) $("inp-start").value = Number(video.currentTime || 0).toFixed(2);
  });
  $("btn-set-out").addEventListener("click", () => {
    const video = $("video-player");
    if (video) $("inp-end").value = Math.max(Number($("inp-start").value) + 0.5, Number(video.currentTime || 0)).toFixed(2);
  });
  $("playback-rate").addEventListener("change", (e) => {
    const video = $("video-player");
    if (video) video.playbackRate = Number(e.target.value || 1);
  });

  // Click anywhere inside timeline lanes to scrub playhead
  $("nle-timeline").addEventListener("click", (e) => {
    const s = state.session;
    const video = $("video-player");
    const lane = $("scene-timeline");
    if (!s || !video || !lane) return;
    const laneRect = lane.getBoundingClientRect();
    if (laneRect.width <= 0) return;
    const ratio = Math.max(0, Math.min(1, (e.clientX - laneRect.left) / laneRect.width));
    const totalDur = Math.max(0.5, Number(video.duration || s.probe?.duration_sec || 24));
    video.currentTime = ratio * totalDur;
    syncPlayhead();
  });

  const video = $("video-player");
  video.addEventListener("timeupdate", syncPlayhead);
  video.addEventListener("loadedmetadata", syncPlayhead);
  video.addEventListener("play", () => ($("btn-play").textContent = "Pause"));
  video.addEventListener("pause", () => ($("btn-play").textContent = "Play"));

  $("btn-approve").addEventListener("click", () => {
    const clip = activeClip();
    if (!state.session || !clip) return;
    runAction(`Approving ${clip.clip_id} (human gate)...`, async () => {
      state.session = await api(
        `/api/studio/sessions/${state.session.session_id}/clips/${clip.clip_id}/decision`,
        { method: "POST", body: JSON.stringify({ decision: "APPROVED", ...readCutInputs() }) }
      );
      renderAll();
    });
  });

  $("btn-reject").addEventListener("click", () => {
    const clip = activeClip();
    if (!state.session || !clip) return;
    runAction(`Rejecting ${clip.clip_id}...`, async () => {
      state.session = await api(
        `/api/studio/sessions/${state.session.session_id}/clips/${clip.clip_id}/decision`,
        { method: "POST", body: JSON.stringify({ decision: "REJECTED", ...readCutInputs() }) }
      );
      renderAll();
    });
  });

  $("btn-dry-run").addEventListener("click", () => {
    const clip = activeClip();
    if (!state.session || !clip) return;
    runAction(`Generating FFmpeg dry-run filtergraph for ${clip.clip_id}...`, async () => {
      const dry = await api(
        `/api/studio/sessions/${state.session.session_id}/clips/${clip.clip_id}/dry-run`,
        { method: "POST", body: JSON.stringify(readCutInputs()) }
      );
      state.session.dry_runs = { ...(state.session.dry_runs || {}), [clip.clip_id]: dry };
      state.activeItab = "filtergraph";
      document.querySelectorAll(".itab").forEach((b) => b.classList.toggle("active", b.dataset.itab === "filtergraph"));
      document.querySelectorAll(".itab-body").forEach((b) => b.classList.toggle("active", b.id === "tab-filtergraph"));
      renderInspector();
    });
  });

  $("btn-render").addEventListener("click", () => {
    const clip = activeClip();
    if (!state.session || !clip) return;
    runAction(`Rendering local 9:16 MP4 for ${clip.clip_id} via FFmpeg...`, async () => {
      const ren = await api(
        `/api/studio/sessions/${state.session.session_id}/clips/${clip.clip_id}/render`,
        { method: "POST", body: JSON.stringify(readCutInputs()) }
      );
      state.session = await api(`/api/studio/sessions/${state.session.session_id}`);
      if (ren.ok) {
        state.previewMode = "rendered";
        state.safeZoneOn = false;
        document.querySelectorAll(".tab-btn").forEach((b) =>
          b.classList.toggle("active", b.dataset.preview === "rendered")
        );
      }
      state.activeItab = "filtergraph";
      document.querySelectorAll(".itab").forEach((b) => b.classList.toggle("active", b.dataset.itab === "filtergraph"));
      document.querySelectorAll(".itab-body").forEach((b) => b.classList.toggle("active", b.id === "tab-filtergraph"));
      renderAll();
    });
  });

  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.previewMode = btn.dataset.preview;
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b === btn));
      renderStage();
    });
  });

  document.querySelectorAll(".itab").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.activeItab = btn.dataset.itab;
      document.querySelectorAll(".itab").forEach((b) => b.classList.toggle("active", b === btn));
      document.querySelectorAll(".itab-body").forEach((b) =>
        b.classList.toggle("active", b.id === `tab-${state.activeItab}`)
      );
    });
  });

  // NLE Keyboard Shortcuts (disabled when typing in form fields)
  document.addEventListener("keydown", (e) => {
    const tag = (e.target?.tagName || "").toLowerCase();
    if (["input", "textarea", "select"].includes(tag)) return;
    if (e.code === "Space") {
      e.preventDefault();
      togglePlay();
    } else if (e.key === "j" || e.key === "J") {
      stepVideo(-1.5);
    } else if (e.key === "k" || e.key === "K") {
      $("video-player")?.pause();
    } else if (e.key === "l" || e.key === "L") {
      stepVideo(1.5);
    } else if (e.key === "a" || e.key === "A") {
      $("btn-approve")?.click();
    } else if (e.key === "r" || e.key === "R") {
      $("btn-reject")?.click();
    } else if (e.key === "d" || e.key === "D") {
      $("btn-dry-run")?.click();
    }
  });
}

async function boot() {
  bindEvents();
  state.health = await api("/api/studio/health");
  await refreshSessions();
  renderAll();
}

boot().catch((err) => showBanner(`Studio init error: ${err.message}`));
