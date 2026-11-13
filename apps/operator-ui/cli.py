"""ClipOps Operator Studio CLI — step-by-step local clipping & render workstation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in (str(HERE), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from studio import StudioService, check_media_engines, probe_media  # noqa: E402
from workers.scene_detection.detect import detect_scenes  # noqa: E402
from workers.transcription.transcribe import transcribe_video  # noqa: E402
from workers.video_rendering.render import build_filtergraph, render_account_package  # noqa: E402
from packages.services.clip_ranking import ClipRankingService  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="clipops-studio",
        description="ClipOps ethical short-form video clipping & editing CLI.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health", help="Inspect FFmpeg, PySceneDetect, ASR, and Remotion readiness.")

    p_probe = sub.add_parser("probe", help="Inspect video duration, resolution, and codecs.")
    p_probe.add_argument("video", help="Path to local video file")

    p_tr = sub.add_parser("transcribe", help="Run WhisperX -> faster-whisper -> heuristic ASR.")
    p_tr.add_argument("video")
    p_tr.add_argument("--out", default="transcript.json")
    p_tr.add_argument("--model", default="tiny")
    p_tr.add_argument("--device", default="cpu")
    p_tr.add_argument("--compute-type", default="int8")

    p_sc = sub.add_parser("scenes", help="Detect scene cut boundaries with PySceneDetect.")
    p_sc.add_argument("video")
    p_sc.add_argument("--out", default="scenes.json")
    p_sc.add_argument("--detector", choices=["content", "adaptive", "hybrid"], default="hybrid")

    p_score = sub.add_parser("score", help="Transcribe, detect scenes, and score hooks/retention.")
    p_score.add_argument("video")
    p_score.add_argument("--campaign", default="Creator Showcase")
    p_score.add_argument("--detector", choices=["content", "adaptive", "hybrid"], default="hybrid")
    p_score.add_argument("--model", default="tiny")

    p_dry = sub.add_parser("dry-run", help="Preview exact FFmpeg filtergraph without rendering.")
    p_dry.add_argument("video")
    p_dry.add_argument("--start", type=float, default=0.0)
    p_dry.add_argument("--end", type=float, default=8.0)
    p_dry.add_argument("--style", choices=["dramatic", "educational", "commentary"], default="dramatic")
    p_dry.add_argument("--band", choices=["15-25", "25-40", "40-60"], default="15-25")
    p_dry.add_argument("--hook", default="Wait until you see this.")
    p_dry.add_argument("--out", default="dry_run.mp4")
    p_dry.add_argument("--no-burn", action="store_true")

    p_ren = sub.add_parser("render", help="Render a 9:16 vertical short-form package locally.")
    p_ren.add_argument("video")
    p_ren.add_argument("--start", type=float, default=0.0)
    p_ren.add_argument("--end", type=float, default=8.0)
    p_ren.add_argument("--style", choices=["dramatic", "educational", "commentary"], default="dramatic")
    p_ren.add_argument("--band", choices=["15-25", "25-40", "40-60"], default="15-25")
    p_ren.add_argument("--hook", default="Wait until you see this.")
    p_ren.add_argument("--caption", default="Paid partnership #CreatorStudio")
    p_ren.add_argument("--out-dir", default="storage/cli_render")
    p_ren.add_argument("--no-burn", action="store_true")

    p_demo = sub.add_parser("demo", help="Run full synthetic demo session (probe -> score -> approve -> render).")
    p_demo.add_argument("--out-json", default=None)

    p_srv = sub.add_parser("serve", help="Start the lightweight local Operator Studio UI.")
    p_srv.add_argument("--host", default="127.0.0.1")
    p_srv.add_argument("--port", type=int, default=8010)

    args = parser.parse_args(argv)

    if args.cmd == "health":
        print(json.dumps(check_media_engines(), indent=2))
        return 0

    if args.cmd == "probe":
        print(json.dumps(probe_media(args.video), indent=2))
        return 0

    if args.cmd == "transcribe":
        res = transcribe_video(
            args.video,
            args.out,
            model=args.model,
            device=args.device,
            compute_type=args.compute_type,
            enable_diarization=False,
        )
        print(json.dumps(res, indent=2))
        return 0

    if args.cmd == "scenes":
        res = detect_scenes(args.video, args.out, detector=args.detector)
        print(json.dumps(res, indent=2))
        return 0

    if args.cmd == "score":
        svc = StudioService()
        sess = svc.open_video_session(args.video, campaign_name=args.campaign)
        svc.step_transcribe(sess["session_id"], model=args.model, device="cpu", compute_type="int8")
        svc.step_detect_scenes(sess["session_id"], detector=args.detector)
        scored = svc.step_score_hooks(sess["session_id"], campaign_name=args.campaign)
        print(json.dumps({"session_id": scored["session_id"], "clips": scored["clips"]}, indent=2))
        return 0

    if args.cmd == "dry-run":
        fg = build_filtergraph(
            source_video=args.video,
            start_sec=args.start,
            end_sec=args.end,
            style=args.style,
            duration_band=args.band,
            hook_text=args.hook,
            output_path=args.out,
            burn_captions=not args.no_burn,
        )
        print(json.dumps(fg, indent=2))
        return 0

    if args.cmd == "render":
        res = render_account_package(
            source_video=args.video,
            start_sec=args.start,
            end_sec=args.end,
            style=args.style,
            duration_band=args.band,
            caption=args.caption,
            hook_text=args.hook,
            package_dir=args.out_dir,
            remotion_url=None,
            burn_captions=not args.no_burn,
        )
        print(json.dumps(res, indent=2))
        return 0 if res.get("ok") else 1

    if args.cmd == "demo":
        svc = StudioService()
        sess = svc.create_demo_session(auto_run=True)
        top_id = sess["clips"][0]["clip_id"]
        svc.decide_clip(sess["session_id"], top_id, decision="APPROVED", notes="CLI verified demo")
        dry = svc.dry_run_render(sess["session_id"], top_id)
        ren = svc.execute_render(sess["session_id"], top_id)
        summary = {
            "session_id": sess["session_id"],
            "probe": sess["probe"],
            "scenes_engine": sess["scenes"]["engine"],
            "detector": sess["scenes"]["detector"],
            "scene_count": len(sess["scenes"]["scenes"]),
            "transcript_engine": sess["transcript"]["engine"],
            "top_clip": svc.get_session(sess["session_id"])["clips"][0],
            "dry_run_vf": dry["ffmpeg"]["vf"],
            "render": ren,
        }
        if args.out_json:
            Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out_json).write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 0 if ren.get("ok") else 1

    if args.cmd == "serve":
        import uvicorn

        uvicorn.run("server:app", app_dir=str(HERE), host=args.host, port=args.port, reload=False)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
