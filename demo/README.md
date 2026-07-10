# CallSense demo data — Phase 5

Reserved. Holds the synthetic Hinglish call scripts, TTS-rendered stereo audio,
pre-computed history fixtures, and `seed.py` (1 org, 3 teams, 9 advisors, ~25
calls). `make seed` loads it so the dashboards have trend lines on first run.

```
demo/
├─ scripts/    scripted call dialogues (great discovery, over-promiser, ...)
├─ audio/      TTS-rendered .wav recordings (gitignored) + inbox/ + store/
├─ fixtures/   pre-transcribed / pre-analysed history for bulk seeding
└─ seed.py     loads org/teams/advisors + calls
```
