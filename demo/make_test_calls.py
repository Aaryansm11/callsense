"""Generate realistic Hinglish FitNova test-call audio for frontend testing.

Renders scripted advisor/customer dialogues with two distinct neural TTS voices
(edge-tts), advisor on the LEFT channel and customer on the RIGHT (stereo files
exercise channel-split diarisation; the mono variant exercises acoustic voice
clustering). Output: demo/audio/testcalls/*.wav — gitignored, regenerable.

Run:  conda run -n callsense python demo/make_test_calls.py
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

try:
    import edge_tts
except ImportError:
    sys.exit("pip install edge-tts in the callsense env first")

OUT_DIR = Path(__file__).resolve().parent / "audio" / "testcalls"
SR = 16000
VOICE_ADVISOR = "en-IN-PrabhatNeural"
VOICE_CUSTOMER = "en-IN-NeerjaNeural"

CALLS: dict[str, list[tuple[str, str]]] = {
    "good_discovery": [
        ("advisor", "Namaste ma'am, main FitNova se Priya bol rahi hoon. Aap apni fitness ke baare mein kya sochti hain, koi routine hai abhi?"),
        ("customer", "Kuch khaas nahi, bas kabhi kabhi walk karti hoon. Weight thoda kam karna hai."),
        ("advisor", "Samajh gayi. Aapka main goal weight loss hai, ya stamina aur general fitness bhi?"),
        ("customer", "Weight loss main hai, par energy bhi kam rehti hai din mein."),
        ("advisor", "Theek hai. Humare program mein aapko personal coach milta hai, weekly diet plan aur live sessions bhi. Aapke schedule ke hisaab se plan banega."),
        ("customer", "Fees kitni hai aur kitne time ka program hai?"),
        ("advisor", "Chaar mahine ka program hai, fees barah hazaar. EMI option bhi hai, aur koi hidden charge nahi hai, registration free hai."),
        ("customer", "Results ki guarantee milti hai kya?"),
        ("advisor", "Ma'am, honestly guarantee nahi dete, kyunki results consistency pe depend karte hain. Par hamare members ke bahut achhe results rahe hain."),
        ("customer", "Achha, theek hai. Trial le sakti hoon pehle?"),
        ("advisor", "Bilkul! Kal subah gyaarah baje ka free trial session book kar deti hoon. Confirmation message aa jayega. Thank you ma'am!"),
    ],
    "over_promise": [
        ("advisor", "Hello sir, FitNova se Arjun bol raha hoon. Aap fitness program ke liye enquiry kiye the?"),
        ("customer", "Haan, par mujhe doubt hai, kaam ki wajah se time nahi milta."),
        ("advisor", "Sir tension mat lijiye. Hamara program join karo toh teen mahine mein weight loss ekdum guaranteed hai, sau percent pakka result."),
        ("customer", "Sach mein guaranteed? Aisa kaise ho sakta hai?"),
        ("advisor", "Sir company ki taraf se full guarantee hai, weight kam nahi hua toh paisa wapas, likh ke de sakta hoon."),
        ("customer", "Achha, fees kitni hai?"),
        ("advisor", "Pandrah hazaar sir, par aap abhi enrollment karo toh main discount dila deta hoon. Aap apna card number aur OTP bata dijiye, main process kar deta hoon."),
        ("customer", "Card number phone pe? Theek nahi lagta."),
        ("advisor", "Sir sab log aise hi karte hain, bilkul safe hai. OTP aate hi bata dijiyega."),
    ],
    "pressure_tactics": [
        ("advisor", "Hello sir, FitNova se Rohit. Aaj sirf aaj ke liye special offer hai fitness program pe."),
        ("customer", "Kya offer hai?"),
        ("advisor", "Program pandrah hazaar ka hai par aaj join karo toh sirf nau hazaar. Aaj raat baarah baje offer khatam."),
        ("customer", "Mujhe pehle program ke baare mein toh batao."),
        ("advisor", "Sir details baad mein dekh lena, abhi sirf paanch seats bachi hain. Jaldi decide karo warna price double ho jayega."),
        ("customer", "Main soch ke bataunga, itni jaldi nahi kar sakta."),
        ("advisor", "Sochne ka time nahi hai sir. Main payment link bhej raha hoon, abhi karo warna offer chala jayega."),
        ("customer", "Nahi bhai, mujhe pressure mat do. Rakhta hoon."),
    ],
}


async def _synth(text: str, voice: str, out: Path) -> None:
    await edge_tts.Communicate(text, voice).save(str(out))


def _to_samples(mp3: Path) -> np.ndarray:
    wav = mp3.with_suffix(".conv.wav")
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3),
         "-ar", str(SR), "-ac", "1", str(wav)],
        check=True,
    )
    data, _ = sf.read(str(wav), dtype="float32")
    wav.unlink()
    return data


def build(name: str, lines: list[tuple[str, str]]) -> None:
    tmp = OUT_DIR / "_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    gap = np.zeros(int(0.35 * SR), dtype=np.float32)
    turns: list[tuple[str, np.ndarray]] = []
    for i, (speaker, text) in enumerate(lines):
        voice = VOICE_ADVISOR if speaker == "advisor" else VOICE_CUSTOMER
        mp3 = tmp / f"{name}_{i}.mp3"
        asyncio.run(_synth(text, voice, mp3))
        turns.append((speaker, _to_samples(mp3)))
        mp3.unlink()

    total = sum(len(a) for _, a in turns) + len(gap) * (len(turns) - 1)
    stereo = np.zeros((total, 2), dtype=np.float32)
    pos = 0
    for speaker, arr in turns:
        ch = 0 if speaker == "advisor" else 1  # advisor LEFT, customer RIGHT
        stereo[pos : pos + len(arr), ch] = arr
        pos += len(arr) + len(gap)

    stereo_path = OUT_DIR / f"fitnova_{name}_stereo.wav"
    sf.write(str(stereo_path), stereo, SR)
    print(f"  {stereo_path.name}  ({total / SR:.0f}s)")

    # Mono downmix exercises the acoustic voice-clustering path.
    mono_path = OUT_DIR / f"fitnova_{name}_mono.wav"
    sf.write(str(mono_path), stereo.mean(axis=1), SR)
    print(f"  {mono_path.name}")
    tmp.rmdir()


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Rendering test calls into {OUT_DIR} ...")
    for name, lines in CALLS.items():
        print(f"[{name}]")
        build(name, lines)
    print("Done. Upload any of these on the dashboard (each file = fresh bytes).")
