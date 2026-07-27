import React from "react";
import { AbsoluteFill, Sequence, useCurrentFrame, interpolate } from "remotion";

export const DramaticComposition: React.FC<{ hookText: string }> = ({
  hookText,
}) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 10], [0, 1], {
    extrapolateRight: "clamp",
  });
  const scale = interpolate(frame, [0, 15], [1.08, 1], {
    extrapolateRight: "clamp",
  });
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
          fontSize: 64,
          fontWeight: 800,
          textShadow: "0 4px 24px rgba(0,0,0,0.8)",
          lineHeight: 1.1,
        }}
      >
        {hookText}
      </div>
      <Sequence from={20}>
        <div
          style={{
            position: "absolute",
            bottom: 80,
            left: 48,
            right: 48,
            height: 8,
            background: "rgba(255,255,255,0.25)",
            borderRadius: 4,
          }}
        >
          <div
            style={{
              width: `${Math.min(100, frame)}%`,
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
