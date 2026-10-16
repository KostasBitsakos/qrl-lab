"""Local speech-to-text for the dashboard chat (faster-whisper, CPU, no network after the first model download).

transcribe(wav_bytes, model=None) is a pure function of the audio and a model object, so tests pass a fake.
get_model() loads the WhisperModel lazily (once per process); size from env QRL_WHISPER_MODEL (default `small`).
"""
import io
import os

DEFAULT_MODEL = "small"
_MODEL = None


def model_name():
    return os.environ.get("QRL_WHISPER_MODEL") or DEFAULT_MODEL


def get_model():
    global _MODEL
    if _MODEL is None:
        from faster_whisper import WhisperModel
        _MODEL = WhisperModel(model_name(), device="cpu", compute_type="int8")
    return _MODEL


def transcribe(wav_bytes, model=None, language="el"):
    """Return (text, detected_language). Tries Greek first; if that yields nothing, retries with auto-detection."""
    if not wav_bytes:
        return "", None
    model = model or get_model()
    for lang in (language, None):
        segments, info = model.transcribe(io.BytesIO(wav_bytes), language=lang, vad_filter=True, beam_size=1)
        text = " ".join(s.text.strip() for s in segments).strip()
        if text:
            return text, getattr(info, "language", lang)
    return "", None
