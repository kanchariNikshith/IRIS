# R2 single-owner audio — 15 Oct 2026

Status: **automated checks passed** for the one-turn audio foundation. Depends on
R0/R1 automated baseline; hardware acceptance
remains pending. No native microphone/audio/model downloads or cloud calls used.

CaptureOwner now owns the 16 kHz mono stream inside the existing cancellable
subprocess, with one native stream lease plus a parent Ears capture-worker lease.
Close/cancel/overflow/device errors clear its bounded ring and release ownership.
An unreapable subprocess permanently latches the parent capture lease until a
runtime restart, preventing a replacement stream alongside a possible orphan.
The existing worker watchdog still terminates/reaps blocking drivers. Orb listening
state follows successful stream start and ends before transcription.

AudioRing provides bounded chronological pre-roll; PCMFrames converts the current
100 ms float blocks to exact detector-sized int16 frames with retained partial
tails and saturating conversion. These are integration primitives: ambient wake
monitoring is not enabled. Existing RMS voice endpointing is separated as EnergyVAD;
it is not a trained speech/noise classifier. Five-second no-speech, 1.2-second
trailing silence, fifteen-second utterance and parent timeouts remain bounded.

Ears.transcribe accepts bounded captured audio without another stream; command
capture delegates to CaptureOwner. Whisper remains local and only runs for a
command. No continuous transcription or separate PyAudio listener was introduced.

Automated checks inject device overflow, read/close faults, concurrency, invalid
audio, cancellation, pre-roll and frame conversion. An audio→Ears→VoiceController→
real local Brain/registry/clock/audit→reply→shutdown integration uses synthetic
device samples and mocked ASR/TTS; it is not real-device acceptance.

Full offline suite with the Qt local endpoint available:
`.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-tmp-r2-full`:
**405 passed in 33.61s**. pip check, compileall and masked --check also pass.
The first isolated audio/voice subset had one existing 3-second provider-worker
test timeout (68 passed); the focused recheck passed all 23 tests, and the full
suite then passed without changing its timeout or weakening its assertion.

Pending Windows: mic permissions/unplug/stall; no-speech/noisy-room/soft-voice
endpointing; immediate speech; pause/kill at each stage; actual orb mic indicator;
no orphan process after device hang; reopen capture after failure. Ambient
pause/buffer behavior across wake sessions requires R3/R4 rather than being
inferred from one-turn tests. Python 3.11 compatibility remains untested.
