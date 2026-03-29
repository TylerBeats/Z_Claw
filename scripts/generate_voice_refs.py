"""
generate_voice_refs.py — Bootstrap voice reference WAVs for all commanders.

Uses pyttsx3 (already installed, no GPU required) to synthesize a short
reference line for each commander, then applies per-commander pitch transforms
using only Python stdlib (wave + struct + math) so each reference has
meaningfully different acoustic characteristics before being handed to
Coqui XTTS v2 for voice cloning.

Voice differentiation strategy
-------------------------------
XTTS v2 voice-cloning reads the reference WAV for pitch, speaking pace, and
vocal texture.  We steer all three with zero extra dependencies:

  * Speaking rate  — pyttsx3 ``rate`` property (words per minute)
  * Pitch          — resample the raw PCM by rewriting the WAV sample-rate
                     header after synthesis.  Lower stored rate → playback
                     sounds higher-pitched; higher stored rate → lower pitch.
  * Timbre hint    — Windows SAPI voices differ in formant character; we
                     attempt to match a preferred voice by keyword before
                     falling back to index-based selection.

Commander personalities
-----------------------
  VAEL   — commanding / authoritative  : low pitch, steady pace
  SEREN  — calm / analytical           : mid-low pitch, slow deliberate pace
  KAELEN — sharp / precise             : higher pitch, fast clipped pace
  LYRIN  — warm / nurturing            : mid-high pitch, gentle moderate pace
  ZETH   — intense / vigilant          : very low pitch, very slow heavy pace
  LYKE   — energetic / creative        : bright pitch, fast enthusiastic pace

Replace with real voice recordings for best XTTS cloning quality:
  - 5–30 seconds of clean speech per commander, no background noise
  - Save as: divisions/production/voice_references/{commander}.wav

Usage:
    python scripts/generate_voice_refs.py
    python scripts/generate_voice_refs.py --commander vael
    python scripts/generate_voice_refs.py --overwrite
"""

import argparse
import math
import struct
import wave
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
OUT_DIR  = BASE_DIR / "divisions" / "production" / "voice_references"

# ---------------------------------------------------------------------------
# Per-commander voice profiles
# ---------------------------------------------------------------------------
# Each entry:
#   text        — reference speech (~10-15 s of content; more = better clone)
#   rate        — pyttsx3 words-per-minute  (75–200; SAPI default is ~200)
#   volume      — pyttsx3 volume 0.0–1.0
#   pitch_shift — semitones applied after synthesis via PCM header rewrite
#                 negative = lower pitch, positive = higher pitch
#   voice_pref  — preferred SAPI voice keyword matched case-insensitively
#                 against voice name/id; first match wins, else index fallback
# ---------------------------------------------------------------------------

COMMANDER_PROFILES: dict[str, dict] = {
    "vael": {
        "text": (
            "I am Vael, commander of the Dawnhunt order. "
            "The ledger opens and the hunt begins. "
            "Every target is a problem to be solved, every opportunity a quarry to be marked. "
            "The pattern is clear. Follow it or fall behind. "
            "Strength is not noise. It is precision applied without hesitation."
        ),
        "rate":        135,   # steady, deliberate
        "volume":      0.97,
        "pitch_shift": -3,    # low commanding voice
        "voice_pref":  "david",
    },
    "seren": {
        "text": (
            "I am Seren, voice of the Auric Veil. "
            "The market speaks in patterns and I listen without reaction. "
            "Signal from noise, clarity from chaos. "
            "Every movement in the ledger is a verdict waiting to be read. "
            "Patience is not passivity. It is the discipline of the analyst."
        ),
        "rate":        120,   # slow, measured
        "volume":      0.88,
        "pitch_shift": -1,    # slightly low, calm
        "voice_pref":  "zira",
    },
    "kaelen": {
        "text": (
            "I am Kaelen, architect of the Iron Codex. "
            "The forge doesn't stop — it only refines. "
            "Every line of code is a blueprint, every system a construct to be perfected. "
            "Build under pressure and the structure holds. "
            "Precision is not optional. It is the only acceptable standard."
        ),
        "rate":        175,   # fast, clipped, sharp
        "volume":      0.92,
        "pitch_shift": +2,    # brighter, crisper
        "voice_pref":  "mark",
    },
    "lyrin": {
        "text": (
            "I am Lyrin, keeper of the Ember Covenant. "
            "The flame is tended with care and attention. "
            "Balance is not a destination — it is a discipline practiced every day. "
            "Rest when the ember dims, rise when it burns bright. "
            "Wellness is the foundation on which every other victory is built."
        ),
        "rate":        145,   # moderate, gentle
        "volume":      0.90,
        "pitch_shift": +1,    # slightly warm, elevated
        "voice_pref":  "hazel",
    },
    "zeth": {
        "text": (
            "I am Zeth, warden of the Nullward. "
            "The veil holds because someone watches the perimeter. "
            "Every threat surface mapped. Every credential audited. Every breach anticipated. "
            "Silence is not the absence of activity. It is the proof of vigilance. "
            "You do not see me working. That is how you know I am doing my job."
        ),
        "rate":        105,   # very slow, heavy, intense
        "volume":      0.99,
        "pitch_shift": -5,    # deep, ominous
        "voice_pref":  "david",
    },
    "lyke": {
        "text": (
            "I am Lyke, master of the Lykeon Forge. "
            "The Forge is lit and the pipeline runs. "
            "Every asset crafted, reviewed, cataloged, and delivered with precision. "
            "From prompt to pixel to realm — the Forge does not rest. "
            "Creation is not art alone. It is system, process, and relentless execution."
        ),
        "rate":        185,   # fast, enthusiastic, energetic
        "volume":      0.94,
        "pitch_shift": +3,    # bright, energetic
        "voice_pref":  "zira",
    },
}

