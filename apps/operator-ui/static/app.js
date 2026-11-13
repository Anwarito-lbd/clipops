const state = {
  health: null,
  sessions: [],
  session: null,
  activeClipId: null,
  previewMode: "source",
  activeItab: "transcript",
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
    { label: e.whisperx ? "WhisperX" : e.faster_whisper ? "faster-whisper" : "ASR Fallback", ok: e.whisperx || e.faster_whisper },
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
          s.title || s.session_id
        }</option>`
    )
    .join("");
}

function renderProbeAndClips() {
  const s = state.session;
  if (!s) {
    $("probe-card").innerHTML = "No active session.";
    $("clip-count").textContent = "0 clips";
    $("clip-list").innerHTML = "";
    return;
  }
  const p = s.probe || {};
  $("probe-card").innerHTML = `
    <div><strong>${p.filename || "source.mp4"}</strong></div>
    <div>Duration: ${p.duration_sec}s · ${p.width}×${p.height} @ ${p.fps || "?"}fps</div>
    <div>Codecs: ${p.video_codec || "?"} / ${p.audio_codec || "?"} · ${(p.bytes / 1024).toFixed(1)} KB</div>
  `;

  const clips = s.clips || [];
  $("clip-count").textContent = `${clips.length} clips`;
  $("clip-list").innerHTML = clips
    .map((c) => {
      const active = c.clip_id === state.activeClipId ? "active" : "";
      const hasRender = Boolean(s.renders?.[c.clip_id]?.ok);
      return `
        <div class="clip-card ${active}" data-clip="${c.clip_id}">
          <div class="clip-top">
            <span class="clip-title">#${c.rank} · ${c.start_sec}s–${c.end_sec}s (${c.duration_sec}s)</span>
            <span class="pill pill-cyan">${c.total_score}</span>
          </div>
          <div class="clip-excerpt">${c.transcript_excerpt}</div>
          <div class="clip-tags">
            ${decisionPill(c.decision)}
            <span class="pill">${c.hook_type}</span>
            <span class="pill">${c.style}</span>
            ${hasRender ? `<span class="pill pill-green">MP4 Ready</span>` : ""}
          </div>
        </div>
      `;
    })
    .join("");

  document.querySelectorAll(".clip-card").forEach((el) => {
    el.addEventListener("click", () => {
      state.activeClipId = el.dataset.clip;
      renderAll();
    });
  });
}

function renderStage() {
  const s = state.session;
  const clip = activeClip();
  const video = $("video-player");
  const empty = $("video-empty");

  if (!s) {
    video.style.display = "none";
    empty.style.display = "block";
    $("scene-timeline").innerHTML = "";
    $("timeline-duration").textContent = "0.0s";
    $("active-clip-badge").textContent = "No clip selected";
    return;
  }

  empty.style.display = "none";
  video.style.display = "block";
  const renderedUrl = clip ? s.renders?.[clip.clip_id]?.video_url : null;
  const targetUrl = state.previewMode === "rendered" && renderedUrl ? renderedUrl : s.source_media_url;
  if (video.dataset.src !== targetUrl) {
    video.src = targetUrl;
    video.dataset.src = targetUrl;
  }

  const totalDur = Math.max(0.5, Number(s.probe?.duration_sec || 24));
  $("timeline-duration").textContent = `${totalDur.toFixed(1)}s`;
  const scenes = s.scenes?.scenes || [];
  $("scene-timeline").innerHTML = scenes
    .map((sc, i) => {
      const span = Math.max(0.5, sc.end_sec - sc.start_sec);
      const pct = (span / totalDur) * 100;
      const isSel = clip && Math.abs(sc.start_sec - clip.start_sec) < 0.25 && Math.abs(sc.end_sec - clip.end_sec) < 0.25;
      return `<div class="scene-seg ${isSel ? "selected" : ""}" style="width:${pct.toFixed(2)}%" data-start="${sc.start_sec}" data-end="${sc.end_sec}">S${i + 1} (${sc.start_sec}–${sc.end_sec}s)</div>`;
    })
    .join("");

  if (clip) {
    $("active-clip-badge").textContent = `${clip.clip_id} · ${clip.rank_report?.predicted_performance || "MEDIUM"}`;
    $("inp-start").value = clip.start_sec;
    $("inp-end").value = clip.end_sec;
    $("inp-style").value = clip.style;
    $("inp-band").value = clip.duration_band;
    $("inp-hook").value = clip.hook_text || "";
  } else {
    $("active-clip-badge").textContent = "Run Step 4 to rank clips";
  }
}

function renderInspector() {
  const s = state.session;
  const clip = activeClip();

  // 1. Transcript & Word Timestamps
  if (!s?.transcript) {
    $("tab-transcript").innerHTML = `<div class="muted">Run Step 2 (WhisperX / ASR) to inspect segments and forced-alignment word timestamps.</div>`;
  } else {
    const tr = s.transcript;
    const words = (tr.word_segments || []).slice(0, 48);
    $("tab-transcript").innerHTML = `
      <div class="segment-item">
        <div class="segment-meta">
          <span>Engine: ${tr.engine}</span>
          <span>Language: ${tr.language || "en"}</span>
        </div>
        <div class="muted" style="font-size:11px;">
          ${tr.fallback_reason ? `Fallback reason: ${tr.fallback_reason}` : "Direct ASR transcription"}
          ${tr.demo_script_overlay ? " (Demo script overlay active for silent synthetic tone)" : ""}
        </div>
      </div>
      ${(tr.segments || [])
        .map(
          (seg) => `
          <div class="segment-item">
            <div class="segment-meta">
              <span>${Number(seg.start).toFixed(2)}s → ${Number(seg.end).toFixed(2)}s</span>
              <span>${seg.speaker || "SPEAKER_0"}</span>
            </div>
            <div>${seg.text}</div>
          </div>`
        )
        .join("")}
      <div class="panel-head mt-12"><h2>Word-Level Timestamps</h2><span class="pill">${(tr.word_segments || []).length} words</span></div>
      <div class="word-cloud">
        ${words
          .map((w) => `<span class="word-chip"><span>${Number(w.start).toFixed(2)}s</span> ${w.word}</span>`)
          .join("")}
      </div>
    `;
  }

  // 2. Hooks & Retention Pacing
  if (!clip) {
    $("tab-scoring").innerHTML = `<div class="muted">Select a ranked clip to inspect hook sub-scores and retention pacing math.</div>`;
  } else {
    const r = clip.rank_report || {};
    const p = clip.retention_pacing || {};
    const bars = [
      ["Hook (0.18)", r.hook_score],
      ["Payoff (0.18)", r.payoff_score],
      ["Curiosity (0.12)", r.curiosity_score],
      ["Conflict (0.12)", r.conflict_score],
      ["Emotion (0.12)", r.emotion_score],
      ["Clarity (0.12)", r.clarity_score],
      ["Brief Fit (0.10)", r.campaign_fit],
      ["Duration (0.06)", r.duration_score],
    ];
    $("tab-scoring").innerHTML = `
      <div class="segment-item">
        <div class="segment-meta">
          <span>Total Score: ${clip.total_score} / 100</span>
          <span>${r.predicted_performance || "MEDIUM"} · ${clip.hook_type}</span>
        </div>
        <div class="muted" style="font-size:11px;">${(r.explanations || []).join(" · ")}</div>
      </div>
      ${bars
        .map(
          ([label, val]) => `
        <div class="metric-row">
          <span>${label}</span>
          <div class="bar-track"><div class="bar-fill" style="width:${Math.min(100, Number(val || 0))}%"></div></div>
          <span class="mono">${val ?? 0}</span>
        </div>`
        )
        .join("")}
      <div class="kv-grid">
        <div class="kv-box"><div class="k">Speaking Rate</div><div class="v">${p.wpm ?? "—"} WPM</div></div>
        <div class="kv-box"><div class="k">Pacing Regime</div><div class="v" style="font-size:11px">${p.pacing_label ?? "—"}</div></div>
        <div class="kv-box"><div class="k">Dead-Air Ratio</div><div class="v">${p.dead_air_ratio != null ? (p.dead_air_ratio * 100).toFixed(1) + "%" : "—"}</div></div>
        <div class="kv-box"><div class="k">3s Hook Density</div><div class="v">${p.hook_window_words_3s ?? 0} words</div></div>
      </div>
    `;
  }

  // 3. FFmpeg Filtergraph Dry-Run & Compliance Gate
  if (!clip) {
    $("tab-filtergraph").innerHTML = `<div class="muted">Select a clip and click Dry-Run Filtergraph or Render Local Cut.</div>`;
  } else {
    const dry = s.dry_runs?.[clip.clip_id];
    const ren = s.renders?.[clip.clip_id];
    const comp = clip.compliance || dry?.compliance_preview;
    const checks = comp?.checks || [];
    $("tab-filtergraph").innerHTML = `
      ${
        ren
          ? `<div class="segment-item">
               <div class="segment-meta"><span>Local Render ${ren.ok ? "COMPLETE" : "FAILED"}</span><span>${ren.duration_sec}s</span></div>
               <div class="mono" style="font-size:11px;">${ren.video_path}</div>
               <div class="muted" style="font-size:11px;">SHA-256: ${(ren.sha256 || "").slice(0, 16)}… · ${ren.probe?.bytes ? (ren.probe.bytes / 1024).toFixed(1) + " KB" : ""}</div>
             </div>`
          : ""
      }
      <div class="panel-head"><h2>FFmpeg Filtergraph (-vf / -af)</h2><span class="pill">${dry ? "Dry-Run Ready" : "Not Run"}</span></div>
      <div class="code-block">${
        dry
          ? `-vf "${dry.ffmpeg.vf}"\n\n-af "${dry.ffmpeg.af}"\n\nFont: ${dry.ffmpeg.fontfile || "default"}`
          : "Click 'Dry-Run Filtergraph' to inspect the exact FFmpeg command and Remotion payload before rendering."
      }</div>
      <div class="panel-head mt-12"><h2>Compliance Gate</h2><span class="pill ${comp?.passed ? "pill-green" : "pill-amber"}">${comp ? (comp.passed ? "PASSED" : "HOLD") : "Pending"}</span></div>
      ${checks
        .map(
          (c) => `<div class="check-item"><span>${c.key}: ${c.detail}</span><span class="pill ${c.passed ? "pill-green" : "pill-red"}">${c.passed ? "PASS" : "FAIL"}</span></div>`
        )
        .join("")}
    `;
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

async function init() {
  state.health = await api("/api/studio/health");
  await refreshSessions();

  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.previewMode = btn.dataset.preview;
      renderStage();
    });
  });

  document.querySelectorAll(".itab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".itab").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".itab-body").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.activeItab = btn.dataset.itab;
      $("tab-" + state.activeItab).classList.add("active");
    });
  });

  $("session-select").addEventListener("change", async (e) => {
    if (e.target.value) {
      state.activeClipId = null;
      await refreshSessions(e.target.value);
    }
  });

  $("btn-demo").addEventListener("click", async () => {
    showBanner("Synthesizing 24s multi-scene demo video & running ASR / PySceneDetect / Hook scoring...");
    try {
      const sess = await api("/api/studio/sessions/demo", {
        method: "POST",
        body: JSON.stringify({ auto_run: true }),
      });
      state.activeClipId = sess.clips?.[0]?.clip_id || null;
      await refreshSessions(sess.session_id);
      showBanner(`Demo session ${sess.session_id} ready — inspect scenes, transcript, and trigger a dry-run or render.`);
    } catch (err) {
      showBanner("Error: " + err.message);
    }
  });

  $("btn-open-modal").addEventListener("click", () => $("open-modal").classList.remove("hidden"));
  $("btn-modal-cancel").addEventListener("click", () => $("open-modal").classList.add("hidden"));
  $("btn-modal-open").addEventListener("click", async () => {
    const video_path = $("modal-video-path").value.trim();
    const campaign_name = $("modal-campaign").value.trim() || "Creator Showcase";
    if (!video_path) return;
    $("open-modal").classList.add("hidden");
    showBanner("Opening and probing local video...");
    try {
      const sess = await api("/api/studio/sessions/open", {
        method: "POST",
        body: JSON.stringify({ video_path, campaign_name }),
      });
      state.activeClipId = null;
      await refreshSessions(sess.session_id);
      showBanner("Video probed. Run Step 2 -> Step 3 -> Step 4.");
    } catch (err) {
      showBanner("Error: " + err.message);
    }
  });

  $("btn-step-transcribe").addEventListener("click", async () => {
    if (!state.session) return;
    showBanner("Running transcription (WhisperX -> faster-whisper -> heuristic)...");
    await api(`/api/studio/sessions/${state.session.session_id}/transcribe`, { method: "POST", body: JSON.stringify({}) });
    await refreshSessions(state.session.session_id);
    showBanner("Transcription step complete.");
  });

  $("btn-step-scenes").addEventListener("click", async () => {
    if (!state.session) return;
    const detector = $("detector-select").value;
    showBanner(`Detecting scene cuts (${detector})...`);
    await api(`/api/studio/sessions/${state.session.session_id}/scenes`, {
      method: "POST",
      body: JSON.stringify({ detector }),
    });
    await refreshSessions(state.session.session_id);
    showBanner("Scene detection complete.");
  });

  $("btn-step-score").addEventListener("click", async () => {
    if (!state.session) return;
    showBanner("Scoring hooks & retention pacing...");
    await api(`/api/studio/sessions/${state.session.session_id}/score`, { method: "POST", body: JSON.stringify({}) });
    await refreshSessions(state.session.session_id);
    showBanner("Hook & retention scoring complete.");
  });

  async function submitDecision(decision) {
    const clip = activeClip();
    if (!state.session || !clip) return;
    await api(`/api/studio/sessions/${state.session.session_id}/clips/${clip.clip_id}/decision`, {
      method: "POST",
      body: JSON.stringify({
        decision,
        start_sec: Number($("inp-start").value),
        end_sec: Number($("inp-end").value),
        style: $("inp-style").value,
        duration_band: $("inp-band").value,
        hook_text: $("inp-hook").value,
      }),
    });
    await refreshSessions(state.session.session_id);
    showBanner(`Clip ${clip.clip_id} marked ${decision}.`);
  }

  $("btn-approve").addEventListener("click", () => submitDecision("APPROVED"));
  $("btn-reject").addEventListener("click", () => submitDecision("REJECTED"));

  $("btn-dry-run").addEventListener("click", async () => {
    const clip = activeClip();
    if (!state.session || !clip) return;
    await api(`/api/studio/sessions/${state.session.session_id}/clips/${clip.clip_id}/dry-run`, {
      method: "POST",
      body: JSON.stringify({
        style: $("inp-style").value,
        duration_band: $("inp-band").value,
        hook_text: $("inp-hook").value,
      }),
    });
    await refreshSessions(state.session.session_id);
    document.querySelector('[data-itab="filtergraph"]').click();
    showBanner(`Dry-run filtergraph generated for ${clip.clip_id}.`);
  });

  $("btn-render").addEventListener("click", async () => {
    const clip = activeClip();
    if (!state.session || !clip) return;
    showBanner(`Rendering 9:16 ${$("inp-style").value} cut with FFmpeg...`);
    await api(`/api/studio/sessions/${state.session.session_id}/clips/${clip.clip_id}/render`, {
      method: "POST",
      body: JSON.stringify({
        style: $("inp-style").value,
        duration_band: $("inp-band").value,
        hook_text: $("inp-hook").value,
      }),
    });
    state.previewMode = "rendered";
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.preview === "rendered"));
    await refreshSessions(state.session.session_id);
    document.querySelector('[data-itab="filtergraph"]').click();
    showBanner(`Local render complete for ${clip.clip_id}. Ready for manual review & publish.`);
  });
}

init().catch((e) => showBanner("Init error: " + e.message));
