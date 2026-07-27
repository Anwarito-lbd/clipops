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

const DramaticHook: React.FC<{ hookText: string }> = ({ hookText }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 10], [0, 1], {
    extrapolateRight: "clamp",
  });
  const scale = interpolate(frame, [0, 15], [1.08, 1], {
    extrapolateRight: "clamp",
  });
  const { durationInFrames } = useVideoConfig();
  const progress = Math.min(100, (frame / Math.max(1, durationInFrames)) * 100);

  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-start",
        padding: 48,
        transform: `scale(${scale})`,
      }}
    >
      <div
        style={{
          opacity,
          color: "white",
          fontSize: 56,
          fontWeight: 800,
          textShadow: "0 4px 24px rgba(0,0,0,0.85)",
          lineHeight: 1.15,
          maxWidth: "92%",
        }}
      >
        {hookText}
      </div>
      <Sequence from={12}>
        <div
          style={{
            position: "absolute",
            bottom: 96,
            left: 48,
            right: 48,
            height: 8,
            background: "rgba(255,255,255,0.25)",
            borderRadius: 4,
          }}
        >
          <div
            style={{
              width: `${progress}%`,
              height: "100%",
              background: "#ff3b5c",
              borderRadius: 4,
            }}
          />
        </div>
      </Sequence>
    </AbsoluteFill>
  );
};

const EducationalHook: React.FC<{ hookText: string }> = ({ hookText }) => {
  const frame = useCurrentFrame();
  const y = interpolate(frame, [0, 20], [40, 0], { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ justifyContent: "flex-end", padding: 40 }}>
      <div
        style={{
          transform: `translateY(${y}px)`,
          background: "rgba(10,16,28,0.82)",
          borderLeft: "6px solid #3dd6c6",
          padding: "20px 24px",
          color: "white",
          fontSize: 40,
          fontWeight: 600,
          marginBottom: 120,
        }}
      >
        {hookText}
      </div>
    </AbsoluteFill>
  );
};

const CommentaryHook: React.FC<{ hookText: string }> = ({ hookText }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 8], [0, 1], {
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        padding: 36,
      }}
    >
      <div
        style={{
          opacity,
          maxWidth: "90%",
          background: "rgba(0,0,0,0.72)",
          borderRadius: 16,
          padding: "18px 22px",
          color: "#f5f5f5",
          fontSize: 38,
          fontWeight: 500,
          textAlign: "center",
        }}
      >
        {hookText}
      </div>
    </AbsoluteFill>
  );
};

export const StyleOverlay: React.FC<StyleOverlayProps> = ({
  styleName,
  hookText,
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
        <EducationalHook hookText={hookText} />
      ) : styleName === "commentary" ? (
        <CommentaryHook hookText={hookText} />
      ) : (
        <DramaticHook hookText={hookText} />
      )}
    </AbsoluteFill>
  );
};
