"""Server-side voice providers.

The realtime loop runs in the browser (`apps/web/lib/voice`): speech-to-text produces final
transcripts that are sent over the interview WebSocket, and interviewer utterances are spoken by
the client. The server-side `VoiceProvider` decides *how* the client speaks:

* ``browser``    – client uses the Web Speech API for STT and TTS (free, no keys, Chrome/Edge best).
* ``elevenlabs`` – server synthesises interviewer speech (MP3) with ElevenLabs; STT stays in browser.
* ``edge``       – server synthesises speech with Microsoft Edge neural voices (free, no key, e.g.
                   ``en-IN-NeerjaNeural``). Uses the public Edge read-aloud endpoint: fine for development
                   and demos; use a contracted TTS (ElevenLabs, Azure Speech) for production traffic.
* ``mock``       – no audio; text only (used in tests and CI).

Business logic depends only on `VoiceProvider`, never on a vendor.
"""

from __future__ import annotations

import abc
import base64
from dataclasses import dataclass

import httpx


@dataclass
class SpeechAudio:
    mime_type: str
    audio_b64: str
    characters: int


@dataclass
class VoiceSessionConfig:
    provider: str
    stt: str  # "browser" | "none"
    tts: str  # "browser" | "server" | "none"
    language: str = "en-US"
    voice_hint: str | None = None


class VoiceProviderError(Exception):
    def __init__(self, message: str, *, cooldown_seconds: float = 60.0) -> None:
        super().__init__(message)
        # transient failures (network blip) pause server TTS briefly; quota/auth problems for longer
        self.cooldown_seconds = cooldown_seconds


class VoiceProvider(abc.ABC):
    name: str

    @abc.abstractmethod
    def session_config(self) -> VoiceSessionConfig: ...

    async def synthesize(self, text: str) -> SpeechAudio | None:
        """Return audio for `text`, or None when the client speaks locally."""
        return None


class BrowserVoiceProvider(VoiceProvider):
    name = "browser"

    def session_config(self) -> VoiceSessionConfig:
        return VoiceSessionConfig(provider=self.name, stt="browser", tts="browser")


class MockVoiceProvider(VoiceProvider):
    name = "mock"

    def session_config(self) -> VoiceSessionConfig:
        return VoiceSessionConfig(provider=self.name, stt="none", tts="none")


class ElevenLabsVoiceProvider(VoiceProvider):
    """TTS via ElevenLabs (same API used by the studio's voice.mjs). Key never leaves the server."""

    name = "elevenlabs"

    def __init__(self, api_key: str, voice_id: str, model_id: str = "eleven_multilingual_v2", timeout: float = 20.0) -> None:
        if not api_key:
            raise VoiceProviderError("ELEVENLABS api key missing")
        self.api_key = api_key
        self.voice_id = voice_id
        self.model_id = model_id
        self.timeout = timeout

    def session_config(self) -> VoiceSessionConfig:
        return VoiceSessionConfig(provider=self.name, stt="browser", tts="server")

    async def synthesize(self, text: str) -> SpeechAudio | None:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}?output_format=mp3_44100_64"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    url,
                    headers={"xi-api-key": self.api_key, "Content-Type": "application/json"},
                    json={"text": text, "model_id": self.model_id, "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}},
                )
        except httpx.HTTPError as exc:
            raise VoiceProviderError(f"ElevenLabs request failed: {exc.__class__.__name__}") from exc
        if resp.status_code != 200:
            detail = ""
            try:
                detail = str(resp.json().get("detail", {}).get("code", ""))
            except Exception:
                detail = ""
            long_pause = resp.status_code in (401, 402, 403) or "quota" in detail
            raise VoiceProviderError(f"ElevenLabs error {resp.status_code} {detail}".strip(), cooldown_seconds=600 if long_pause else 60)
        return SpeechAudio(mime_type="audio/mpeg", audio_b64=base64.b64encode(resp.content).decode(), characters=len(text))


class EdgeVoiceProvider(VoiceProvider):
    """Free neural TTS through the `edge-tts` package. No key; the voice locale also sets browser STT language."""

    name = "edge"

    def __init__(self, voice: str = "en-IN-NeerjaNeural", rate: str = "+0%", timeout: float = 15.0) -> None:
        self.voice = voice
        self.rate = rate
        self.timeout = timeout

    def session_config(self) -> VoiceSessionConfig:
        locale = "-".join(self.voice.split("-")[:2]) if self.voice.count("-") >= 2 else "en-US"
        return VoiceSessionConfig(provider=self.name, stt="browser", tts="server", language=locale, voice_hint=self.voice)

    async def synthesize(self, text: str) -> SpeechAudio | None:
        import asyncio

        try:
            import edge_tts
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise VoiceProviderError("edge-tts is not installed (pip install edge-tts)") from exc

        async def _collect() -> bytes:
            buf = bytearray()
            async for chunk in edge_tts.Communicate(text, self.voice, rate=self.rate).stream():
                if chunk["type"] == "audio":
                    buf += chunk["data"]
            return bytes(buf)

        try:
            audio = await asyncio.wait_for(_collect(), self.timeout)
        except TimeoutError as exc:
            raise VoiceProviderError("Edge TTS timed out") from exc
        except Exception as exc:
            raise VoiceProviderError(f"Edge TTS failed: {exc.__class__.__name__}") from exc
        if not audio:
            raise VoiceProviderError("Edge TTS returned no audio (check VOICE_ID)", cooldown_seconds=600)
        return SpeechAudio(mime_type="audio/mpeg", audio_b64=base64.b64encode(audio).decode(), characters=len(text))


def build_voice_provider(name: str, api_key: str | None = None, voice_id: str | None = None) -> VoiceProvider:
    if name == "browser":
        return BrowserVoiceProvider()
    if name == "mock":
        return MockVoiceProvider()
    if name == "elevenlabs":
        return ElevenLabsVoiceProvider(api_key or "", voice_id or "21m00Tcm4TlvDq8ikWAM")
    if name == "edge":
        # ElevenLabs voice ids have no locale; only accept Edge-style names such as en-IN-NeerjaNeural
        return EdgeVoiceProvider(voice_id if voice_id and voice_id.endswith("Neural") else "en-IN-NeerjaNeural")
    raise ValueError(f"Unknown voice provider '{name}'")


__all__ = [
    "BrowserVoiceProvider",
    "EdgeVoiceProvider",
    "ElevenLabsVoiceProvider",
    "MockVoiceProvider",
    "SpeechAudio",
    "VoiceProvider",
    "VoiceProviderError",
    "VoiceSessionConfig",
    "build_voice_provider",
]