# Distinct fundamental tones (Hz) used for fallback tonal placeholders
_FALLBACK_FREQ: dict[str, float] = {
    "vael":   130.0,   # bass-baritone C3
    "seren":  165.0,   # baritone E3
    "kaelen": 220.0,   # tenor A3
    "lyrin":  260.0,   # mezzo-soprano C4
    "zeth":   110.0,   # deep bass A2
    "lyke":   294.0,   # soprano D4
}


# ---------------------------------------------------------------------------
# Audio helpers — stdlib only (wave + struct + math)
# ---------------------------------------------------------------------------

def _pitch_shift_wav(path: Path, semitones: float) -> None:
    """
    Apply a pitch shift to a WAV file by rewriting the sample-rate header.

    The PCM frames are left untouched; only the framerate tag changes.
    A lower stored framerate makes playback read frames faster, raising the
    perceived pitch.  A higher stored framerate lowers perceived pitch.

    Formula: new_framerate = original_framerate / 2^(semitones/12)
    So negative semitones → ratio < 1 → new_rate > original → lower pitch.
    Positive semitones → ratio > 1 → new_rate < original → higher pitch.
    """
    if semitones == 0:
        return

    ratio = 2 ** (semitones / 12.0)

    with wave.open(str(path), "rb") as wf:
        params     = wf.getparams()
        raw_frames = wf.readframes(params.nframes)

    new_rate = max(8000, min(96000, int(round(params.framerate / ratio))))

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(params.nchannels)
        wf.setsampwidth(params.sampwidth)
        wf.setframerate(new_rate)
        wf.writeframes(raw_frames)


def _make_tone_wav(
    path: Path,
    duration_s: float = 8.0,
    sample_rate: int = 22050,
    freq_hz: float = 180.0,
    semitones: float = 0,
) -> None:
    """
    Write a tonal WAV placeholder when pyttsx3 is unavailable.

    Each commander gets a unique fundamental frequency so even the fallback
    tones are acoustically distinct for XTTS pitch detection.
    """
    adjusted_freq = freq_hz * (2 ** (semitones / 12.0))
    n_samples = int(sample_rate * duration_s)

    frames_list = []
    for i in range(n_samples):
        t        = i / sample_rate
        envelope = min(1.0, t * 4) * min(1.0, (duration_s - t) * 4)
        amp      = int(8000 * envelope * math.sin(2 * math.pi * adjusted_freq * t))
        frames_list.append(struct.pack("<h", max(-32767, min(32767, amp))))

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"".join(frames_list))


# ---------------------------------------------------------------------------
# Voice selection helper
# ---------------------------------------------------------------------------

