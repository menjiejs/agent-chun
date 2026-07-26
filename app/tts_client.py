import os
import time

import requests

from app.logging_config import logger


TTS_URL = "https://open.bigmodel.cn/api/paas/v4/audio/speech"
TTS_MODEL = "glm-tts"
TTS_VOICE = "tongtong"
TTS_TIMEOUT = (5, 120)


class TTSConfigurationError(RuntimeError):
    pass


class TTSUnavailableError(RuntimeError):
    pass


class TTSUpstreamError(RuntimeError):
    pass


def is_wav(data):
    return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"


def synthesize_speech(text: str, request_id: str) -> bytes:
    api_key = os.getenv("ZHIPU_API_KEY", "").strip()
    if not api_key:
        raise TTSConfigurationError("ZHIPU_API_KEY is not configured")

    started_at = time.perf_counter()
    try:
        response = requests.post(
            TTS_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "X-Request-ID": request_id,
            },
            json={
                "model": TTS_MODEL,
                "input": text,
                "voice": TTS_VOICE,
                "response_format": "wav",
            },
            timeout=TTS_TIMEOUT,
        )
    except requests.Timeout as exc:
        logger.warning(
            "tts_upstream_error request_id=%s text_length=%s error_type=Timeout",
            request_id,
            len(text),
        )
        raise TTSUnavailableError("TTS request timed out") from exc
    except requests.RequestException as exc:
        logger.warning(
            "tts_upstream_error request_id=%s text_length=%s error_type=%s",
            request_id,
            len(text),
            type(exc).__name__,
        )
        raise TTSUnavailableError("TTS request failed") from exc

    logger.info(
        "tts_upstream_complete request_id=%s status_code=%s text_length=%s "
        "audio_bytes=%s duration_ms=%.2f",
        request_id,
        response.status_code,
        len(text),
        len(response.content),
        (time.perf_counter() - started_at) * 1000,
    )
    if response.status_code == 429:
        raise TTSUnavailableError("TTS is temporarily unavailable")
    if response.status_code != 200:
        raise TTSUpstreamError("TTS upstream returned an error")
    if not is_wav(response.content):
        raise TTSUpstreamError("TTS upstream returned non-WAV content")
    return response.content
