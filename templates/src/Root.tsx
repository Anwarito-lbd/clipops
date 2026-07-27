import React from "react";
import { Composition } from "remotion";
import { StyleOverlay, StyleOverlayProps } from "./StyleOverlay";

const FPS = 30;
const WIDTH = 1080;
const HEIGHT = 1920;
const DEFAULT_DURATION = 30 * FPS;

const defaultProps: StyleOverlayProps = {
  styleName: "dramatic",
  hookText: "Wait for this",
  caption: "",
  videoSrc: "",
};

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="Dramatic"
        component={StyleOverlay}
        durationInFrames={DEFAULT_DURATION}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
        defaultProps={{ ...defaultProps, styleName: "dramatic" }}
        calculateMetadata={async ({ props }) => {
          // Duration resolved at render time via selectComposition + inputProps
          return {
            durationInFrames: DEFAULT_DURATION,
            props,
          };
        }}
      />
      <Composition
        id="Educational"
        component={StyleOverlay}
        durationInFrames={DEFAULT_DURATION}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
        defaultProps={{ ...defaultProps, styleName: "educational" }}
      />
      <Composition
        id="Commentary"
        component={StyleOverlay}
        durationInFrames={DEFAULT_DURATION}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
        defaultProps={{ ...defaultProps, styleName: "commentary" }}
      />
    </>
  );
};
