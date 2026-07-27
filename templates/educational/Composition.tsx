import React from "react";
import { AbsoluteFill, useCurrentFrame, interpolate } from "remotion";

export const EducationalComposition: React.FC<{ hookText: string }> = ({
  hookText,
}) => {
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
          fontSize: 42,
          fontWeight: 600,
        }}
      >
        {hookText}
      </div>
    </AbsoluteFill>
  );
};
