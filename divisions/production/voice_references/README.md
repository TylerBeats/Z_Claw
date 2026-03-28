# Voice Reference Files

Place `{commander}.wav` files here to enable XTTS v2 voice cloning.

## Requirements
- Format: WAV (any sample rate; XTTS resamples internally)
- Duration: 5–30 seconds of clean, clear speech
- Content: Natural speech with minimal background noise or music

## Commanders
| File | Commander |
|------|-----------|
| `vael.wav` | VAEL — tactical analyst, cold precision |
| `seren.wav` | SEREN — pattern recognition, calm authority |
| `kaelen.wav` | KAELEN — forge master, relentless drive |
| `lyrin.wav` | LYRIN — healer, warm resolve |
| `zeth.wav` | ZETH — shadow operative, terse and quiet |
| `lyke.wav` | LYKE — craftsperson, direct confidence |

## How It Works
When `voice_generate.py` synthesizes for a commander it checks for `{commander}.wav`
here. If found, it uses XTTS `tts_with_vc()` for voice cloning. If not found,
it falls back to the built-in `Claribel Dervla` speaker.

Generated audio is written to:
`mobile/assets/generated/voice/{commander}/{queue_id}.wav`
