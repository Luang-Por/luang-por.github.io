#!/usr/bin/env python3
"""Align human proof-read Thai transcript to whisper.cpp token timestamps.

Produces per-track JSON: {id, title, audio, duration, lines:[{s,e,w:[[text,s,e],...]}]}
Words come from the proof text ONLY; ASR supplies timing, never words.
"""
import json, re, subprocess, sys, unicodedata
from difflib import SequenceMatcher
from pathlib import Path

BASE = Path("/Users/twotothepowerofseven/Downloads/OngPathom")
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
NODE_SEG = Path(__file__).parent / "segment_words.mjs"

SPECIAL = re.compile(r"^\[_.*\]$")
WS = re.compile(r"\s")


def load_asr_chars(json_path):
    """-> (chars:str, starts:[ms], ends:[ms]) for non-whitespace chars, plus stats.

    whisper.cpp writes raw UTF-8 bytes; BPE tokens can split mid-character, making
    the file invalid UTF-8. Decode latin-1 (byte<->char 1:1), time each byte from
    its token, then regroup bytes into real characters.
    """
    data = json.loads(json_path.read_bytes().decode("latin-1"))
    chars, starts, ends = [], [], []
    seg_fallbacks = 0
    for seg in data["transcription"]:
        seg_bytes = seg["text"].encode("latin-1")
        s0, s1 = seg["offsets"]["from"], seg["offsets"]["to"]
        toks = [t for t in seg.get("tokens", []) if not SPECIAL.match(t["text"])]
        concat = b"".join(t["text"].encode("latin-1") for t in toks)
        stripped = seg_bytes.strip()
        # per-byte timing over the segment's byte string
        if concat == seg_bytes or concat == stripped:
            target = seg_bytes if concat == seg_bytes else stripped
            b_start, b_end = [], []
            for t in toks:
                tb = t["text"].encode("latin-1")
                a, b = t["offsets"]["from"], t["offsets"]["to"]
                n = max(1, len(tb))
                for i in range(len(tb)):
                    b_start.append(a + (b - a) * i / n)
                    b_end.append(a + (b - a) * (i + 1) / n)
            # whisper.cpp token clocks drift behind real time; segment offsets are
            # reliable. Rescale token times into the segment window, keeping rhythm.
            if b_start:
                lo, hi = min(b_start), max(b_end)
                if hi > lo:
                    k = (s1 - s0) / (hi - lo)
                    b_start = [s0 + (t - lo) * k for t in b_start]
                    b_end = [s0 + (t - lo) * k for t in b_end]
                else:
                    b_start = [float(s0)] * len(b_start)
                    b_end = [float(s1)] * len(b_end)
        else:
            seg_fallbacks += 1
            target = seg_bytes
            n = max(1, len(target))
            b_start = [s0 + (s1 - s0) * i / n for i in range(len(target))]
            b_end = [s0 + (s1 - s0) * (i + 1) / n for i in range(len(target))]
        # regroup bytes -> characters (UTF-8 lead-byte boundaries)
        text = target.decode("utf-8", errors="replace")
        bi = 0
        for ch in text:
            nb = len(ch.encode("utf-8")) if ch != "�" else 1
            i0, i1 = bi, min(bi + nb, len(target)) - 1
            bi += nb
            if i1 < i0 or i0 >= len(b_start):
                continue
            if ch == "�" or WS.match(ch):
                continue
            chars.append(ch)
            starts.append(b_start[i0])
            ends.append(b_end[min(i1, len(b_end) - 1)])
    return "".join(chars), starts, ends, seg_fallbacks


def parse_proof():
    """Split proof file into two tracks; return [(header_lines, content_lines), ...]."""
    text = BASE.joinpath("NotebookLM/OngPathom_proof.txt").read_text(encoding="utf-8")
    text = unicodedata.normalize("NFC", text)
    lines = text.split("\n")
    marks = [i for i, l in enumerate(lines) if l.startswith("ถอดความธรรมบรรยาย")]
    assert len(marks) == 2, marks
    tracks = []
    for ti, start in enumerate(marks):
        end = marks[ti + 1] if ti + 1 < len(marks) else len(lines)
        block = lines[start:end]
        header, content, in_header = [], [], True
        for l in block:
            if in_header and (l.startswith(("ถอดความ", "ผู้แสดงธรรม", "ศาลา", "ไฟล์เสียง")) or not l.strip()):
                if l.strip():
                    header.append(l.strip())
                continue
            in_header = False
            if l.strip():
                content.append(l.strip())
        tracks.append((header, content))
    return tracks


