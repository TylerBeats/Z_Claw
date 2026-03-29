"""
generate_voice_refs.py — Bootstrap voice reference WAVs for all commanders.

Uses pyttsx3 (already installed, no GPU required) to synthesize a short
reference line for each commander. These are placeholder references — good
enough for Coqui XTTS v2 voice cloning to function immediately.

Replace with real voice recordings later for better cloning quality:
  - 5–30 seconds of clean speech per commander
  - No background noise, no music
  - Save as: divisions/production/voice_references/{commander}.wav

Usage:
    python scripts/generate_voice_refs.py
    python scripts/generate_voice_refs.py --commander vael
"""

import argparse
import sys
import wave
import struct
import math
from pathlib import Path

BASE_DIR  = Path(__file__).parent.parent
OUT_DIR   = BASE_DIR / "divisions" / "production" / "voice_references"

# Reference lines — each commander introduces themselves
# ~10 seconds of speech at normal pace
REFERENCE_LINES = {
    "vael": (
        "I am Vael, commander of the Dawnhunt order. "
        "The ledger opens and the hunt begins. "
        "Every target is a problem to be solved, every opportunity a quarry to be marked. "
        "The pattern is clear — follow it or fall behind."
    ),
    "seren": (
        "I am Seren, voice of the Auric Veil. "
        "The market speaks in patterns and I listen. "
        "Signal from noise, clarity from chaos. "
        "Every movement in the ledger is a verdict waiting to be read."
    ),
    "kaelen": (
        "I am Kaelen, architect of the Iron Codex. "
        "The forge doesn't stop — it only refines. "
        "Every line of code is a blueprint, every system a construct to be perfected. "
        "Build under pressure and the structure holds."
    ),
    "lyrin": (
        "I am Lyrin, keeper of the Ember Covenant. "
        "The flame is tended with care and attention. "
        "Balance is not a destination — it is a discipline practiced every day. "
        "Rest when the ember dims, rise when it burns bright."
    ),
    "zeth": (
        "I am Zeth, warden of the Nullward. "
        "The veil holds because someone watches the perimeter. "
        "Every threat surface mapped, every credential audited, every breach anticipated. "
        "Silence is not the absence of activity — it is the proof of vigilance."
    ),
    "lyke": (
        "I am Lyke, master of the Lykeon Forge. "
        "The Forge is lit and the pipeline runs. "
        "Every asset crafted, reviewed, cataloged, and delivered with precision. "
        "From prompt to pixel to realm — the Forge does not rest."
    ),
}


def _make_silence_wav(path: Path, duration_s: float = 1.0, sample_rate: int = 22050) -> None:
    """Write a short silent WAV as an absolute fallback if pyttsx3 fails."""
    n_samples = int(sample_rate * duration_s)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        # Low-amplitude tone so XTTS doesn't see pure silence as invalid
        frames = b"".join(
            struct.pack("<h", int(300 * math.sin(2 * math.pi * 220 * i / sample_rate)))
            for i in range(n_samples)
        )
        wf.writeframes(frames)


def generate_with_pyttsx3(commander: str, text: str, out_path: Path) -> bool:
    try:
        import pyttsx3  # type: ignore
    except ImportError:
        print(f"  [WARN] pyttsx3 not available — writing tone placeholder for {commander}")
        return False

    try:
        engine = pyttsx3.init()
        # Slightly slower rate for cleaner reference audio
        engine.setProperty("rate", 155)
        engine.setProperty("volume", 0.95)

        # Try to pick a voice with some variation per commander
        voices = engine.getProperty("voices")
        if voices:
            # Alternate between available voices for variety
            commanders = list(REFERENCE_LINES.keys())
            idx = commanders.index(commander) % len(voices)
            engine.setProperty("voice", voices[idx].id)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        engine.save_to_file(text, str(out_path))
        engine.runAndWait()

        if out_path.exists() and out_path.stat().st_size > 1000:
            print(f"  [OK]   {commander}.wav — {out_path.stat().st_size // 1024} KB")
            return True
        else:
            print(f"  [WARN] pyttsx3 produced empty file for {commander}")
            return False

    except Exception as e:
        print(f"  [WARN] pyttsx3 failed for {commander}: {e}")
        return False


def generate_commander(commander: str, overwrite: bool = False) -> None:
    out_path = OUT_DIR / f"{commander}.wav"

    if out_path.exists() and not overwrite:
        print(f"  [SKIP] {commander}.wav already exists (use --overwrite to replace)")
        return

    text = REFERENCE_LINES[commander]
    print(f"  Generating {commander}...")

    success = generate_with_pyttsx3(commander, text, out_path)
    if not success:
        print(f"  [FALLBACK] Writing tone placeholder for {commander}")
        _make_silence_wav(out_path, duration_s=8.0)
        print(f"  [OK]   {commander}.wav — tone placeholder written")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate voice reference WAVs for all commanders")
    parser.add_argument("--commander", choices=list(REFERENCE_LINES.keys()),
                        help="Generate only one commander (default: all)")
    parser.add_argument("--overwrite", action="store_true",
                        help="Overwrite existing WAV files")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\nOutput directory: {OUT_DIR}")
    print("=" * 50)

    commanders = [args.commander] if args.commander else list(REFERENCE_LINES.keys())
    for cmdr in commanders:
        generate_commander(cmdr, overwrite=args.overwrite)

    print("\nDone.")
    print("\nTo replace with real voice recordings:")
    print("  Record 5-30s of clean speech, save as {commander}.wav")
    print(f"  Drop into: {OUT_DIR}")
    print("  Re-run voice-generate to pick up the new reference automatically.")


if __name__ == "__main__":
    main()
