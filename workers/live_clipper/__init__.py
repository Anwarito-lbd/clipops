"""Live chat-spike clipper: be first to the best clips while the stream is still live.

Streamlink records -> chat counted per 10 s (fires mid-bucket) -> FFmpeg cuts 30 s -> draft
-> Whisper captions -> ranked 9:16 clip + post kit. Game profiles (e.g. `gta6`) tune it all.
"""

from .clipper import ClipperConfig, LiveClipper, clip_window, process_spike, replay_vod
from .profiles import GTA6, PROFILES, get_profile
from .spikes import ChatMessage, ChatSpikeDetector, Spike, detect_spikes

__all__ = [
    "GTA6", "PROFILES", "ChatMessage", "ChatSpikeDetector", "ClipperConfig", "LiveClipper", "Spike",
    "clip_window", "detect_spikes", "get_profile", "process_spike", "replay_vod",
]
