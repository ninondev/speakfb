#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 Ninon
"""Turn a recording into a local speech report and a progress row."""
import argparse
import csv, datetime, html, os, re, subprocess, sys, tempfile, wave

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
        with wave.open(wav) as w:
            # The Swift tool never finishes on a file with no frames.
            if w.getnframes() == 0:
                sys.exit(f"ERROR: no audio frames in {path}")
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
    wpm = a["wpm"]
    zone = "fast" if wpm > 160 else "steady" if wpm >= 100 else "slow"
    pace = ("Fast: leave time to breathe" if zone == "fast" else "Steady pace" if zone == "steady" else "Slow: try shorter pauses")
    mark = min(max((wpm - 60) / 160 * 100, 0.5), 99.5)  # scale runs 60 to 220 words per minute
    low = "".join("<li><b>%s</b> <span>%s, confidence %.2f</span></li>" % (html.escape(bare(r[3])), mmss(r[0]), r[2]) for r in a["low"][:12])
    low = "<ul>%s</ul>" % low if low else '<p class="none">None</p>'
    pauses = "".join("<li>At %s: %.1f seconds</li>" % (mmss(t), g) for g, t in a["pauses"][:5])
    pauses = "<ul>%s</ul>" % pauses if pauses else '<p class="none">No pauses longer than 1 second</p>'
    text = " ".join(re.sub(r"^(\W*)(.*?)(\W*)$", lambda m: html.escape(m[1]) + "<mark>" + html.escape(m[2]) + "</mark>" + html.escape(m[3]), w)
                    if bare(w) in FILLERS else html.escape(w) for w in a["text"].split(" "))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Speech feedback {html.escape(name)}</title><style>
:root{{--bg:#F6F7F5;--card:#fff;--ink:#1B211D;--muted:#5D6760;--accent:#1F6F66;--soft:#DCEBE7;--line:#DCE1DC;color-scheme:light dark}}
@media (prefers-color-scheme:dark){{:root{{--bg:#111513;--card:#181E1B;--ink:#E4EAE6;--muted:#9AA69F;--accent:#5CC3B2;--soft:#1E3A35;--line:#27302B}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font:17px/1.6 -apple-system,system-ui,sans-serif}}
::selection{{background:var(--soft);color:var(--ink)}}
main{{max-width:40rem;margin:0 auto;padding:32px 16px 64px}} h1{{font-size:1.2rem;margin:0 0 2px}} .sub{{color:var(--muted);font-size:.9rem;margin:0 0 20px}}
.pace{{margin:28px 0 30px}} .wpm{{margin:0;font-size:1rem;color:var(--muted)}}
.wpm b{{font-size:3.4rem;line-height:1;color:var(--ink);font-weight:700;letter-spacing:-.02em;font-variant-numeric:tabular-nums;margin-right:8px}}
.verdict{{margin:6px 0 16px;font-size:1.15rem;font-weight:600;color:var(--accent)}}
.zones{{position:relative;display:grid;grid-template-columns:25% 37.5% 37.5%;height:10px;border-radius:5px;overflow:visible}}
.zones i{{background:var(--line)}} .zones i:first-child{{border-radius:5px 0 0 5px}} .zones i:nth-child(3){{border-radius:0 5px 5px 0}}
.zones i.on{{background:var(--accent)}}
.zones .mk{{position:absolute;top:-6px;width:4px;height:22px;margin-left:-2px;background:var(--ink);border-radius:2px;box-shadow:0 0 0 2px var(--bg)}}
.ticks{{position:relative;height:1.4em;font-size:.8rem;color:var(--muted);font-variant-numeric:tabular-nums;margin-top:6px}}
.ticks span{{position:absolute;transform:translateX(-50%)}} .ticks .z{{transform:none}}
.pace .sub{{margin:10px 0 0}}
.nums{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:0 20px;margin:0 0 8px}}
.nums div{{display:flex;flex-direction:column-reverse;justify-content:flex-end;border-top:2px solid var(--ink);padding-top:8px}}
.nums dd{{margin:0;font-size:1.5rem;font-weight:700;line-height:1.2;font-variant-numeric:tabular-nums}} .nums dt{{color:var(--muted);font-size:.85rem;line-height:1.35;margin-top:4px}}
h2{{font-size:1rem;margin:32px 0 8px}} ul{{margin:0;padding-left:1.2em}} li+li{{margin-top:2px}} li span{{color:var(--muted);font-size:.9rem}}
.none{{margin:0;color:var(--muted)}}
.t{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;line-height:1.75}}
mark{{background:var(--soft);color:var(--ink);border-radius:3px;padding:0 3px}}
@media (max-width:520px){{.nums{{grid-template-columns:repeat(2,minmax(0,1fr));gap:16px 20px}} .wpm b{{font-size:2.8rem}}}}
</style></head><body><main>
<h1>{html.escape(name)}</h1><p class="sub">{datetime.datetime.now():%Y-%m-%d %H:%M} · Transcribed on this Mac</p>
<section class="pace"><p class="wpm"><b>{wpm:.0f}</b>Words per minute</p><p class="verdict">{pace}</p>
<div role="img" aria-label="Pace scale: {wpm:.0f} words per minute is in the {zone} zone"><div class="zones"><i{' class="on"' if zone == "slow" else ''}></i><i{' class="on"' if zone == "steady" else ''}></i><i{' class="on"' if zone == "fast" else ''}></i><span class="mk" style="left:{mark:.1f}%"></span></div>
<div class="ticks" aria-hidden="true"><span class="z" style="left:0">slow</span><span style="left:25%">100</span><span style="left:43.75%">steady</span><span style="left:62.5%">160</span><span style="left:81.25%">fast</span></div></div>
<p class="sub">Pace guide: below 100 words per minute is slow; 100 to 160 is steady; above 160 is fast.</p></section>
<dl class="nums"><div><dt>First word to last word</dt><dd>{a['span']:.0f} s</dd></div>
<div><dt>English words</dt><dd>{a['words']}</dd></div>
<div><dt>Pauses over 1 second</dt><dd>{len(a['pauses'])}</dd></div>
<div><dt>um / uh</dt><dd>{a['fillers']}</dd></div></dl>
<h2>Low-confidence words</h2><p class="sub">The system was less sure about these words. Listen to them again. Names can be wrong. This is not a pronunciation score.</p>{low}
<h2>Longest pauses</h2>{pauses}
<h2>Transcript</h2><div class="t">{text}</div>
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
