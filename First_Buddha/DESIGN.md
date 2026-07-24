# First_Buddha — Design Document
**Date:** 2026-07-25 · **URL:** http://lunarwisdom.luangpor.com/First_Buddha/

A Dharma tribute website honoring พระเดชพระคุณ หลวงพ่อสมปอง สุธัมมสันตจิตโต (ท่านจิตโต),
presenting his Dhamma talk on สมเด็จองค์ปฐม (พระพุทธสิขีทศพลที่ 1), delivered at
ศาลา 12 ไร่ on 8 ธันวาคม 2544, with audio playback perfectly synchronized to the
proof-read transcription by Teera Jarawuttiyakorn — karaoke-style word highlighting included.

## Architecture

Static subdirectory of `luang-por.github.io` (GitHub Pages, custom domain via CNAME):

```
First_Buddha/
├── index.html          # single-file Aurora-Prime artifact (NeXus_Architect_v19)
├── audio/OngPathom1.mp3, OngPathom2.mp3
├── data/track1.json, track2.json   # word-level karaoke timing
├── img/hero.jpg        # optimized enhanced image (LuangPor Sompong & Tanat Tonguthaisri)
└── DESIGN.md
```

## Karaoke timing pipeline (offline, deterministic)

1. **Token timeline** — whisper.cpp large-v3 JSON (`transcripts/raw/largev3/*.json`)
   provides per-token millisecond timestamps. Tokens are concatenated per segment and
   validated against segment text; each character gets an interpolated [start, end].
2. **Alignment** — the human proof-read text (authoritative) is aligned character-by-character
   to the ASR character stream with `difflib.SequenceMatcher(autojunk=False)`
   (whitespace-stripped). Matched proof characters inherit ASR times; edits/insertions are
   linearly interpolated between anchors. Monotonicity is enforced.
3. **Word segmentation** — each proof line is segmented into Thai words with Node 22
   `Intl.Segmenter('th', {granularity:'word'})` (ICU dictionary). Every word span maps
   back to character times → `[word, start_ms, end_ms]`.
4. **Gap smoothing** — whisper token clocks drift, so token times are rescaled into each
   segment's window; where ASR holes left proof lines without anchors (three regions),
   degenerate zero-duration word runs are redistributed across the surrounding window by
   character count, and fully-collapsed lines are merged with the preceding line's span.
5. **Output** — per track: `{id, title, audio, duration, lines:[{s, e, w:[[text,s,e],…]}]}`,
   where concatenating `w` texts reconstructs the proof line exactly.
   Validation: match ratio, global word-level monotonicity, duration coverage,
   exact text reconstruction, no collapsed lines.

## Frontend (index.html) — Nexus-Architect v19 "Aurora-Prime" compliance

- **Aurora Glass palette**, CSS `@layer` micro-framework, no external CSS/icon frameworks;
  inline SVG icons; Inter + Sarabun + JetBrains Mono fonts.
- **Dual-tier Antigravity Halo** (65,536 particles: three.js GPGPU Tier A, Canvas-2D Tier B
  fallback, `?halo=2d` debug) — the levitating luminous ring doubles as a Buddhist aura motif.
- **Hero:** the enhanced image at the very top (user requirement), spectrum headline.
- **Player:** dual-track playlist; custom controls; scrolling transcript that auto-centers the
  active line; **karaoke word highlight** — the active word fills left→right with the spectrum
  gradient via `background-clip:text` + a CSS custom property driven by `requestAnimationFrame`
  (binary search over word timings); sung words stay tinted; click any word/line to seek.
  Auto-scroll pauses on user scroll (resume button). Playback-speed + font-size **reactive
  sliders** (Filter-Flow), transcript search, copy-share-link-at-timestamp (glass toast),
  keyboard shortcuts, Media Session API, `?track=&t=` deep links, localStorage resume.
- **Insights:** Chart.js "sermon flow" (speech density over time, click-to-seek) and a
  **polymorphic D3 concept topology** of key Dhamma terms — node click jumps the audio to the
  first utterance of that term. Key-teaching cards carry spectrum progress bars (position of
  each teaching within the talk) and seek on click.
- **i18n:** `body[data-lang]` CSS toggling, Thai default, EN for framing copy (transcript is Thai).
- **Resilience/A11y:** CDN retry loop, three.js importmap 4s settlement → Tier B, context-loss
  fallback, `prefers-reduced-motion` settles the halo, semantic transcript markup, OG metadata.

## Review outcomes (2026-07-25)

A 38-agent multi-lens review (JS correctness, data integrity, spec compliance, a11y/perf,
Thai content) confirmed and led to fixes for: a loadTrack race (sequence token), promise-cached
data fetches, storage-blocked resilience (`store` helper), fetch-failure retry, clipboard
fallback for http, autoplay inside the gesture window, `.past` line marking, scroll-override
detection for scrollbar/keyboard, resume-chip CSS, karaoke contrast & width-stable highlighting,
deferred CDN scripts, timestamp buttons + ARIA states, localized runtime strings, and a Tier B
halo governor that settles to a static frame on CPU-bound devices (the 65,536-particle
population is never culled, per spec). Accepted as-is: Tier A has no GPU governor (spec parity;
context-loss falls back to Tier B), and the พระเดชพระคุณ honorific follows the commissioning
request. Note for local previews: `python3 -m http.server` lacks HTTP Range support, so audio
seeking is clamped locally; GitHub Pages serves ranges correctly.

## Provenance rules

Transcript = human proof-read text (Teera Jarawuttiyakorn). ASR is used **only** for timing,
never for words. Timing is heuristic alignment — good to word level, not laboratory-exact.
