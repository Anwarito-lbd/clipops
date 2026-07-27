import React from "react";
import { AbsoluteFill, useCurrentFrame, interpolate } from "remotion";

export const CommentaryComposition: React.FC<{ hookText: string }> = ({
  hookText,
}) => {
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
          background: "rgba(0,0,0,0.7)",
          borderRadius: 16,
          padding: "18px 22px",
          color: "#f5f5f5",
          fontSize: 40,
          fontWeight: 500,
          textAlign: "center",
        }}
      >
        {hookText}
      </div>
    </AbsoluteFill>
  );
};
