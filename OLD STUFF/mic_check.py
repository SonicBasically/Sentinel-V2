#!/usr/bin/env python3
"""Find the right microphone for Sentinel voice.

Run:  .venv/bin/python mic_check.py
Speak normally for the 4 seconds it listens, then note which device shows the
highest level. Put part of that device's name in ~/.config/sentinel/.env as
SENTINEL_MIC=<part of name>, e.g. SENTINEL_MIC=Kraken, then restart launch.sh.
"""
import time
from array import array

import sounddevice as sd

devices = [(i, d) for i, d in enumerate(sd.query_devices())
           if d["max_input_channels"] > 0 and "(hw:" in d["name"]]
peaks = {i: 0 for i, _ in devices}
streams = []


def make_callback(idx):
    def callback(indata, frames, t, status):
        samples = array("h", bytes(indata))
        if samples:
            peaks[idx] = max(peaks[idx], max(abs(x) for x in samples))
    return callback


for idx, d in devices:
    try:
        s = sd.RawInputStream(samplerate=int(d["default_samplerate"]), device=idx,
                              dtype="int16", channels=1, callback=make_callback(idx))
        s.start()
        streams.append(s)
    except Exception as e:
        print(f"  skipped [{idx}] {d['name']}: {str(e)[:60]}")

print("\nListening for 4 seconds. Speak normally now...")
time.sleep(4)
for s in streams:
    s.stop()
    s.close()

print("\nPeak level per device (out of 32767; speech is usually in the thousands):")
for idx, d in sorted(devices, key=lambda x: -peaks[x[0]]):
    bar = "#" * min(40, peaks[idx] // 400)
    print(f"  [{idx:2}] {peaks[idx]:6}  {bar:<40}  {d['name']}")
