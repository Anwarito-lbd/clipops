"""Install / verify WhisperX + CUDA for ClipOps (RTX 50-series needs cu128)."""

from __future__ import annotations

import argparse
import subprocess
import sys


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.check_call(cmd)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-torch", action="store_true")
    parser.add_argument("--skip-whisperx", action="store_true")
    args = parser.parse_args()
    py = sys.executable

    if not args.skip_torch:
        run([py, "-m", "pip", "uninstall", "-y", "torch", "torchvision", "torchaudio"])
        run(
            [
                py,
                "-m",
                "pip",
                "install",
                "torch",
                "torchvision",
                "torchaudio",
                "--index-url",
                "https://download.pytorch.org/whl/cu128",
            ]
        )

    if not args.skip_whisperx:
        # whisperx pulls torch; already installed cu128 — avoid CPU overwrite
        run([py, "-m", "pip", "install", "whisperx", "--no-deps"])
        run(
            [
                py,
                "-m",
                "pip",
                "install",
                "faster-whisper",
                "ctranslate2",
                "transformers",
                "pandas",
                "nltk",
                "pyannote.audio",
                "torchcodec",
                "omegaconf",
                "pytorch-lightning",
                "rich",
                "asteroid-filterbanks",
                "speechbrain",
                "tensorboardX",
                "matplotlib",
                "ffmpeg-python",
            ]
        )

    import torch

    print("torch", torch.__version__, "cuda", torch.version.cuda)
    print("cuda_available", torch.cuda.is_available())
    if torch.cuda.is_available():
        print("device", torch.cuda.get_device_name(0))
        x = torch.zeros(1, device="cuda")
        print("cuda_tensor_ok", x.device)
    try:
        import whisperx  # noqa: F401

        print("whisperx_import_ok")
    except Exception as exc:
        print("whisperx_import_failed", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
