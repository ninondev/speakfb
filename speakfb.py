#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 Ninon
"""Turn a recording into a local speech report and a progress row."""
import argparse
import csv, datetime, html, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("SPEAKFB_ROOT") or os.path.expanduser("~/SpeakFB")
INBOX, REPORTS = os.path.join(ROOT, "inbox"), os.path.join(ROOT, "reports")
LOG = os.path.join(ROOT, "progress.tsv")
TOOL = os.path.join(HERE, "speakfb")
MEDIA = (".mp4", ".mov", ".m4a", ".mp3", ".wav", ".aac", ".3gp", ".webm", ".caf")
FILLERS = {"um", "uh", "er", "ah", "erm", "hmm", "mm"}
SMALL = {"the", "and", "but", "for", "you", "are", "was", "his", "her", "its", "our", "has", "had",
         "not", "can", "did", "does", "that", "this", "with", "from", "they", "them", "what", "when",
         "have", "just", "like", "very", "also", "then", "than", "into", "some", "been", "will"}
PAUSE = 1.0      # Count gaps between words longer than 1 second.
LOWCONF = 0.5    # Flag confidence below 0.5, with the word filters below.


def words_of(path, locale="en-US"):
    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "a.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-vn", "-ac", "1", "-ar", "16000", wav], check=True)
        out = subprocess.run([TOOL, wav, "--locale", locale], capture_output=True, text=True, check=True).stdout
    rows = []
    for line in out.splitlines():
        p = line.split("\t")
        if len(p) == 4:
            rows.append((float(p[0]), float(p[1]), float(p[2]), p[3]))
        elif line.startswith("ERROR"):
            raise RuntimeError(line)
    return rows


def bare(w):
    return re.sub(r"[^a-z']", "", w.lower())


def analyze(rows):
    toks = [r for r in rows if re.search(r"[A-Za-z]", r[3])]
    if not toks:
        return None
    start, end = toks[0][0], toks[-1][1]
    span = max(end - start, 1e-6)
    fill = [r for r in toks if bare(r[3]) in FILLERS]
    spoken = [r for r in toks if bare(r[3]) not in FILLERS]
    gaps = sorted(((b[0] - a[1], a[1]) for a, b in zip(toks, toks[1:]) if b[0] - a[1] > PAUSE), reverse=True)
    low = [r for r in spoken if 0 <= r[2] < LOWCONF and len(bare(r[3])) >= 3 and bare(r[3]) not in SMALL]
    return {
        "span": span, "words": len(spoken), "wpm": len(spoken) / span * 60,
        "pauses": gaps, "fillers": len(fill), "low": low,
        "text": " ".join(r[3] for r in toks),
    }