def segment_lines(content):
    p = subprocess.run(["node", str(NODE_SEG)], input=json.dumps(content),
                       capture_output=True, text=True, check=True)
    return json.loads(p.stdout)


def align_track(track_idx, asr_json, content, duration_ms):
    asr_str, a_start, a_end, seg_fb = load_asr_chars(asr_json)

    # proof char stream (non-whitespace) with back-map to (line, col)
    p_chars, p_map = [], []
    line_col_to_stream = []  # per line: {col: stream_idx}
    for li, line in enumerate(content):
        colmap = {}
        for ci, ch in enumerate(line):
            if not WS.match(ch):
                colmap[ci] = len(p_chars)
                p_chars.append(ch)
                p_map.append((li, ci))
        line_col_to_stream.append(colmap)
    p_str = "".join(p_chars)

    sm = SequenceMatcher(None, asr_str, p_str, autojunk=False)
    blocks = sm.get_matching_blocks()
    match_ratio = sum(b.size for b in blocks) / max(1, len(p_str))

    N = len(p_str)
    t0 = [None] * N
    t1 = [None] * N
    for b in blocks:
        for k in range(b.size):
            t0[b.b + k] = a_start[b.a + k]
            t1[b.b + k] = a_end[b.a + k]

    # interpolate unmatched runs between anchors
    j = 0
    while j < N:
        if t0[j] is not None:
            j += 1
            continue
        run_start = j
        while j < N and t0[j] is None:
            j += 1
        run_end = j  # exclusive
        left = t1[run_start - 1] if run_start > 0 else None
        right = t0[run_end] if run_end < N else None
        if left is None and right is None:
            left, right = 0.0, float(duration_ms)
        elif left is None:
            left = max(0.0, right - 180.0 * (run_end - run_start))
        elif right is None:
            right = min(float(duration_ms), left + 180.0 * (run_end - run_start))
        n = run_end - run_start
        for k in range(n):
            t0[run_start + k] = left + (right - left) * k / n
            t1[run_start + k] = left + (right - left) * (k + 1) / n

    # enforce monotonicity
    prev = 0.0
    for k in range(N):
        t0[k] = max(t0[k], prev)
        t1[k] = max(t1[k], t0[k])
        prev = t0[k]

    # word segmentation and timing
    words_per_line = segment_lines(content)
    flat = []  # word records across all lines: [line_idx, text, s, e, timed]
    last_end = 0.0
    for li, (line, words) in enumerate(zip(content, words_per_line)):
        col = 0
        for w in words:
            idxs = [line_col_to_stream[li][col + i] for i, ch in enumerate(w)
                    if (col + i) in line_col_to_stream[li]]
            if idxs:
                ws_ = min(t0[i] for i in idxs)
                we_ = max(t1[i] for i in idxs)
                ws_ = max(ws_, last_end)
                we_ = max(we_, ws_)
                last_end = we_
                flat.append([li, w, ws_, we_, True])
            else:  # whitespace / punctuation-only token
                flat.append([li, w, last_end, last_end, False])
            col += len(w)

    # Smooth ASR-gap collapses: where alignment had no anchors, runs of words
    # end up with ~zero duration next to one absurdly stretched word. Find runs
    # of near-zero timed words, widen the window to the preceding timed word,
    # and redistribute the window across all timed words by character length.
    MIN_DUR = 80.0
    i = 0
    n = len(flat)
    while i < n:
        if not flat[i][4] or (flat[i][3] - flat[i][2]) >= MIN_DUR:
            i += 1
            continue
        j = i  # run of degenerate timed words [i, j]
        while j + 1 < n and flat[j + 1][4] and (flat[j + 1][3] - flat[j + 1][2]) < MIN_DUR:
            j += 1
        # window: start at previous timed word's start (it may hold the whole
        # collapsed span), end at the run's end (next word starts there anyway)
        k = i - 1
        while k >= 0 and not flat[k][4]:
            k -= 1
        w_start = flat[k][2] if k >= 0 else max(0.0, flat[i][2] - 400.0 * (j - i + 1))
        w_end = flat[j][3]
        members = ([k] if k >= 0 else []) + [m for m in range(i, j + 1) if flat[m][4]]
        total_chars = sum(len(flat[m][1]) for m in members)
        if w_end - w_start > 250.0 and total_chars:
            cur = w_start
            for m in members:
                share = (w_end - w_start) * len(flat[m][1]) / total_chars
                flat[m][2] = cur
                flat[m][3] = cur = cur + share
        i = j + 1

    out_lines = []
    last_end = 0.0
    li_words = {}
    for rec in flat:
        li_words.setdefault(rec[0], []).append(rec)
    for li in range(len(content)):
        w_out = []
        for _, w, ws_, we_, timed in li_words.get(li, []):
            if timed:
                ws_ = max(ws_, last_end)
                we_ = max(we_, ws_)
                last_end = we_
                w_out.append([w, int(round(ws_)), int(round(we_))])
            else:
                w_out.append([w, int(round(last_end)), int(round(last_end))])
        timed_ws = [w for w in w_out if w[2] > w[1]]
        ls = timed_ws[0][1] if timed_ws else int(round(last_end))
        le = timed_ws[-1][2] if timed_ws else int(round(last_end))
        out_lines.append({"s": ls, "e": le, "w": w_out})

    # Line-level rescue: a fully-collapsed line (all words at one instant) means
    # the ASR hole swallowed this line together with the preceding one, whose
    # words absorbed the entire window. Redistribute the combined span evenly
    # (by character count) across both lines' words.
    def _thai(w):
        return any("ก" <= c <= "๏" for c in w)
    for li in range(len(out_lines)):
        L = out_lines[li]
        if L["e"] - L["s"] > 200 or not any(_thai(w[0]) for w in L["w"]):
            continue
        if li == 0:
            continue
        P = out_lines[li - 1]
        w_start, w_end = P["s"], max(L["e"], P["e"])
        members = [w for w in P["w"] + L["w"] if _thai(w[0])]
        total_chars = sum(len(w[0]) for w in members)
        if w_end - w_start < 2000 or not total_chars:
            continue
        cur = float(w_start)
        for w in members:
            share = (w_end - w_start) * len(w[0]) / total_chars
            w[1] = int(round(cur))
            cur += share
            w[2] = int(round(cur))
        for X in (P, L):
            for w in X["w"]:
                if not _thai(w[0]):
                    w[1] = w[2] = max(w[1], X["w"][0][1])
            timed_ws = [w for w in X["w"] if w[2] > w[1]]
            if timed_ws:
                X["s"], X["e"] = timed_ws[0][1], timed_ws[-1][2]

    # final global monotonicity guarantee over word starts/ends
    prev = 0
    for L in out_lines:
        for w in L["w"]:
            if w[2] > w[1]:
                w[1] = max(w[1], prev)
                w[2] = max(w[2], w[1])
                prev = w[1]
        timed_ws = [w for w in L["w"] if w[2] > w[1]]
        if timed_ws:
            L["s"], L["e"] = timed_ws[0][1], timed_ws[-1][2]

    stats = {
        "match_ratio": round(match_ratio, 4),
        "asr_chars": len(asr_str),
        "proof_chars": N,
        "segment_fallbacks": seg_fb,
        "first_ms": out_lines[0]["s"],
        "last_ms": out_lines[-1]["e"],
        "duration_ms": duration_ms,
    }
    return out_lines, stats


