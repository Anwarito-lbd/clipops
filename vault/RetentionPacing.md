---
tags:
  - pipeline
---

# Retention Pacing Math

Upstream: [[Transcription]], [[SceneDetection]] · Sibling: [[Scoring]], [[Hooks]] · UI Inspector: [[OperatorUI]]

Implemented in `packages/services/clip_ranking.py` (`ClipRankingService.rank_footage` and `compute_retention_pacing`).

## Composite Clip Score Equation

Each candidate scene window $[t_0, t_1]$ with duration $\Delta t = t_1 - t_0$ is scored on a deterministic $0\text{–}100$ scale without calling an external LLM:

$$S_{\text{total}} = \text{clip}_{[0, 100]}\Big(0.18\,H + 0.12\,U + 0.12\,C + 0.12\,E + 0.18\,P + 0.12\,L + 0.10\,F + 0.06\,D - 0.05\,A_{\text{dead}}\Big)$$

Where:
- $H$: `hook_score` (`strong_opening` regex match in first sentence + `8.0` boost if `hook_type` matches operator preference)
- $P$: `payoff_score` (`clear_payoff` resolution cues)
- $U, C, E$: `curiosity`, `conflict_surprise`, `emotional_reaction`
- $L$: `standalone_clarity` (`70.0` when $8 \le N_{\text{words}} \le 80$, else `45.0`)
- $F$: `campaign_relevance`
- $D$: `duration_score` (`80` for `15-25`, `90` for `25-40`, `70` for `40-60`, `+10` on band match)
- $A_{\text{dead}}$: dead-air penalty $\max(0, 40 - 2 N_{\text{words}})$ when $\Delta t > 10\text{ s}$

## Pacing & Cadence Telemetry (`compute_retention_pacing`)

- **Speaking Rate (WPM)**: $\text{WPM} = \frac{N_{\text{words}}}{\Delta t} \times 60$, targeting `[125, 185]` WPM (`OPTIMAL_CADENCE`). Above `185` is `FAST_ENERGETIC`; `75–125` is `MODERATE`; `<75` is `SPARSE_LOW_SPEECH`.
- **Spoken Coverage & Dead-Air Ratio**: Sums forced-alignment `word_segments` overlap inside $[t_0, t_1]$ (or $0.35\text{ s/word}$ fallback) so $\text{dead\_air\_ratio} = \frac{\max(0, \Delta t - t_{\text{spoken}})}{\Delta t}$.
- **3-Second Hook Density**: Counts aligned words starting inside $[t_0, t_0 + 3.0\text{ s}]$ to verify immediate viewer retention before visual drop-off.

Thresholds: $S_{\text{total}} \ge 80 \implies \text{HIGH}$, $S_{\text{total}} \ge 60 \implies \text{MEDIUM}$, else $\text{LOW}$. See [[EXAMPLES]] for live pacing metrics.
