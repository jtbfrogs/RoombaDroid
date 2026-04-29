"""Hardware module package.

Contains:
    RoombaInterface  - UART driver for iRobot Open Interface (OI) protocol.
    VisionProcessor  - OpenCV + MediaPipe camera capture and face/pose detection.
    VoiceProcessor   - Speech recognition (STT), text-to-speech (TTS), and Ollama LLM.

Note: SmartLights / smart_lights.py is NOT implemented in v3.0 despite being
listed in older documentation and the config.json 'lights' section.
"""
__all__ = ['RoombaInterface', 'VisionProcessor', 'VoiceProcessor']