def main():
    durations = {1: 1842390, 2: 1711308}
    titles = {
        1: "สมเด็จองค์ปฐม พระพุทธสิขีทศพลที่ ๑ (ตอนที่ ๑)",
        2: "สมเด็จองค์ปฐม พระพุทธสิขีทศพลที่ ๑ (ตอนที่ ๒)",
    }
    tracks = parse_proof()
    OUT.mkdir(parents=True, exist_ok=True)
    for n, (header, content) in enumerate(tracks, start=1):
        best = None
        for model in ("largev3", "turbo"):
            asr_json = BASE / f"transcripts/raw/{model}/OngPathom{n}.json"
            lines_, stats = align_track(n, asr_json, content, durations[n])
            stats["model"] = model
            print(f"track{n} {model}: {json.dumps(stats, ensure_ascii=False)}")
            if best is None or stats["match_ratio"] > best[1]["match_ratio"]:
                best = (lines_, stats)
        lines_, stats = best
        doc = {
            "id": f"OngPathom{n}",
            "title": titles[n],
            "audio": f"audio/OngPathom{n}.mp3",
            "duration": durations[n] / 1000.0,
            "header": header,
            "timing_model": stats["model"],
            "lines": lines_,
        }
        # integrity: words reconstruct lines exactly
        for line, ol in zip(content, lines_):
            assert "".join(w[0] for w in ol["w"]) == line
        path = OUT / f"track{n}.json"
        path.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")),
                        encoding="utf-8")
        print(f"track{n}: chose {stats['model']}, wrote {path} "
              f"({path.stat().st_size//1024} KB, {len(lines_)} lines)")


if __name__ == "__main__":
    main()
