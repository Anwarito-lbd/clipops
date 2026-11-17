# TikTok Viral Brain — Obsidian starter vault

A local-first research vault for GTA 6 edits, viral gaming clips, and streamer reaction formats. **No videos or metrics were scraped, and no viral examples are falsely asserted.**

## Start
1. Install [Obsidian](https://obsidian.md/). Extract this ZIP. In Obsidian choose **Open folder as vault** and select the `TikTok-Viral-Brain` folder.
2. Open `00 Home.md`. Enable the built-in **Bases** plugin in Obsidian settings if necessary. Open `Clips.base` to view your clip database.
3. Find clips in [TikTok Creative Center](https://ads.tiktok.com/creative/creativeCenter/trends) or directly in TikTok using terms from `01 Discovery/Watchlist.md`.
4. Add a clip from this directory with Python 3.10+ (no packages needed):

   ```bash
   python tools/brain.py add "https://www.tiktok.com/@example/video/1234567890000000000" --category gta6 --style beat-drop-reveal --hook "Payoff preview in first second" --views 100000 --likes 10000 --shares 500
   ```
   The URL and statistics above are **synthetic examples**. Use real copied links and numbers you personally verify.
5. Paste observations into the generated markdown note: opening hook, cuts, text, audio, transitions, reveal, first/last frames, timestamped beat map. Mark the clip `reviewed: true` when finished.
6. Run `python tools/brain.py report` to generate `09 Reports/Latest Report.md` and `python tools/brain.py rules` to export candidate rule weights to `exports/clipper_edit_rules.json`.

## Bulk CSV import
`python tools/brain.py import-csv tools/examples.template.csv`
Columns: url, category, creator, caption, views, likes, comments, shares, duration_seconds, posted_at, observed_at, style, hook, source, reviewed. Numeric cells can be empty; an empty metric means **unknown**, not zero. CSV rows with empty URL are skipped. The supplied CSV is a header-only template, so no fabricated posts are imported.

## Optional AI notes assistant
After you **personally inspect** a clip and add notes, run:

```bash
pip install openai
# Set OPENAI_API_KEY in your shell; paid API use is separate from a ChatGPT subscription.
python tools/brain.py ai-analyze "02 Clips/<your-note-name>.md" --model gpt-5.5
```

This sends *only the Markdown note you select* to the API and appends a labelled hypothesis/strategy analysis. It does **not** watch a TikTok video, fetch the audio, or infer unseen footage. Avoid adding sensitive data to notes sent to an API.

## What works automatically and what does not
**Works locally:** Markdown notes, duplicate URL detection, supported URL validation, source links, CSV import, computed engagement ratios from observed numbers, reports, Obsidian Bases view, reusable editing rules, optional AI analysis of user-provided observations.

**Not automatic in this MVP:** Endless TikTok feed browsing, scraping TikTok's For You feed, acquiring all viral videos, live view counts, downloading others' video files, or direct Twitch clipping integration. Public oEmbed metadata may be available for individual URLs but isn't a general viral-search or analytics API. These are deliberately not faked.

## Ethical / permissions
Use others' clips as *research references*. Reposting copyrighted footage/audio may require permission, and account/channel or platform restrictions may apply. Do not use unauthorized scraping or bypass access controls. Link to source creators. Avoid implying unverified fan concepts are official GTA VI footage.

## How scoring works
Reports use metrics entered at the date of observation. Engagement rate = (likes + comments + shares) / views, **only if all four numbers exist and views > 0**. Shares per 1,000 views requires shares + views. The report does **not** claim these metrics cause virality. Compare like-for-like samples and check publish age before drawing conclusions.

## Sources checked November 17, 2026
- https://ads.tiktok.com/creative/creativeCenter/trends
- https://developers.tiktok.com/docs/en/embed-videos
- https://developers.tiktok.com/docs/en/research-api-faq
- https://obsidian.md/help/bases
- https://obsidian.md/help/bases/syntax
- https://developers.openai.com/api/reference/python