def _pick_voice(engine, pref_keyword: str, fallback_index: int):
    """
    Return a voice id whose name/id contains *pref_keyword* (case-insensitive).
    Falls back to voices[fallback_index % len(voices)].id if no match found.
    """
    try:
        voices = engine.getProperty("voices")
        if not voices:
            return None
        keyword = pref_keyword.lower()
        for v in voices:
            name = (v.name or "").lower()
            vid  = (v.id  or "").lower()
            if keyword in name or keyword in vid:
                return v.id
        return voices[fallback_index % len(voices)].id
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Generation logic
# ---------------------------------------------------------------------------

def _generate_with_pyttsx3(commander: str, profile: dict, out_path: Path) -> bool:
    try:
        import pyttsx3  # type: ignore
    except ImportError:
        print(f"  [WARN] pyttsx3 not available — writing tone placeholder for {commander}")
        return False

    try:
        engine = pyttsx3.init()
        engine.setProperty("rate",   profile["rate"])
        engine.setProperty("volume", profile["volume"])

        commanders_list = list(COMMANDER_PROFILES.keys())
        fallback_idx    = commanders_list.index(commander)
        voice_id = _pick_voice(engine, profile["voice_pref"], fallback_idx)
        if voice_id:
            engine.setProperty("voice", voice_id)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        engine.save_to_file(profile["text"], str(out_path))
        engine.runAndWait()

        if out_path.exists() and out_path.stat().st_size > 1000:
            print(
                f"  [OK]   {commander}.wav — "
                f"{out_path.stat().st_size // 1024} KB  "
                f"(rate={profile['rate']}, pitch={profile['pitch_shift']:+d} st)"
            )
            return True
        else:
            print(f"  [WARN] pyttsx3 produced empty/tiny file for {commander}")
            return False

    except Exception as exc:
        print(f"  [WARN] pyttsx3 failed for {commander}: {exc}")
        return False


def generate_commander(commander: str, overwrite: bool = False) -> None:
    profile  = COMMANDER_PROFILES[commander]
    out_path = OUT_DIR / f"{commander}.wav"

    if out_path.exists() and not overwrite:
        print(f"  [SKIP] {commander}.wav already exists (use --overwrite to replace)")
        return

    print(f"\n  Generating {commander} ...")
    print(
        f"    style : rate={profile['rate']} wpm, vol={profile['volume']}, "
        f"pitch={profile['pitch_shift']:+d} semitones, voice_pref='{profile['voice_pref']}'"
    )

    success = _generate_with_pyttsx3(commander, profile, out_path)

    if success:
        semitones = profile.get("pitch_shift", 0)
        if semitones != 0:
            _pitch_shift_wav(out_path, semitones)
            print(f"  [PITCH] {commander}.wav — adjusted {semitones:+d} semitones via header rewrite")
    else:
        print(f"  [FALLBACK] Writing tonal placeholder for {commander}")
        freq = _FALLBACK_FREQ.get(commander, 200.0)
        _make_tone_wav(
            out_path,
            duration_s=8.0,
            freq_hz=freq,
            semitones=profile.get("pitch_shift", 0),
        )
        adjusted = freq * (2 ** (profile.get("pitch_shift", 0) / 12))
        print(f"  [OK]   {commander}.wav — tone placeholder at {adjusted:.0f} Hz")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate voice reference WAVs for all commanders with distinct acoustic profiles."
    )
    parser.add_argument(
        "--commander",
        choices=list(COMMANDER_PROFILES.keys()),
        help="Generate only one commander (default: all)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing WAV files",
    )
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\nOutput directory: {OUT_DIR}")
    print("=" * 60)
    print("Commander voice profiles:")
    for name, p in COMMANDER_PROFILES.items():
        print(
            f"  {name:<8} rate={p['rate']:>3} wpm  "
            f"pitch={p['pitch_shift']:+d} st  "
            f"vol={p['volume']:.2f}  pref='{p['voice_pref']}'"
        )
    print("=" * 60)

    commanders = [args.commander] if args.commander else list(COMMANDER_PROFILES.keys())
    for cmdr in commanders:
        generate_commander(cmdr, overwrite=args.overwrite)

    print("\nDone.")
    print("\nTo replace with real voice recordings:")
    print("  Record 5-30s of clean speech, save as {commander}.wav")
    print(f"  Drop into: {OUT_DIR}")
    print("  Re-run voice-generate to pick up the new reference automatically.")


if __name__ == "__main__":
    main()
