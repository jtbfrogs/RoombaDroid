"""Optimized voice processing with caching and pooling."""
import speech_recognition as sr
import pyttsx3
import json
import threading
from typing import Optional, Tuple
from pathlib import Path
from core.logger import logger
from utils.config import config

try:
    from ollama import Client as OllamaClient
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

class VoiceProcessor:
    """Fast voice input/output with LLM integration."""
    
    def __init__(self):
        self.log = logger.get_logger("VoiceProcessor")
        
        # Speech recognition
        try:
            self.recognizer = sr.Recognizer()
            self.recognizer.energy_threshold = config.get("voice.recognizer_energy_threshold", 300)
            self.recognizer.dynamic_energy_threshold = True
            self.recognizer.pause_threshold = config.get("voice.recognizer_pause_threshold", 2.3)
        except Exception as e:
            self.log.error(f"Recognizer init error: {e}")
            self.recognizer = None
        
        # Text-to-speech
        try:
            self.engine = pyttsx3.init()
            voices = self.engine.getProperty('voices')
            if voices:
                self.engine.setProperty('voice', voices[0].id)
            self.engine.setProperty('rate', config.get("voice.tts_rate", 230))
            self.engine.setProperty('volume', config.get("voice.tts_volume", 1.0))
        except Exception as e:
            self.log.error(f"TTS engine init error: {e}")
            self.engine = None
        
        # LLM (non-blocking init)
        self.llm_client: Optional[OllamaClient] = None
        self.llm_model = config.get("llm.model", "neural-chat")
        
        if OLLAMA_AVAILABLE:
            try:
                self.llm_client = OllamaClient()
                self.log.info("✓ Ollama LLM available")
            except Exception as e:
                self.log.warning(f"Ollama unavailable: {e}")
        else:
            self.log.warning("Ollama not installed (pip install ollama)")
        
        # Chat history
        self.chat_history = []
        self.chat_history_file = Path("data/chat_history.json")
        self._load_chat_history()
        
        # Personality
        self.system_prompt = self._build_system_prompt()
        
        # Threading
        self._speak_lock = threading.Lock()
    
    def _build_system_prompt(self) -> str:
        """Build personality prompt."""
        return (
            "You are D O, a shy, loyal, awkward droid. "
            "Speak in short, broken sentences. "
            "Be casual and soft-spoken. "
            "Don't use special characters. "
            "Never sound like an AI assistant. "
            f"Call them {config.get('droid.name', 'friend')}."
        )
    
    def speak(self, text: str, timeout: float = 10.0):
        """Convert text to speech (thread-safe, non-blocking)."""
        if not text or not text.strip() or not self.engine:
            return
        
        def speak_thread():
            with self._speak_lock:
                try:
                    self.log.debug(f"Speaking: {text[:50]}...")
                    # Use a timeout to prevent hang
                    try:
                        self.engine.say(text)
                        self.engine.runAndWait()
                    except Exception as e:
                        self.log.error(f"TTS error: {e}")
                except Exception as e:
                    self.log.error(f"Speak error: {e}")
        
        # Run in background thread to avoid blocking
        import threading
        thread = threading.Thread(target=speak_thread, daemon=True)
        thread.daemon = True
        thread.start()
        
        # Don't wait for completion - just start and return
    
    def listen(self, timeout: float = 5.0) -> Optional[str]:
        """Listen for speech input."""
        if not self.recognizer:
            self.log.warning("Recognizer not available")
            return None
        
        try:
            with sr.Microphone() as source:
                self.log.debug("Listening...")
                audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=10)
            
            try:
                text = self.recognizer.recognize_google(audio)
                self.log.info(f"Heard: {text}")
                return text
            except sr.UnknownValueError:
                self.log.warning("Could not understand")
                return None
            except sr.RequestError as e:
                self.log.error(f"Speech service error: {e}")
                return None
        except Exception as e:
            self.log.error(f"Microphone error: {e}")
            return None
    
    def get_response(self, user_input: str) -> str:
        """Get LLM response."""
        if not self.llm_client:
            return "I cannot think right now."
        
        try:
            messages = [
                {"role": "system", "content": self.system_prompt},
                *self.chat_history[-10:],  # Last 10 messages
                {"role": "user", "content": user_input}
            ]
            
            response = self.llm_client.chat(
                model=self.llm_model,
                messages=messages,
                stream=False
            )
            
            response_text = response.get('message', {}).get('content', "I... I don't know.")
            
            # Add to history
            self.chat_history.append({"role": "user", "content": user_input})
            self.chat_history.append({"role": "assistant", "content": response_text})
            
            # Keep manageable
            if len(self.chat_history) > 100:
                self.chat_history = self.chat_history[-100:]
            
            self._save_chat_history()
            return response_text
        except Exception as e:
            self.log.error(f"LLM error: {e}")
            return "Something went wrong."
    
    def _load_chat_history(self):
        """Load chat history from file."""
        try:
            if self.chat_history_file.exists():
                with open(self.chat_history_file) as f:
                    self.chat_history = json.load(f)
                self.log.info(f"Loaded {len(self.chat_history)} history items")
        except Exception as e:
            self.log.warning(f"Could not load history: {e}")
    
    def _save_chat_history(self):
        """Save chat history to file."""
        try:
            self.chat_history_file.parent.mkdir(exist_ok=True)
            with open(self.chat_history_file, 'w') as f:
                json.dump(self.chat_history, f)
        except Exception as e:
            self.log.error(f"Could not save history: {e}")
    
    def parse_command(self, text: str) -> Optional[str]:
        """Parse text for commands."""
        text_lower = text.lower()
        
        commands = {
            "FORWARD": ["go forward", "move forward", "forward", "let's go"],
            "BACKWARD": ["go back", "move back", "back", "reverse"],
            "LEFT": ["turn left", "go left", "left"],
            "RIGHT": ["turn right", "go right", "right"],
            "STOP": ["stop", "halt", "freeze", "wait"],
        }
        
        for cmd, patterns in commands.items():
            if any(p in text_lower for p in patterns):
                return cmd
        
        return None
