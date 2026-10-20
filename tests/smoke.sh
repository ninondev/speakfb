#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 Ninon
set -eu
cd "$(dirname "$0")/.."

for tool in say ffmpeg python3; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "SKIP: smoke test needs $tool"
        echo "Results: 0 passed, 0 failed, 1 skipped"
        exit 77
    fi
done
if [ ! -x ./speakfb ]; then
    echo "FAIL: build the Swift tool with make first"
    echo "Results: 0 passed, 1 failed, 0 skipped"
    exit 1
fi

tmp=$(mktemp -d "${SPEAKFB_TEST_TMP:-${TMPDIR:-/tmp}}/speakfb-smoke.XXXXXX")
echo "Test files: $tmp"
if ! say -v Samantha -o "$tmp/sample.aiff" "Today I am testing a small speech tool. I will speak about my morning walk, um, and the book I read after breakfast. The air was cool and the street was quiet. I stopped near a tree before I went home."; then
    echo "FAIL: synthetic speech"
    echo "Results: 0 passed, 1 failed, 3 skipped"
    exit 1
fi
echo "PASS: say command"
if ! ffmpeg -v error -y -i "$tmp/sample.aiff" -ac 1 -ar 16000 "$tmp/sample.wav"; then
    echo "FAIL: audio conversion"
    echo "Results: 1 passed, 1 failed, 2 skipped"
    exit 1
fi
if ! python3 -c 'import sys, wave; f = wave.open(sys.argv[1]); assert f.getnframes() > 0, "No audio frames in sample"' "$tmp/sample.wav"; then
    echo "FAIL: sample has no usable audio"
    echo "Results: 1 passed, 1 failed, 2 skipped"
    exit 1
fi
echo "PASS: audio conversion"

if ffmpeg -v error -y -f lavfi -i anullsrc=r=16000:cl=mono -t 0 "$tmp/empty.wav"; then
    if python3 - "$tmp" <<'EMPTY'
import os, subprocess, sys
from pathlib import Path

tmp = Path(sys.argv[1])
env = dict(os.environ, SPEAKFB_ROOT=str(tmp / "data-empty"), SPEAKFB_NO_OPEN="1", TMPDIR=str(tmp))
try:
    result = subprocess.run(
        [sys.executable, "speakfb.py", "--locale", "en-US", str(tmp / "empty.wav")],
        env=env, capture_output=True, text=True, timeout=60,
    )
except subprocess.TimeoutExpired:
    print("FAIL: empty audio hung the pipeline instead of failing")
    sys.exit(1)
output = (result.stdout + result.stderr).strip()
if result.returncode == 0 or "no audio frames" not in output:
    print("FAIL: empty audio must fail with a clear error, rc=" + str(result.returncode))
    print(output[:300])
    sys.exit(1)
print("PASS: empty audio is refused with a clear error")
EMPTY
    then :; else
        echo "Results: 2 passed, 1 failed, 2 skipped"
        exit 1
    fi
else
    echo "FAIL: could not create an empty sample"
    echo "Results: 2 passed, 1 failed, 2 skipped"
    exit 1
fi

python3 - "$tmp" <<'PY'
import csv
import os
from pathlib import Path
import subprocess
import sys

tmp = Path(sys.argv[1])
root = tmp / "data"
env = dict(os.environ, SPEAKFB_ROOT=str(root), SPEAKFB_NO_OPEN="1", TMPDIR=str(tmp))
try:
    result = subprocess.run(
        [sys.executable, "speakfb.py", "--locale", "en-US", str(tmp / "sample.wav")],
        env=env, capture_output=True, text=True, timeout=180,
    )
except subprocess.TimeoutExpired as error:
    output = (error.stdout or b"") + (error.stderr or b"")
    (tmp / "pipeline.log").write_bytes(output)
    print("FAIL: pipeline timed out after 180 seconds; see pipeline.log")
    print("Results: 3 passed, 1 failed, 1 skipped")
    sys.exit(1)

output = result.stdout + result.stderr
(tmp / "pipeline.log").write_text(output)
print(output, end="")
if result.returncode:
    print("FAIL: transcription; see pipeline.log")
    print("The system may need a speech model download. Check the error before retrying.")
    print("Results: 3 passed, 1 failed, 1 skipped")
    sys.exit(1)

reports = list((root / "reports").glob("*.html"))
report_ok = len(reports) == 1 and reports[0].stat().st_size > 0
print(("PASS" if report_ok else "FAIL") + ": one HTML report")
rows = []
if (root / "progress.tsv").exists():
    with (root / "progress.tsv").open(newline="") as file:
        rows = list(csv.reader(file, delimiter="\t"))
progress_ok = len(rows) == 2 and len(rows[1]) == 8 and rows[1][1] == "sample.wav"
print(("PASS" if progress_ok else "FAIL") + ": one progress row")
passed = 3 + int(report_ok) + int(progress_ok)
print(f"Results: {passed} passed, {5 - passed} failed, 0 skipped")
if progress_ok:
    print("Synthetic sample: " + ", ".join(f"{key}={value}" for key, value in zip(rows[0][2:], rows[1][2:])))
sys.exit(0 if report_ok and progress_ok else 1)
PY
