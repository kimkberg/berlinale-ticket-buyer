import {
  AbsoluteFill,
  Sequence,
  useVideoConfig,
  useCurrentFrame,
  interpolate,
  staticFile,
} from "remotion";
import { Audio } from "@remotion/media";
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { slide } from "@remotion/transitions/slide";
import { TitleScene } from "./scenes/TitleScene";
import { ProblemScene } from "./scenes/ProblemScene";
import { UIShowcaseScene } from "./scenes/UIShowcaseScene";
import { GrabFlowScene } from "./scenes/GrabFlowScene";
import { WatchScene } from "./scenes/WatchScene";
import { CTAScene } from "./scenes/CTAScene";

export const BerlinaleDemo = () => {
  const { fps, durationInFrames } = useVideoConfig();

  // Two-part background music (Google Lyria2, crossfaded):
  // Part 1 (0-33s): Dark driving tension — plays 0-33s, fades out 28-33s
  // Part 2 (28-62s): Triumphant resolution — fades in 28-33s, fades out 57-62s
  // Crossfade overlap: 28-33s (5 seconds)
  const XFADE_START = 28 * fps;
  const XFADE_END = 33 * fps;

  // Part 1 volume: fade in 0-2s, steady, fade out during crossfade
  const part1Volume = (f: number) => {
    // f is relative to Part 1 start (frame 0)
    if (f < 2 * fps) {
      return interpolate(f, [0, 2 * fps], [0, 0.35]);
    }
    if (f < XFADE_START) {
      return 0.35;
    }
    if (f < XFADE_END) {
      return interpolate(f, [XFADE_START, XFADE_END], [0.35, 0], {
        extrapolateRight: "clamp",
      });
    }
    return 0;
  };

  // Part 2 volume: fade in during crossfade, peak at success, fade out at end
  const part2Volume = (f: number) => {
    // f is relative to Part 2 start (frame XFADE_START)
    const crossfadeDur = XFADE_END - XFADE_START;
    if (f < crossfadeDur) {
      // Crossfade in (0-5s of Part 2)
      return interpolate(f, [0, crossfadeDur], [0, 0.35]);
    }
    // After crossfade: 33s to 62s of video = 5s to 34s of Part 2
    const videoTime = XFADE_START / fps + f / fps; // absolute video time
    if (videoTime < 48) {
      // Build to peak during grab + watch
      return interpolate(videoTime, [33, 48], [0.35, 0.55], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      });
    }
    if (videoTime < 52) {
      // Peak at success moment
      return 0.55;
    }
    if (videoTime < 57) {
      // Settle
      return interpolate(videoTime, [52, 57], [0.55, 0.4], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      });
    }
    // Fade out
    return interpolate(videoTime, [57, 62], [0.4, 0], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  };

  return (
    <AbsoluteFill style={{ backgroundColor: "#0d0d0d" }}>
      {/* Part 1: Dark driving tension (Google Lyria2) */}
      <Audio
        src={staticFile("bgm_part1.wav")}
        volume={part1Volume}
      />

      {/* Part 2: Triumphant resolution (Google Lyria2) — starts at crossfade point */}
      <Sequence from={XFADE_START}>
        <Audio
          src={staticFile("bgm_part2.wav")}
          volume={part2Volume}
        />
      </Sequence>

      <TransitionSeries>
        {/* Scene 1: Title (0-5s) */}
        <TransitionSeries.Sequence durationInFrames={5 * fps}>
          <TitleScene />
        </TransitionSeries.Sequence>

        <TransitionSeries.Transition
          presentation={fade()}
          timing={linearTiming({ durationInFrames: Math.round(0.5 * fps) })}
        />

        {/* Scene 2: Problem (5-11s) */}
        <TransitionSeries.Sequence durationInFrames={6 * fps}>
          <ProblemScene />
        </TransitionSeries.Sequence>

        <TransitionSeries.Transition
          presentation={slide({ direction: "from-right" })}
          timing={linearTiming({ durationInFrames: Math.round(0.6 * fps) })}
        />

        {/* Scene 3: UI Showcase (11-32s) */}
        <TransitionSeries.Sequence durationInFrames={21 * fps}>
          <UIShowcaseScene />
        </TransitionSeries.Sequence>

        <TransitionSeries.Transition
          presentation={fade()}
          timing={linearTiming({ durationInFrames: Math.round(0.5 * fps) })}
        />

        {/* Scene 4: Grab Flow (32-44s) */}
        <TransitionSeries.Sequence durationInFrames={12 * fps}>
          <GrabFlowScene />
        </TransitionSeries.Sequence>

        <TransitionSeries.Transition
          presentation={fade()}
          timing={linearTiming({ durationInFrames: Math.round(0.5 * fps) })}
        />

        {/* Scene 5: Watch Mode (44-52s) */}
        <TransitionSeries.Sequence durationInFrames={8 * fps}>
          <WatchScene />
        </TransitionSeries.Sequence>

        <TransitionSeries.Transition
          presentation={fade()}
          timing={linearTiming({ durationInFrames: Math.round(0.7 * fps) })}
        />

        {/* Scene 6: CTA (52-62s) */}
        <TransitionSeries.Sequence durationInFrames={10 * fps}>
          <CTAScene />
        </TransitionSeries.Sequence>
      </TransitionSeries>
    </AbsoluteFill>
  );
};
