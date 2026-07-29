import React from "react";
import {
  AbsoluteFill,
  OffthreadVideo,
  Sequence,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

export type StyleName = "dramatic" | "educational" | "commentary";

export type StyleOverlayProps = {
  styleName: StyleName;
  hookText: string;
  caption: string;
  videoSrc: string;
};

/** MoneyPrinterTurbo-inspired karaoke word highlight on campaign footage. */
const KaraokeCaptions: React.FC<{
  text: string;
  color: string;
  highlight: string;
  bottom: number;
  fontSize?: number;
}> = ({ text, color, highlight, bottom, fontSize = 44 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const words = (text || "")
    .replace(/\n+/g, " ")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 28);
  if (!words.length) return null;

  const wordsPerSec = 2.4;
  const activeIdx = Math.min(
    words.length - 1,
    Math.floor((frame / fps) * wordsPerSec)
  );
  // Show a sliding window of ~6 words
  const start = Math.max(0, activeIdx - 2);
  const visible = words.slice(start, start + 6);

  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-end",
        alignItems: "center",
        paddingBottom: bottom,
        paddingLeft: 36,
        paddingRight: 36,
      }}
    >
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "center",
          gap: 10,
          maxWidth: "94%",
          background: "rgba(0,0,0,0.55)",
          borderRadius: 14,
          padding: "14px 18px",
        }}
      >
        {visible.map((w, i) => {
          const globalIdx = start + i;
          const on = globalIdx === activeIdx;
          return (
            <span
              key={`${globalIdx}-${w}`}
              style={{
                color: on ? highlight : color,
                fontSize: on ? fontSize + 4 : fontSize,
                fontWeight: on ? 800 : 700,
                textShadow: on
                  ? `0 0 18px ${highlight}, 0 3px 10px rgba(0,0,0,0.9)`
                  : "0 2px 8px rgba(0,0,0,0.85)",
                WebkitTextStroke: on ? "0px transparent" : `1.5px rgba(0,0,0,0.65)`,
                transform: on ? "translateY(-2px)" : "none",
                transition: "none",
              }}
            >
              {w}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

const DramaticHook: React.FC<{ hookText: string; caption: string }> = ({
  hookText,
  caption,
}) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 10], [0, 1], {
    extrapolateRight: "clamp",
  });
  const scale = interpolate(frame, [0, 15], [1.1, 1], {
    extrapolateRight: "clamp",
  });
  const { durationInFrames } = useVideoConfig();
  const progress = Math.min(100, (frame / Math.max(1, durationInFrames)) * 100);

  return (
    <AbsoluteFill>
      <AbsoluteFill
        style={{
          justifyContent: "flex-start",
          padding: 44,
          transform: `scale(${scale})`,
        }}
      >
        <div
          style={{
            opacity,
            color: "#fff",
            fontSize: 58,
            fontWeight: 900,
            letterSpacing: -0.5,
            textShadow: "0 0 2px #000, 0 4px 28px rgba(0,0,0,0.9)",
            WebkitTextStroke: "2px rgba(0,0,0,0.35)",
            lineHeight: 1.12,
            maxWidth: "94%",
            textTransform: "uppercase",
          }}
        >
          {hookText}
        </div>
        <Sequence from={12}>
          <div
            style={{
              position: "absolute",
              bottom: 72,
              left: 48,
              right: 48,
              height: 10,
              background: "rgba(255,255,255,0.22)",
              borderRadius: 6,
            }}
          >
            <div
              style={{
                width: `${progress}%`,
                height: "100%",
                background: "linear-gradient(90deg,#ff3b5c,#ff8a3d)",
                borderRadius: 6,
                boxShadow: "0 0 16px rgba(255,59,92,0.55)",
              }}
            />
          </div>
        </Sequence>
      </AbsoluteFill>
      <Sequence from={Math.round(0.8 * 30)}>
        <KaraokeCaptions
          text={caption || hookText}
          color="#f5f5f5"
          highlight="#ff3b5c"
          bottom={120}
          fontSize={46}
        />
      </Sequence>
    </AbsoluteFill>
  );
};

const EducationalHook: React.FC<{ hookText: string; caption: string }> = ({
  hookText,
  caption,
}) => {
  const frame = useCurrentFrame();
  const y = interpolate(frame, [0, 20], [48, 0], { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{ justifyContent: "flex-end", padding: 36 }}>
        <div
          style={{
            transform: `translateY(${y}px)`,
            background: "rgba(8,14,26,0.88)",
            borderLeft: "7px solid #3dd6c6",
            borderRadius: "0 14px 14px 0",
            padding: "22px 26px",
            color: "white",
            fontSize: 42,
            fontWeight: 700,
            marginBottom: 200,
            boxShadow: "0 12px 40px rgba(0,0,0,0.45)",
            lineHeight: 1.25,
          }}
        >
          {hookText}
        </div>
      </AbsoluteFill>
      <Sequence from={18}>
        <KaraokeCaptions
          text={caption || hookText}
          color="#e8f7f5"
          highlight="#3dd6c6"
          bottom={110}
          fontSize={42}
        />
      </Sequence>
    </AbsoluteFill>
  );
};

const CommentaryHook: React.FC<{ hookText: string; caption: string }> = ({
  hookText,
  caption,
}) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 8], [0, 1], {
    extrapolateRight: "clamp",
  });
  const bounce = interpolate(frame, [0, 12, 24], [1.06, 0.98, 1], {
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill>
      <AbsoluteFill
        style={{
          justifyContent: "center",
          alignItems: "center",
          padding: 32,
        }}
      >
        <div
          style={{
            opacity,
            transform: `scale(${bounce})`,
            maxWidth: "92%",
            background: "rgba(0,0,0,0.78)",
            border: "3px solid #ffe566",
            borderRadius: 20,
            padding: "20px 24px",
            color: "#ffe566",
            fontSize: 40,
            fontWeight: 800,
            textAlign: "center",
            textShadow: "0 3px 0 #000, 0 8px 24px rgba(0,0,0,0.7)",
            lineHeight: 1.2,
          }}
        >
          {hookText}
        </div>
      </AbsoluteFill>
      <Sequence from={20}>
        <KaraokeCaptions
          text={caption || hookText}
          color="#fff8d6"
          highlight="#ffe566"
          bottom={130}
          fontSize={44}
        />
      </Sequence>
    </AbsoluteFill>
  );
};

export const StyleOverlay: React.FC<StyleOverlayProps> = ({
  styleName,
  hookText,
  caption,
  videoSrc,
}) => {
  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      {videoSrc ? (
        <OffthreadVideo
          src={videoSrc}
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
      ) : null}
      {styleName === "educational" ? (
        <EducationalHook hookText={hookText} caption={caption} />
      ) : styleName === "commentary" ? (
        <CommentaryHook hookText={hookText} caption={caption} />
      ) : (
        <DramaticHook hookText={hookText} caption={caption} />
      )}
    </AbsoluteFill>
  );
};
