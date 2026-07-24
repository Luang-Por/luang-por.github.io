# Karaoke timing pipeline

Regenerates `../data/track{1,2}.json` from the proof-read transcript and the
whisper.cpp large-v3 token-level JSON output.

```bash
python3 align.py ../data
```

Requirements: Python 3, Node 18+ (Intl.Segmenter with Thai ICU). Source paths
(proof text and whisper JSONs under `Downloads/OngPathom/`) are set at the top
of `align.py` — adjust `BASE` if the source material moves.

Method: whisper.cpp writes raw UTF-8 bytes (BPE tokens split mid-character), so
the JSON is parsed via latin-1 to time each byte, then bytes regroup into Thai
characters; token clocks drift, so token times are rescaled into each segment's
window; the human proof text is aligned character-wise with difflib
(autojunk=False) and inherits ASR times; words come from Intl.Segmenter('th');
ASR holes are smoothed by redistributing degenerate spans by character count.
The proof-read text is authoritative — ASR contributes timing only.
