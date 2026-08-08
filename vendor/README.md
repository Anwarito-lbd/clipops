# vendor/

Third-party code and model weights the pipeline depends on. Nothing here is
committed: `openshorts` is a 161 MB checkout carrying its own `.git`, a 63 MB
demo gif and YOLO weights, and model binaries do not belong in source control.
Both are reproduced by the steps below.

## openshorts

Supplies the speaker-tracked vertical reframe. Our own reframe computes one crop
offset for a whole clip; openshorts drives a per-frame crop through ffmpeg
`sendcmd` so the camera follows the speaker, and its `punch_in` module pushes in
on emphasis beats. Its own note on why that matters:

> "A static crop for 45 seconds is the single most 'unedited' thing a vertical
> clip can do."

**Only the reframe path is used.** openshorts' clip selection routes through
Gemini, which is out of quota on this account; our ranker is free, faster, and
reproduces the benchmark batch, so selection stays where it is. Nothing in the
reframe path needs an API key.

```bash
git clone --depth 1 https://github.com/mutonby/openshorts.git vendor/openshorts
git -C vendor/openshorts apply ../patches/openshorts-windows-sendcmd-path.patch
```

The patch is required on Windows. ffmpeg's filtergraph parser reads backslashes
and the drive-letter colon as syntax, so the native temp path openshorts builds
for `sendcmd` fails with `No option name near '\Users\...'`. It is a no-op on
POSIX paths.

Python dependencies, on top of the API venv:

```bash
pip install ultralytics==8.4.46 google-genai==1.75.0 mediapipe==0.10.14
```

`mediapipe` must be **0.10.14**. openshorts calls the legacy `mp.solutions`
API, which later releases removed; 0.10.14 still carries both `solutions` and
the newer `tasks` API that `workers/video_rendering/reframe.py` uses, so one
version satisfies both. `google-genai` is imported by openshorts' `main` module
and is needed for the import to resolve — the reframe path never calls it.

## models

`blaze_face_short_range.tflite` (~229 KB) backs the mediapipe Tasks face
detector in `workers/video_rendering/reframe.py`, the fallback used when the
openshorts reframe is unavailable.

```bash
curl -L -o vendor/models/blaze_face_short_range.tflite \
  https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite
```
