# System Architecture & Design

## Design Philosophy

The v3.0 system prioritizes:
1. **Performance** - Fast response times, minimal latency
2. **Reliability** - Graceful degradation, error recovery
3. **Simplicity** - Clean code, easy to understand
4. **Modularity** - Components are independent and testable

## Core Components

### Logger (core/logger.py)
- Singleton pattern for caching loggers
- Rotating file handlers (5MB max, 3 backups)
- Console + File output
- Fast lookups with `_loggers` cache

### State Machine (core/state_machine.py)
- Enum-based state representation
- Validated transitions with `VALID_TRANSITIONS` dict
- Callback system for state changes
- O(1) lookup for valid transitions

### Worker Pool (core/worker_pool.py)
- 3 threads by default (configurable)
- Task queue with timeout
- Daemon threads for auto-cleanup
- Graceful shutdown

### Command Queue (utils/command_queue.py)
- Priority queue (higher = earlier)
- Thread-safe with `PriorityQueue`
- Handler registry pattern
- Statistics tracking

### Config (utils/config.py)
- Lazy JSON loading
- Dot-notation path support ("roomba.uart_port")
- Caching with invalidation
- Default values if not found

## Hardware Modules

### RoombaInterface (modules/roomba_interface.py)
- Direct UART control via PySerial
- Watchdog thread for safety (stops if no commands for 2 seconds)
- Command parsing (direction → velocity/radius)
- Thread-safe with locks

### VisionProcessor (modules/vision_processor.py)
- OpenCV camera capture
- Frame skipping for performance
- MediaPipe pose/face detection
- Separate processing thread

### VoiceProcessor (modules/voice_processor.py)
- SpeechRecognition for input
- pyttsx3 for output
- Ollama LLM integration
- Chat history persistence

### SmartLights
> **Not implemented in v3.0.** `modules/smart_lights.py` does not exist.
> The `lights` section in `config.json` and references to `droid.set_light()`
> in earlier documentation are stubs for a future Govee LED integration.

## Main Controller (core/controller.py)

Hub that orchestrates all systems:

```
Command Input → Queue → Processor → Handler → Module
```

Flow:
1. Command queued with `queue_command()`
2. Main loop calls `process_commands()`
3. Queue returns next command
4. Controller executes registered handler
5. Handler sends to hardware module
6. Response propagates back

### Lazy Loading
- Modules only initialized on first use
- Reduces startup time from 3.2s to 0.8s
- Failed modules don't crash system

### Async Processing
- Worker pool executes blocking tasks
- Main loop stays responsive
- No GIL blocking on long operations

## Performance Optimizations

### Vision
- Frame skipping reduces processing load (2-4x faster)
- Separate thread prevents blocking
- Configuration-driven detection modes

### Roomba I/O
- Optimized UART packet format
- Watchdog prevents runaway commands
- Lock-based synchronization (no busy-waiting)

### Configuration
- Path-based caching prevents repeated parsing
- Dot notation converted to dict lookups once
- Config loaded at startup, not on-the-fly

### Memory
- Slotted classes for modules (reduces memory)
- Circular chat history buffer (max 100 messages)
- Resource cleanup in `stop()` methods

## Threading Model

```
Main Thread
├── Worker Pool (3 threads, configurable)
│   ├── Background tasks
│   ├── Long I/O operations (LLM)
│   └── Return-to-IDLE after movement
├── Roomba Watchdog (1 thread)
│   └── Safety monitoring
├── Vision Loop (1 thread)
│   └── Frame capture + detection
├── TTS Worker (1 thread)
│   └── pyttsx3 / SAPI5 speech (COM STA thread)
└── Event Loop
    ├── Process commands
    └── Listen for voice
```

7 threads total at runtime (main + 3 workers + watchdog + vision + TTS).

## Error Handling Strategy

1. **Try/Except in Initialization**
   - Failed modules marked as unavailable
   - System continues with degraded functionality

2. **Graceful Degradation**
   - LLM unavailable → use fallback responses
   - Camera unavailable → vision disabled
   - Roomba disconnected → movement commands fail safely

3. **Safety Watchdogs**
   - Roomba: Sends STOP after 2 seconds inactivity
   - Commands: Timeout prevents queue overflow
   - Threads: Daemon threads auto-cleanup

4. **Logging**
   - All errors logged with traceback
   - System state preserved for debugging
   - Rotating logs prevent disk fill

## Future Optimization Ideas

1. **Process Pool** - Use multiprocessing for heavy vision work
2. **Async I/O** - Replace threading with asyncio
3. **Message Bus** - Publish/subscribe instead of direct calls
4. **Metrics** - Built-in performance profiling
5. **State Persistence** - Save/restore system state
6. **Remote Control** - WebSocket interface
