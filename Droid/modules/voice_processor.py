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


class VoiceProcessor:
    """Handles microphone input, text-to-speech output, and LLM responses.

    * ``listen()``        -  blocks until speech is heard (or timeout).
    * ``speak()``         -  fires-and-forgets; returns immediately.
    * ``get_response()``  -  queries the local Ollama LLM.
    * ``parse_command()`` -  maps plain-language phrases to movement commands.
    """

    _COMMAND_MAP: Dict[str, List[str]] = {
        "FORWARD":  ["go forward", "move forward", "forward", "let's go"],
        "BACKWARD": ["go back", "move back", "back", "reverse"],
        "LEFT":     ["turn left", "go left", "left"],
        "RIGHT":    ["turn right", "go right", "right"],
        "STOP":     ["stop", "halt", "freeze", "wait"],
    }

    def __init__(self) -> None:
        self.log = logger.get_logger("VoiceProcessor")

        self._recognizer  = self._init_recognizer()

        # TTS: pyttsx3 on Windows (SAPI5) uses a COM Single-Threaded
        # Apartment - the engine must be created AND used in the same
        # thread.  We spin up a dedicated worker and let it do the init.
        self._engine: Optional[pyttsx3.Engine] = None
        self._tts_queue: queue.Queue = queue.Queue()
        self._tts_ready = threading.Event()
        threading.Thread(
            target=self._tts_worker, daemon=True, name="TTSWorker"
        ).start()
        if not self._tts_ready.wait(timeout=5.0):
            self.log.warning("TTS engine did not initialise within 5 s")

        self._llm = self._init_llm()

        self.llm_model     = config.get("llm.model", "neural-chat")
        self.system_prompt = self._build_system_prompt()

        self.chat_history: List[Dict] = []
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
            rec.pause_threshold       = config.get("voice.recognizer_pause_threshold", 2.3)
            return rec
        except Exception as exc:
            self.log.error("Recognizer init failed: %s", exc)
            return None

    def _tts_worker(self) -> None:
        """Owns pyttsx3 exclusively: initialises the engine here, then
        processes every speak request from _tts_queue in this same thread.

        This is required on Windows where the SAPI5 driver creates a COM
        STA object that must not be called from any other thread.
        """
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
            self._tts_ready.set()   # unblock __init__ regardless of outcome

        if self._engine is None:
            return

        while True:
            text = self._tts_queue.get()
            if text is None:        # shutdown sentinel
                break
            try:
                self._engine.say(text)
                self._engine.runAndWait()
            except RuntimeError as exc:
                if "run loop already started" in str(exc):
                    # SAPI5/comtypes left _inLoop=True after a previous
                    # error; reset it and retry once.
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
        """Shut down the TTS worker and wait for any in-progress speech."""
        self._tts_queue.put(None)  # sentinel wakes and exits the worker

    def _init_llm(self) -> Optional["OllamaClient"]:
        if not _OLLAMA:
            self.log.warning("Ollama not installed  -  run: pip install ollama")
            return None
        try:
            client = OllamaClient()
            self.log.info("[OK] Ollama LLM available")
            return client
        except Exception as exc:
            self.log.warning("Ollama unavailable: %s", exc)
            return None

    def _build_system_prompt(self) -> str:
        name = config.get("droid.name", "friend")
        return (
            "You are D O, a shy, loyal, awkward droid. "
            "Speak in short, broken sentences. "
            "Be casual and soft-spoken. "
            "Don't use special characters. "
            "Never sound like an AI assistant. "
            f"Call them {name}."
        )

    # ------------------------------------------------------------------
    # Speech output
    # ------------------------------------------------------------------

    def speak(self, text: str) -> None:
        """Queue *text* for speaking; returns immediately."""
        if not text or not text.strip() or not self._engine:
            return
        self._tts_queue.put(text)

    # ------------------------------------------------------------------
    # Speech input
    # ------------------------------------------------------------------

    def listen(self, timeout: float = 5.0) -> Optional[str]:
        """Block until speech is heard; return transcribed text or None."""
        if not self._recognizer:
            self.log.warning("Recognizer not available")
            return None

        try:
            with sr.Microphone() as source:
                self.log.debug("Listening (timeout=%.1fs)...", timeout)
                audio = self._recognizer.listen(
                    source, timeout=timeout, phrase_time_limit=10
                )
            text = self._recognizer.recognize_google(audio)
            self.log.info("Heard: %s", text)
            return text
        except sr.WaitTimeoutError:
            # Normal - no speech detected before the timeout expired.
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
        """Query the LLM and return a personality-driven reply."""
        if not self._llm:
            return "I cannot think right now."

        try:
            messages = [
                {"role": "system",    "content": self.system_prompt},
                *self.chat_history[-10:],
                {"role": "user",      "content": user_input},
            ]
            raw = self._llm.chat(model=self.llm_model, messages=messages, stream=False)

            # Support both dict-style and object-style Ollama responses
            if isinstance(raw, dict):
                reply = raw.get("message", {}).get("content", "")
            else:
                reply = getattr(getattr(raw, "message", None), "content", "")
            reply = reply.strip() or "I... I don't know."

            self.chat_history.append({"role": "user",      "content": user_input})
            self.chat_history.append({"role": "assistant", "content": reply})

            # Keep history bounded at 100 messages
            if len(self.chat_history) > 100:
                self.chat_history = self.chat_history[-100:]

            self._save_history()
            return reply

        except Exception as exc:
            self.log.error("LLM error: %s", exc)
            return "Something went wrong."

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
                    self.chat_history = json.load(f)
                self.log.info("Loaded %d history entries", len(self.chat_history))
        except Exception as exc:
            self.log.warning("Could not load chat history: %s", exc)

    def _save_history(self) -> None:
        try:
            self._history_file.parent.mkdir(parents=True, exist_ok=True)
            with self._history_file.open("w") as f:
                json.dump(self.chat_history, f)
        except Exception as exc:
            self.log.error("Could not save chat history: %s", exc)
