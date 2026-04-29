"""Speech recognition, TTS output, and LLM-backed conversation."""
import json
import queue
import threading
from pathlib import Path
from typing import Dict, List, Optional

import pyttsx3
import speech_recognition as sr

from core.logger import logger
from utils.config import config

try:
    from ollama import Client as OllamaClient
    _OLLAMA = True
except ImportError:
    _OLLAMA = False

try:
    import winsound
    _WINSOUND = True
except ImportError:
    _WINSOUND = False  # Non-Windows platform

try:
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    _PYCAW = True
except ImportError:
    _PYCAW = False


class VoiceProcessor:
    """Handles microphone input, text-to-speech output, and LLM responses.

    * ``listen()``        -  blocks until speech is heard (or timeout).
    * ``speak()``         -  fires-and-forgets; returns immediately.
    * ``get_response()``  -  streams LLM reply, speaking sentences as they arrive.
    * ``parse_command()`` -  maps plain-language phrases to movement commands.
    * ``calibrate()``     -  calibrates microphone for ambient noise.
    """

    _COMMAND_MAP: Dict[str, List[str]] = {
        "FORWARD":  [
            "forward", "go forward", "move forward", "drive forward",
            "go ahead", "move ahead", "straight", "go straight",
            "advance", "lets go", "let's go", "move",
        ],
        "BACKWARD": [
            "back", "backward", "backwards", "go back", "move back",
            "reverse", "back up", "go backward",
        ],
        "LEFT":     [
            "left", "turn left", "go left", "rotate left",
            "spin left", "face left",
        ],
        "RIGHT":    [
            "right", "turn right", "go right", "rotate right",
            "spin right", "face right",
        ],
        "STOP":     [
            "stop", "halt", "freeze", "wait", "hold on",
            "stay", "cancel", "enough", "cease",
        ],
    }

    def __init__(self) -> None:
        self.log = logger.get_logger("VoiceProcessor")

        self._recognizer = self._init_recognizer()

        # TTS: pyttsx3 on Windows (SAPI5) uses a COM Single-Threaded
        # Apartment - the engine must be created AND used in the same thread.
        self._engine: Optional[pyttsx3.Engine] = None
        self._tts_queue: queue.Queue = queue.Queue()
        self._tts_ready = threading.Event()
        threading.Thread(
            target=self._tts_worker, daemon=True, name="TTSWorker"
        ).start()
        if not self._tts_ready.wait(timeout=5.0):
            self.log.warning("TTS engine did not initialise within 5 s")

        self.llm_model = config.get("llm.model")
        self._llm      = self._init_llm()

        self.system_prompt = self._build_system_prompt()

        self.chat_history: List[Dict] = []
        self._history_lock = threading.Lock()   # guards chat_history across threads
        self._history_file = Path("data/chat_history.json")
        self._load_history()

    # ------------------------------------------------------------------
    # Initialisation helpers
    # ------------------------------------------------------------------

    def _init_recognizer(self) -> Optional[sr.Recognizer]:
        try:
            rec = sr.Recognizer()
            rec.energy_threshold      = config.get("voice.recognizer_energy_threshold", 300)
            rec.dynamic_energy_threshold = True
            # How long of silence counts as end-of-phrase.
            # Default 2.3 s is too slow; 0.8 s feels natural.
            rec.pause_threshold = config.get("voice.recognizer_pause_threshold", 0.8)
            return rec
        except Exception as exc:
            self.log.error("Recognizer init failed: %s", exc)
            return None

    def _tts_worker(self) -> None:
        """Owns pyttsx3 exclusively - init and all calls happen in this thread."""
        try:
            engine = pyttsx3.init()
            voices = engine.getProperty("voices")
            if voices:
                engine.setProperty("voice", voices[0].id)
            engine.setProperty("rate",   config.get("voice.tts_rate", 230))
            engine.setProperty("volume", config.get("voice.tts_volume", 1.0))
            self._engine = engine
        except Exception as exc:
            self.log.error("TTS init failed: %s", exc)
        finally:
            self._tts_ready.set()

        if self._engine is None:
            return

        while True:
            text = self._tts_queue.get()
            if text is None:
                break
            try:
                self._engine.say(text)
                self._engine.runAndWait()
            except RuntimeError as exc:
                if "run loop already started" in str(exc):
                    try:
                        self._engine.endLoop()
                        self._engine.say(text)
                        self._engine.runAndWait()
                    except Exception as retry_exc:
                        self.log.error("TTS retry failed: %s", retry_exc)
                else:
                    self.log.error("TTS error: %s", exc)
            except Exception as exc:
                self.log.error("TTS error: %s", exc)

    def stop(self) -> None:
        """Shut down the TTS worker."""
        self._tts_queue.put(None)

    def _init_llm(self) -> Optional["OllamaClient"]:
        if not _OLLAMA:
            self.log.warning("Ollama not installed  -  run: pip install ollama")
            return None
        try:
            client = OllamaClient()
            client.list()   # actual probe - constructor alone makes no connection
            self.log.info("[OK] Ollama running (model: %s)", self.llm_model)
            return client
        except Exception as exc:
            self.log.warning(
                "Ollama not reachable (%s)  -  LLM disabled. "
                "Start Ollama and restart to enable.", exc
            )
            return None

    def _build_system_prompt(self) -> str:
        name = config.get("droid.name", "friend")
        return (
            "You are D O, a shy, loyal, awkward droid. "
            "Speak in short, broken sentences. "
            "Be casual and soft-spoken. "
            "Use only plain English letters and basic punctuation. "
            "No emoji. No special symbols. No markdown. "
            "Never sound like an AI assistant. "
            f"Call them {name}."
        )

    # ------------------------------------------------------------------
    # Microphone calibration
    # ------------------------------------------------------------------

    def _get_volume_endpoint(self):
        """Return a pycaw IAudioEndpointVolume interface, or None.

        Handles both old pycaw (GetSpeakers returns raw IMMDevice COM object)
        and new pycaw (GetSpeakers returns an AudioDevice wrapper whose
        underlying COM device is in ._dev).
        """
        if not _PYCAW:
            return None
        try:
            speakers = AudioUtilities.GetSpeakers()
            # Newer pycaw wraps IMMDevice in AudioDevice; unwrap if needed.
            device = getattr(speakers, "_dev", speakers)
            interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            return cast(interface, POINTER(IAudioEndpointVolume))
        except Exception as exc:
            self.log.warning("pycaw endpoint unavailable: %s", exc)
            return None

    def set_system_volume(self, level: int) -> None:
        """Set the Windows master volume (0-100).

        Requires pycaw: pip install pycaw
        Falls back to adjusting pyttsx3 output volume if pycaw is absent.
        """
        level = max(0, min(100, level))

        endpoint = self._get_volume_endpoint()
        if endpoint is not None:
            try:
                endpoint.SetMasterVolumeLevelScalar(level / 100.0, None)
                self.log.info("System volume set to %d%%", level)
                return
            except Exception as exc:
                self.log.warning("pycaw volume set failed: %s", exc)

        # Fallback: adjust pyttsx3 output level only
        if self._engine:
            try:
                self._engine.setProperty("volume", level / 100.0)
                self.log.info("TTS volume set to %d%% (system volume unchanged)", level)
            except Exception as exc:
                self.log.warning("TTS volume set failed: %s", exc)
        else:
            self.log.warning("Volume control not available (no pycaw, no TTS engine)")

    def get_system_volume(self) -> Optional[int]:
        """Return the current Windows master volume (0-100), or None."""
        endpoint = self._get_volume_endpoint()
        if endpoint is not None:
            try:
                return round(endpoint.GetMasterVolumeLevelScalar() * 100)
            except Exception as exc:
                self.log.warning("pycaw volume get failed: %s", exc)
        return None

    def beep(self, pattern: str = "startup") -> None:
        """Play a beep pattern via the Windows audio device.

        Uses winsound.Beep() which bypasses pyttsx3 entirely - useful for
        confirming the audio output device is working before testing TTS.

        Patterns:
            'startup'  - ascending R2-D2 style chirp
            'ok'       - short double beep (command acknowledged)
            'error'    - low descending tone
        """
        if not _WINSOUND:
            self.log.debug("winsound not available (non-Windows)")
            return

        patterns = {
            "startup": [(1047, 120), (1319, 120), (1568, 120), (2093, 250)],
            "ok":      [(1568, 80),  (2093, 120)],
            "error":   [(500,  200), (350,  300)],
        }

        try:
            for freq, duration in patterns.get(pattern, patterns["ok"]):
                winsound.Beep(freq, duration)
        except Exception as exc:
            self.log.warning("Beep failed: %s", exc)

    def log_audio_devices(self) -> None:
        """Log all detected audio input and output devices."""
        self.log.info("--- Audio devices ---")

        # Output devices via pyaudio
        try:
            import pyaudio
            pa = pyaudio.PyAudio()
            outputs = []
            inputs  = []
            default_out = pa.get_default_output_device_info()
            default_in  = pa.get_default_input_device_info()

            for i in range(pa.get_device_count()):
                info = pa.get_device_info_by_index(i)
                if info["maxOutputChannels"] > 0:
                    marker = " <- DEFAULT" if i == default_out["index"] else ""
                    outputs.append(f"  [{i}] {info['name']}{marker}")
                if info["maxInputChannels"] > 0:
                    marker = " <- DEFAULT" if i == default_in["index"] else ""
                    inputs.append(f"  [{i}] {info['name']}{marker}")
            pa.terminate()

            self.log.info("Output devices (%d):", len(outputs))
            for line in outputs:
                self.log.info(line)
            self.log.info("Input devices (%d):", len(inputs))
            for line in inputs:
                self.log.info(line)

        except Exception as exc:
            self.log.warning("Could not enumerate audio devices: %s", exc)

        # Confirm which mic index speech_recognition will use
        mic_index = config.get("voice.microphone_index")
        if mic_index is None:
            self.log.info("Microphone: using system default (set voice.microphone_index to override)")
        else:
            self.log.info("Microphone: index %s (from config)", mic_index)

        self.log.info("--- End audio devices ---")

    def calibrate(self, duration: float = 1.0) -> None:
        """Calibrate energy threshold for the current ambient noise level.

        Call once at startup before the listen loop begins.  Reads the
        microphone for *duration* seconds and adjusts the recognizer's
        energy_threshold accordingly so soft speech isn't missed and
        background noise doesn't trigger false positives.
        """
        if not self._recognizer:
            return
        try:
            mic_index = config.get("voice.microphone_index")
            with sr.Microphone(device_index=mic_index) as source:
                self.log.info("Calibrating microphone for ambient noise (%.1fs)...", duration)
                self._recognizer.adjust_for_ambient_noise(source, duration=duration)
                self.log.info(
                    "[OK] Microphone calibrated (energy threshold: %.0f)",
                    self._recognizer.energy_threshold,
                )
        except Exception as exc:
            self.log.warning("Microphone calibration failed: %s", exc)

    # ------------------------------------------------------------------
    # Speech output
    # ------------------------------------------------------------------

    def speak(self, text: str) -> None:
        """Queue *text* for speaking; returns immediately."""
        if not text or not text.strip() or not self._engine:
            return
        # Strip non-ASCII characters (emoji, symbols) before sending to
        # pyttsx3/SAPI5.  On Windows, SAPI5 silently drops the entire
        # utterance if it encounters characters it cannot pronounce.
        clean = text.encode("ascii", errors="ignore").decode("ascii").strip()
        if clean:
            self._tts_queue.put(clean)

    # ------------------------------------------------------------------
    # Speech input
    # ------------------------------------------------------------------

    def listen(self, timeout: float = 5.0) -> Optional[str]:
        """Block until speech is heard; return transcribed text or None."""
        if not self._recognizer:
            self.log.warning("Recognizer not available")
            return None
        try:
            mic_index = config.get("voice.microphone_index")  # None = system default
            with sr.Microphone(device_index=mic_index) as source:
                self.log.debug("Listening (timeout=%.1fs)...", timeout)
                audio = self._recognizer.listen(
                    source, timeout=timeout, phrase_time_limit=10
                )
            return self._recognizer.recognize_google(audio)
        except sr.WaitTimeoutError:
            self.log.debug("No speech detected within %.1fs", timeout)
        except sr.UnknownValueError:
            self.log.debug("Could not understand audio")
        except sr.RequestError as exc:
            self.log.error("Speech service error: %s", exc)
        except Exception as exc:
            self.log.error("Microphone error: %s", exc)
        return None

    # ------------------------------------------------------------------
    # LLM
    # ------------------------------------------------------------------

    def get_response(self, user_input: str) -> str:
        """Stream an LLM reply, speaking each sentence as it arrives.

        Using stream=True means the droid starts speaking after the first
        sentence (~2-3 s) rather than waiting for the full response (~28 s).
        The full reply text is returned and saved to chat history.
        """
        self.log.info("LLM processing: '%s'", user_input[:50])

        if not self._llm:
            self.log.info("LLM: not available - using fallback")
            self.speak("I cannot think right now.")
            return "I cannot think right now."

        try:
            messages = [
                {"role": "system", "content": self.system_prompt},
                *self.chat_history[-10:],
                {"role": "user",   "content": user_input},
            ]

            self.log.info("LLM: waiting for first token...")
            stream = self._llm.chat(
                model=self.llm_model, messages=messages, stream=True
            )

            full_response = ""
            buffer = ""
            token_count = 0

            for chunk in stream:
                # Support both dict-style and object-style Ollama responses
                if isinstance(chunk, dict):
                    token = chunk.get("message", {}).get("content", "") or ""
                else:
                    token = getattr(getattr(chunk, "message", None), "content", "") or ""

                if not token:
                    continue

                if token_count == 0:
                    self.log.info("LLM: first token received")

                token_count += 1
                full_response += token
                buffer += token

                # Speak at natural sentence boundaries.
                # Require at least 8 chars so we don't speak tiny fragments.
                stripped = buffer.rstrip()
                if stripped and stripped[-1] in ".!?" and len(stripped) >= 8:
                    self.log.debug("LLM: speaking chunk (%d chars)", len(stripped))
                    self.speak(buffer.strip())
                    buffer = ""

            self.log.info("LLM: stream complete (%d tokens)", token_count)

            # Speak any trailing text that didn't end with punctuation
            if buffer.strip():
                self.log.debug("LLM: speaking trailing buffer (%d chars)", len(buffer.strip()))
                self.speak(buffer.strip())

            # If the stream produced nothing at all speak a fallback
            if not full_response.strip():
                self.log.warning("LLM: empty response from model")
                self.speak("I... I don't know.")
                return "I... I don't know."

            reply = full_response.strip()

            with self._history_lock:
                self.chat_history.append({"role": "user",      "content": user_input})
                self.chat_history.append({"role": "assistant", "content": reply})
                if len(self.chat_history) > 100:
                    self.chat_history = self.chat_history[-100:]

            self._save_history()
            return reply

        except Exception as exc:
            self.log.warning("LLM error: %s", exc)
            reply = "I cannot think right now."
            self.speak(reply)
            return reply

    # ------------------------------------------------------------------
    # Command parsing
    # ------------------------------------------------------------------

    def parse_command(self, text: str) -> Optional[str]:
        """Return a movement keyword if a known phrase is found in *text*."""
        lower = text.lower()
        for cmd, phrases in self._COMMAND_MAP.items():
            if any(p in lower for p in phrases):
                return cmd
        return None

    # ------------------------------------------------------------------
    # Chat history persistence
    # ------------------------------------------------------------------

    def _load_history(self) -> None:
        try:
            if self._history_file.exists():
                with self._history_file.open() as f:
                    with self._history_lock:
                        self.chat_history = json.load(f)
                self.log.info("Loaded %d history entries", len(self.chat_history))
        except Exception as exc:
            self.log.warning("Could not load chat history: %s", exc)

    def _save_history(self) -> None:
        try:
            self._history_file.parent.mkdir(parents=True, exist_ok=True)
            with self._history_lock:
                data = list(self.chat_history)
            with self._history_file.open("w") as f:
                json.dump(data, f)
        except Exception as exc:
            self.log.error("Could not save chat history: %s", exc)