def mmss(t):
    return "%d:%02d" % (int(t) // 60, int(t) % 60)


def report(src, a):
    name = os.path.basename(src)
    pace = ("Fast: leave time to breathe" if a["wpm"] > 160 else "Steady pace" if a["wpm"] >= 100 else "Slow: try shorter pauses")
    low = "".join("<li><b>%s</b> <span>%s, confidence %.2f</span></li>" % (html.escape(bare(r[3])), mmss(r[0]), r[2]) for r in a["low"][:12]) or "<li>None</li>"
    pauses = "".join("<li>At %s: %.1f seconds</li>" % (mmss(t), g) for g, t in a["pauses"][:5]) or "<li>No pauses longer than 1 second</li>"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Speech feedback {html.escape(name)}</title><style>
:root{{--bg:#F6F7F5;--card:#fff;--ink:#1B211D;--muted:#5D6760;--accent:#1F6F66;--line:#DCE1DC}}
@media (prefers-color-scheme:dark){{:root{{--bg:#111513;--card:#181E1B;--ink:#E4EAE6;--muted:#9AA69F;--accent:#5CC3B2;--line:#27302B}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font:17px/1.6 -apple-system,system-ui,sans-serif}}
main{{max-width:40rem;margin:0 auto;padding:28px 16px 64px}} h1{{font-size:1.2rem;margin:0 0 4px}} .sub{{color:var(--muted);font-size:.9rem;margin:0 0 20px}}
.nums{{display:grid;grid-template-columns:repeat(auto-fit,minmax(6.5rem,1fr));gap:10px;margin-bottom:22px}}
.n{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px}} .n b{{display:block;font-size:1.6rem;font-variant-numeric:tabular-nums}} .n span{{color:var(--muted);font-size:.85rem}}
h2{{font-size:1rem;margin:22px 0 8px}} ul{{margin:0;padding-left:1.2em}} li span{{color:var(--muted);font-size:.9rem}}
.t{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;line-height:1.7}}
</style></head><body><main>
<h1>{html.escape(name)}</h1><p class="sub">{datetime.datetime.now():%Y-%m-%d %H:%M} · Transcribed on this Mac</p>
<div class="nums"><div class="n"><b>{a['span']:.0f} s</b><span>First word to last word</span></div>
<div class="n"><b>{a['words']}</b><span>English words</span></div>
<div class="n"><b>{a['wpm']:.0f}</b><span>Words per minute · {pace}</span></div>
<div class="n"><b>{len(a['pauses'])}</b><span>Pauses over 1 second</span></div>
<div class="n"><b>{a['fillers']}</b><span>um / uh</span></div></div>
<h2>Low-confidence words</h2><p class="sub">The system was less sure about these words. Listen to them again. Names can be wrong. This is not a pronunciation score.</p><ul>{low}</ul>
<h2>Longest pauses</h2><ul>{pauses}</ul>
<h2>Transcript</h2><div class="t">{html.escape(a['text'])}</div>
<p class="sub" style="margin-top:18px">Pace guide: below 100 words per minute is slow; 100 to 160 is steady; above 160 is fast.</p>
</main></body></html>"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--locale", default="en-US", help="Speech locale (default: en-US). English word rules stay the same.")
    parser.add_argument("files", nargs="*", help="Audio or video files. With no files, read the inbox.")
    args = parser.parse_args()
    os.makedirs(INBOX, exist_ok=True); os.makedirs(REPORTS, exist_ok=True)
    files = args.files
    if not files:
        done = set()
        if os.path.exists(LOG):
            with open(LOG, encoding="utf-8") as f:
                done = {r[1] for r in csv.reader(f, delimiter="\t") if len(r) > 1}
        files = [os.path.join(INBOX, f) for f in sorted(os.listdir(INBOX))
                 if f.lower().endswith(MEDIA) and f not in done]
    if not files:
        print("No new recordings. Put audio or video files in:", INBOX); return
    new_log = not os.path.exists(LOG)
    last = None
    for src in files:
        a = analyze(words_of(src, args.locale))
        if not a:
            print("No English words found:", src); continue
        stamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M%S")
        out = os.path.join(REPORTS, stamp + "-" + os.path.splitext(os.path.basename(src))[0] + ".html")
        with open(out, "w", encoding="utf-8") as f:
            f.write(report(src, a))
        with open(LOG, "a", encoding="utf-8", newline="") as f:
            w = csv.writer(f, delimiter="\t")
            if new_log:
                w.writerow(["time", "file", "seconds", "words", "wpm", "long_pauses", "fillers", "low_confidence"]); new_log = False
            w.writerow([stamp, os.path.basename(src), "%.0f" % a["span"], a["words"], "%.0f" % a["wpm"],
                        len(a["pauses"]), a["fillers"], len(a["low"])])
        print("%s: %.0f seconds, %d words, %.0f words/min, %d long pauses, %d fillers, %d low-confidence words"
              % (os.path.basename(src), a["span"], a["words"], a["wpm"], len(a["pauses"]), a["fillers"], len(a["low"])))
        last = out
    if last and not os.environ.get("SPEAKFB_NO_OPEN"):
        subprocess.run(["open", last])


if __name__ == "__main__":
    main()
