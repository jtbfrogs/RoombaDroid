# RoombaDroid – Droid System v3.0 · Codebase Reference

> **Audience:** developers and AI coding assistants working on future sessions.  
> **Purpose:** single authoritative source of truth for architecture, APIs, config, and known quirks.  
> This file supersedes scattered notes in older `.md` files wherever they conflict.

---

## Table of Contents

1. [Project Purpose](#1-project-purpose)
2. [Repository Layout](#2-repository-layout)
3. [Dependency Stack](#3-dependency-stack)
4. [System Architecture](#4-system-architecture)
5. [Boot Sequence](#5-boot-sequence)
6. [State Machine](#6-state-machine)
7. [Threading Model](#7-threading-model)
8. [Command Flow](#8-command-flow)
9. [Module Reference](#9-module-reference)
   - [core/logger.py](#coreloggerpy)
   - [core/state_machine.py](#corestate_machinepy)
   - [core/worker_pool.py](#coreworker_poolpy)
   - [core/controller.py](#corecontrollerpy)
   - [utils/config.py](#utilsconfigpy)
   - [utils/command_queue.py](#utilscommand_queuepy)
   - [modules/roomba_interface.py](#modulesroomba_interfacepy)
   - [modules/vision_processor.py](#modulesvision_processorpy)
   - [modules/voice_processor.py](#modulesvoice_processorpy)
10. [Configuration Reference](#10-configuration-reference)
11. [Voice Command Map](#11-voice-command-map)
12. [Error Handling & Graceful Degradation](#12-error-handling--graceful-degradation)
13. [Log Files](#13-log-files)
14. [Running & Testing](#14-running--testing)
15. [Known Limitations & Caveats](#15-known-limitations--caveats)
16. [Extension Points](#16-extension-points)

---

## 1. Project Purpose

A Star Wars-themed droid built on an iRobot Roomba base.  
The droid responds to spoken natural-language commands, holds conversations
via a local Ollama LLM, navigates via UART motor control, and watches the
environment through a USB camera.

**Target platform:** Windows (primary – uses SAPI5 TTS, winsound, pycaw, COM ports).  
Linux / macOS run in degraded mode (no TTS beeps, no Windows volume control).

---

## 2. Repository Layout

```
Droid/
├── main.py                   # Entry point – boot sequence + main loop
├── config.json               # Runtime config (auto-created from defaults)
├── requirements.txt          # Pinned pip dependencies
├── diagnostic.py             # Pre-flight dependency & hardware checker
├── test_system.py            # Unit / integration test suite
├── batch_example.py          # Priority-queue demo
├── run.sh / run.bat          # OS convenience launchers
│
├── core/
│   ├── controller.py         # DroidController – central orchestrator
│   ├── state_machine.py      # StateMachine + DroidState enum
│   ├── logger.py             # LoggerManager singleton (rotating files)
│   └── worker_pool.py        # WorkerPool – daemon thread pool
│
├── modules/
│   ├── roomba_interface.py   # UART driver (iRobot OI protocol)
│   ├── vision_processor.py   # OpenCV + MediaPipe camera pipeline
│   └── voice_processor.py    # STT, TTS, LLM, beep, volume
│
├── utils/
│   ├── config.py             # JSON config with dot-notation access
│   └── command_queue.py      # Priority command queue + handler registry
│
├── data/
│   └── chat_history.json     # Persisted LLM conversation history
│
└── logs/
    └── *.log                 # Per-module rotating log files
```

> **Note:** `smart_lights.py` and a Govee lights module are referenced in some
> older docs and in `config.json` defaults but **do not exist** in the current
> codebase. The `lights` config section and any `set_light()` / `droid.lights`
> calls in example docs are unimplemented stubs.

---

## 3. Dependency Stack

| Package | Role | Optional? |
|---|---|---|
| `pyserial` | Roomba UART | No (movement disabled without it) |
| `opencv-python` / `opencv-contrib-python` | Camera capture | No (vision disabled without it) |
| `SpeechRecognition` | Microphone STT via Google | No (voice disabled without it) |
| `pyaudio` | Microphone backend for SpeechRecognition | No |
| `pyttsx3` | Text-to-speech (SAPI5 on Windows) | No (TTS disabled without it) |
| `mediapipe` | Pose + face detection | **Yes** – falls back to Haar cascade |
| `ollama` | Local LLM client | **Yes** – LLM disabled without it |
| `pycaw` + `comtypes` | Windows volume control | **Yes** – volume control disabled |
| `winsound` | Startup/status beeps | **Yes** (stdlib on Windows only) |

---

## 4. System Architecture

```
┌─────────────────────────────────────────────────────┐
│                   main.py                           │
│  signal handler · boot sequence · main loop         │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│              DroidController                        │
│  StateMachine · CommandQueue · WorkerPool           │
│  lazy properties: roomba / vision / voice           │
└────┬────────────┬─────────────┬─────────────────────┘
     │            │             │
┌────▼────┐  ┌───▼────┐  ┌─────▼──────┐
│ Roomba  │  │ Vision │  │   Voice    │
│Interface│  │Processor│  │ Processor  │
│ UART/OI │  │OpenCV  │  │STT·TTS·LLM │
└─────────┘  └────────┘  └────────────┘
```

**Key design choices:**

| Choice | Rationale |
|---|---|
| Lazy module init | Startup stays fast even if hardware is absent; failed init is cached so it's not retried |
| Priority `CommandQueue` | Emergency STOP can jump the queue ahead of movement commands |
| `WorkerPool` for blocking tasks | LLM calls (~28 s) and long I/O don't stall the main loop |
| `StateMachine` with validated transitions | Prevents illegal state changes; fires callbacks (e.g. emergency stop on ERROR) |
| Rotating file logs per module | Post-mortem debugging without disk fill |

---

## 5. Boot Sequence

```
main()
 ├─ logger.init("logs")
 ├─ DroidController.__init__()
 │    ├─ StateMachine()                 → state = IDLE
 │    ├─ CommandQueue(max=50)
 │    ├─ WorkerPool(workers=3)
 │    ├─ _register_handlers()           → move/speak/listen/stop → handler fns
 │    └─ _register_callbacks()          → ERROR state → emergency stop
 │
 ├─ droid.start()
 │    ├─ worker_pool.start()            → spawns Worker-0/1/2 threads
 │    └─ voice.speak("Hello, I am awake.")   ← lazy-inits VoiceProcessor
 │
 └─ droid.initialize()
      ├─ roomba  → connect + SAFE mode, start watchdog thread
      ├─ vision  → open camera, drain warmup frames, start VisionLoop thread
      ├─ voice   → calibrate mic, log audio devices, set volume
      ├─ beep("startup")               → ascending R2-D2 chirp
      └─ speak("Droid online. All systems ready.")
```

After `initialize()` returns, `main()` enters the main loop:

```python
while droid.running and not shutdown_requested.is_set():
    droid.process_commands(timeout=0.05)   # drain queue
    if idle and queue empty:
        droid.listen(timeout=5.0)          # blocks up to 5 s for speech
    time.sleep(0.05)
```

**Ctrl-C / SIGINT** sets `shutdown_requested`, calls `droid.stop()`, and
launches a 3-second force-exit thread as a safety net.

---

## 6. State Machine

### States (`DroidState` enum)

| State | Meaning |
|---|---|
| `IDLE` | Waiting; listen loop runs here |
| `LISTENING` | Microphone open, waiting for speech |
| `THINKING` | Speech received; command parsing or LLM in progress |
| `MOVING` | Drive command sent to Roomba |
| `TRACKING` | Vision-guided follow mode (reserved for future use) |
| `EXECUTING` | Running a multi-step command sequence (reserved) |
| `ERROR` | Hardware/logic error – triggers emergency stop callback |
| `SHUTDOWN` | Terminal state; no further transitions allowed |

### Valid Transitions

```
IDLE        → LISTENING, MOVING, TRACKING, ERROR, SHUTDOWN
LISTENING   → THINKING, IDLE, ERROR
THINKING    → EXECUTING, IDLE, ERROR
MOVING      → IDLE, TRACKING, ERROR
TRACKING    → MOVING, IDLE, ERROR
EXECUTING   → IDLE, ERROR
ERROR       → IDLE, SHUTDOWN
SHUTDOWN    → (none)
```

`can_accept_commands()` returns `False` when state is `ERROR` or `SHUTDOWN`,
which blocks movement commands even if queued.

### Callbacks

```python
state_machine.register_callback(DroidState.ERROR, my_fn)
# my_fn(previous_state: DroidState, new_state: DroidState) -> None
```

The controller registers one built-in callback: entering `ERROR` sends an
immediate `STOP` to the Roomba.

---

## 7. Threading Model

```
Main Thread (main.py)
 ├── process_commands()   – drains CommandQueue, calls handlers synchronously
 └── listen()             – blocks on microphone for up to 5 s

Worker-0 / Worker-1 / Worker-2  (WorkerPool daemon threads)
 ├── _return_to_idle()    – sleeps 0.5 s then transitions state back to IDLE
 └── voice.get_response() – long-running LLM streaming call

RoombaWatchdog  (daemon thread inside RoombaInterface)
 └── every 0.2 s: sends STOP if no command received in watchdog_timeout seconds

VisionLoop  (daemon thread inside VisionProcessor)
 └── continuous: captures frames, runs detection every frame_skip-th frame

TTSWorker  (daemon thread inside VoiceProcessor)
 └── serialises pyttsx3 calls (SAPI5 COM STA requirement)
```

**Total threads at runtime:** 1 main + 3 workers + 1 watchdog + 1 vision + 1 TTS = **7 threads**.

---

## 8. Command Flow

```
droid.move("FORWARD")
  └─ queue_command("move", {"direction": "FORWARD"}, priority=0)
       └─ CommandQueue.put(Command("move", {"direction":"FORWARD"}, priority=0))

main loop: droid.process_commands()
  └─ CommandQueue.get()   → returns Command (highest priority first)
       └─ CommandQueue.execute(cmd)
            └─ DroidController._handle_move({"direction": "FORWARD"})
                 ├─ state_machine.transition(MOVING)
                 ├─ roomba.send_command("FORWARD")
                 └─ worker_pool.submit(_return_to_idle, delay=0.5)
                      └─ [0.5 s later, Worker thread] state_machine.transition(IDLE)
```

**Priority values in practice:**

```python
droid.queue_command("stop", {}, priority=100)    # emergency – runs first
droid.queue_command("move", {"direction": "LEFT"}, priority=50)
droid.move("FORWARD")                            # priority=0  (default)
```

---

## 9. Module Reference

### `core/logger.py`

**Class:** `LoggerManager` (used as a class-level singleton, imported as `logger`)

| Method | Signature | Notes |
|---|---|---|
| `init` | `(log_dir: str = "logs") -> None` | Creates dir, safe to call multiple times |
| `get_logger` | `(name: str) -> logging.Logger` | Returns cached logger; creates if absent |

Each logger gets:
- Console handler: `INFO` and above, UTF-8 safe (important on Windows cp1252 consoles)
- File handler: `DEBUG` and above, rotating at 5 MB, 3 backups, path `logs/{name}.log`

**Usage:**
```python
from core.logger import logger
log = logger.get_logger("MyModule")
log.info("Hello")
log.debug("detail only in file")
```

---

### `core/state_machine.py`

**Class:** `StateMachine`

| Method | Signature | Returns | Notes |
|---|---|---|---|
| `transition` | `(new_state: DroidState) -> bool` | `True` if transition succeeded | Logs warning on invalid transition |
| `is_in_state` | `(state: DroidState) -> bool` | `bool` | |
| `can_transition_to` | `(state: DroidState) -> bool` | `bool` | Does not perform the transition |
| `can_accept_commands` | `() -> bool` | `bool` | `False` when `ERROR` or `SHUTDOWN` |
| `register_callback` | `(state: DroidState, callback: Callable) -> None` | – | Fires on entry to `state`; `cb(prev, new)` |

**Attributes:** `current_state`, `previous_state`

---

### `core/worker_pool.py`

**Class:** `WorkerPool`

| Method | Signature | Returns | Notes |
|---|---|---|---|
| `start` | `() -> None` | – | Spawns `num_workers` daemon threads |
| `stop` | `() -> None` | – | Sends `None` sentinel to each worker, joins with 1 s timeout |
| `submit` | `(func: Callable, *args, **kwargs) -> bool` | `False` if queue full | Enqueues `(func, args, kwargs)`; 1 s put timeout |

Workers run `func(*args, **kwargs)` and catch+log any exception.  
`None` in the internal queue is the shutdown sentinel.

---

### `core/controller.py`

**Class:** `DroidController`

#### Lazy Hardware Properties

| Property | Type | Notes |
|---|---|---|
| `roomba` | `Optional[RoombaInterface]` | Returns `None` if failed or `not connected` |
| `vision` | `Optional[VisionProcessor]` | Returns `None` if failed; starts processor on first access |
| `voice` | `Optional[VoiceProcessor]` | Returns `None` if failed |

Failure sentinels (`_roomba_failed`, `_vision_failed`, `_voice_failed`) prevent
repeated init attempts after a hard failure.

#### Lifecycle

| Method | Notes |
|---|---|
| `start()` | Starts WorkerPool, triggers lazy voice init, speaks greeting |
| `initialize()` | Eagerly inits all hardware, calibrates mic, runs beep+TTS test |
| `stop()` | Sets `running=False`, transitions to SHUTDOWN, stops all modules and pool |

#### Public Command API

| Method | Signature | Notes |
|---|---|---|
| `queue_command` | `(type, data={}, priority=0) -> bool` | Returns `False` if queue full |
| `move` | `(direction: str) -> bool` | Shorthand for `queue_command("move", ...)` |
| `speak` | `(text: str) -> bool` | Shorthand for `queue_command("speak", ...)` |
| `listen` | `(timeout=5.0) -> bool` | Shorthand for `queue_command("listen", ...)` |
| `process_commands` | `(timeout=0.1) -> int` | Drains queue; returns count executed |

#### Built-in Command Handlers

| Command type | Handler | What it does |
|---|---|---|
| `"move"` | `_handle_move` | Validates state, transitions to MOVING, sends direction to Roomba, schedules return-to-IDLE via WorkerPool |
| `"speak"` | `_handle_speak` | Calls `voice.speak(text)` (fire-and-forget via TTSWorker) |
| `"listen"` | `_handle_listen` | Transitions LISTENING→THINKING, parses movement or submits LLM call via WorkerPool |
| `"stop"` | `_handle_stop` | Sends STOP to Roomba, transitions to IDLE |

**`_handle_listen` LLM path detail:**
1. Speaks `"hmm..."` immediately so the user knows the droid heard them.
2. Submits `voice.get_response(text)` to the WorkerPool (non-blocking).
3. `get_response` streams tokens from Ollama, speaking each complete sentence.
4. State transitions to IDLE immediately after submitting (doesn't wait for LLM).

---

### `utils/config.py`

**Class:** `Config` (module-level singleton `config`)

| Method | Signature | Notes |
|---|---|---|
| `get` | `(path: str, default=None) -> Any` | Dot-notation, e.g. `"roomba.uart_port"`. Caches result. |
| `set` | `(path: str, value: Any) -> None` | Writes through to `config.json`; invalidates cache entry |

`config.json` is created from defaults on first run. Edit it directly or call `config.set()`.

---

### `utils/command_queue.py`

**Class:** `Command`

```python
Command(command_type: str, data: dict = None, priority: int = 0)
# Attributes: command_type, data, priority, created_at (monotonic float)
```

**Class:** `CommandQueue`

| Method | Signature | Returns | Notes |
|---|---|---|---|
| `put` | `(command, timeout=None) -> bool` | `False` if full | Internally stores `(-priority, seq, command)` for max-heap behaviour |
| `get` | `(timeout=0.1) -> Optional[Command]` | `None` if empty | |
| `execute` | `(command) -> bool` | `False` if no handler or handler raises | Dispatches to all registered handlers |
| `register_handler` | `(type: str, handler: Callable) -> None` | – | Multiple handlers per type are supported |
| `size` | `() -> int` | Queue depth | |
| `stats` | `() -> dict` | `{"processed": N, "dropped": N}` | |

---

### `modules/roomba_interface.py`

**Class:** `RoombaInterface`

Implements the iRobot Open Interface (OI) over a serial UART connection.

#### iRobot OI Startup Sequence (mandatory)

```
Serial open → wait wakeup_wait_time → START (0x80) → 20 ms → SAFE (0x83)
```
Without this sequence, `DRIVE` (opcode 137) commands are silently ignored.

#### Drive Packet Format (opcode 137)

```
[137][vel_high][vel_low][rad_high][rad_low]
Velocity: -500 to +500 mm/s (negative = backward)
Radius:   0x8000 = straight, 0x0001 = CCW spin, 0xFFFF = CW spin
```

#### Direction Map

| Direction string | Velocity | Radius |
|---|---|---|
| `FORWARD` | `+velocity` (config) | `0x8000` (straight) |
| `BACKWARD` | `-velocity` | `0x8000` |
| `LEFT` | `+spin_velocity` (config) | `0x0001` (CCW) |
| `RIGHT` | `+spin_velocity` | `0xFFFF` (CW) |
| `STOP` | `0` | `0x0000` |

#### Public Methods

| Method | Notes |
|---|---|
| `send_command(direction: str) -> bool` | Direction must match map above (case-insensitive). Returns `False` if not connected. |
| `stop()` | Disables watchdog, sends STOP, closes serial port |

#### Watchdog

Background daemon thread (`RoombaWatchdog`) checks every 0.2 s.  
If the current command is not `STOP` and no command has arrived within
`roomba.watchdog_timeout` seconds, it automatically sends `STOP`.  
This prevents the robot from driving indefinitely if the software hangs.

#### Attributes

| Attribute | Type | Notes |
|---|---|---|
| `connected` | `bool` | Set `False` on serial error; checked by `controller.roomba` property |
| `uart_port` | `str` | Logged on successful connect |
| `current_command` | `str` | Last sent direction string |

---

### `modules/vision_processor.py`

**Class:** `VisionProcessor`

#### Detection Pipeline

1. **Haar cascade** (`haarcascade_frontalface_default.xml`) – always available via OpenCV
2. **MediaPipe** `Pose` + `FaceDetection` – only when `mediapipe` is installed and `mp.solutions` exists

Frame skipping: only every `vision.frame_skip`-th frame runs detection. Others are captured but discarded, keeping camera read continuous.

#### Lifecycle

| Method | Notes |
|---|---|
| `start()` | Drains `warmup_frames` then starts `VisionLoop` daemon thread |
| `stop()` | Stops loop, releases `cv2.VideoCapture` |

#### Public Accessors

| Method | Returns | Notes |
|---|---|---|
| `get_frame() -> Optional[dict]` | `{"faces": [...], "poses": [...], "frame": ndarray}` or `None` | Thread-safe |
| `detect_face() -> (bool, Optional[dict])` | `(True, {"x","y","w","h"})` if face found | Uses latest frame |

#### Camera Init Note

`_init_camera()` does **not** raise on failure; it logs a warning and leaves
`self._cap = None`. `controller.initialize()` checks `self._vision._cap is not None`
to distinguish "VisionProcessor created but camera missing" from "VisionProcessor
not created at all".

---

### `modules/voice_processor.py`

**Class:** `VoiceProcessor`

#### Sub-systems

| Sub-system | Class/Library | Thread |
|---|---|---|
| Speech-to-text | `speech_recognition.Recognizer` + Google API | Main (blocks in `listen()`) |
| Text-to-speech | `pyttsx3` (SAPI5 on Windows) | `TTSWorker` daemon |
| LLM | `ollama.Client` streaming | WorkerPool thread (submitted from `_handle_listen`) |
| Volume control | `pycaw` (Windows only) | Main |
| Beep | `winsound` (Windows only) | Main |

#### TTS Threading Note

SAPI5 requires the pyttsx3 engine to be **created and used in the same thread**
(COM STA requirement). `VoiceProcessor` owns a `TTSWorker` daemon thread that:
1. Creates `pyttsx3.init()` on startup.
2. Sits in a loop reading from `_tts_queue`.
3. Calls `engine.say(text)` + `engine.runAndWait()` for each item.

`speak(text)` simply does `_tts_queue.put(clean_text)` – it is non-blocking.  
ASCII sanitisation is applied before queuing to prevent SAPI5 silently dropping
utterances that contain emoji or non-ASCII symbols.

#### Key Methods

| Method | Signature | Notes |
|---|---|---|
| `speak` | `(text: str) -> None` | Non-blocking; queued to TTSWorker |
| `listen` | `(timeout=5.0) -> Optional[str]` | Blocking; uses Google STT |
| `calibrate` | `(duration=1.0) -> None` | Adjusts energy threshold for ambient noise; call once at startup |
| `get_response` | `(user_input: str) -> str` | Streams Ollama, speaks sentences as they arrive; saves to history |
| `parse_command` | `(text: str) -> Optional[str]` | Returns movement keyword or `None` |
| `beep` | `(pattern="startup") -> None` | Patterns: `startup`, `ok`, `error`; Windows only |
| `set_system_volume` | `(level: int) -> None` | 0–100; uses pycaw, falls back to pyttsx3 volume |
| `get_system_volume` | `() -> Optional[int]` | Returns 0–100 or `None` |
| `log_audio_devices` | `() -> None` | Logs PyAudio in/out and SAPI5 output device indices |
| `stop` | `() -> None` | Sends `None` sentinel to TTSWorker |

#### LLM Conversation History

- Stored in `data/chat_history.json` (JSON list of `{"role", "content"}` dicts)
- Last 10 exchanges sent to Ollama as context
- Capped at 100 total messages (oldest pruned first)
- Protected by `_history_lock` (TTSWorker and WorkerPool threads may both access)

#### System Prompt (character definition)

```
"You are D O, a shy, loyal, awkward droid.
Speak in short, broken sentences.
Be casual and soft-spoken.
Use only plain English letters and basic punctuation.
No emoji. No special symbols. No markdown.
Never sound like an AI assistant.
Call them {droid.name}."
```

---

## 10. Configuration Reference

`config.json` is loaded by `utils/config.py` at import time.  
Sections and keys with their **types**, **defaults**, and notes:

### `droid`

| Key | Type | Default | Notes |
|---|---|---|---|
| `name` | str | `"D O"` | Used in LLM system prompt |
| `personality` | str | `"shy, loyal, awkward droid"` | Informational only |

### `roomba`

| Key | Type | Default | Notes |
|---|---|---|---|
| `uart_port` | str | `"COM7"` | Windows COM port, e.g. `"COM3"`, `"COM4"` |
| `baud_rate` | int | `115200` | Must match Roomba OI spec |
| `use_rts_cts` | bool | `true` | Hardware flow control |
| `wakeup_wait_time` | float | `0.5` | Seconds to wait after serial open before OI startup |
| `velocity` | int | `200` | Forward/backward speed mm/s |
| `spin_velocity` | int | `100` | Left/right spin speed mm/s |
| `max_velocity` | int | `500` | Clamped maximum mm/s |
| `watchdog_timeout` | float | `2.0` | Seconds before watchdog auto-stops |
| `connection_timeout` | float | `3.0` | Serial port open timeout |

### `vision`

| Key | Type | Default | Notes |
|---|---|---|---|
| `camera_index` | int | `0` | OpenCV device index; try `1` if default fails |
| `frame_width` | int | `640` | Requested width in pixels |
| `frame_height` | int | `480` | Requested height in pixels |
| `fps` | int | `30` | Requested camera FPS |
| `frame_skip` | int | `2` | Run detection on every Nth frame |
| `min_detection_confidence` | float | `0.5` | MediaPipe confidence threshold |
| `warmup_frames` | int | `5` | Frames read and discarded at camera start |

### `voice`

| Key | Type | Default | Notes |
|---|---|---|---|
| `recognizer_energy_threshold` | int | `300` | Initial STT energy threshold (auto-adjusted by `calibrate()`) |
| `recognizer_pause_threshold` | float | `0.8` | Silence duration (s) that ends a phrase |
| `tts_rate` | int | `230` | pyttsx3 words-per-minute |
| `tts_volume` | float | `1.0` | pyttsx3 volume (0.0–1.0) |
| `language` | str | `"en-US"` | Reserved; Google STT uses system locale |
| `system_volume` | int | `90` | Windows master volume set at startup (0–100) |
| `microphone_index` | int\|null | `null` | PyAudio device index; `null` = system default |
| `speaker_index` | int\|null | `null` | SAPI5 output device index; `null` = SAPI5 default |

> **Finding device indices:** run `droid.initialize()` (or just start the system);
> `log_audio_devices()` is called automatically and prints all indices to the log.

### `llm`

| Key | Type | Default | Notes |
|---|---|---|---|
| `model` | str | `"neural-chat"` | Ollama model name; must be pulled first: `ollama pull neural-chat` |

### `lights`

| Key | Type | Default | Notes |
|---|---|---|---|
| `enabled` | bool | `false` | **Unimplemented** – lights module does not exist in v3.0 |
| `govee_api_key` | str | `""` | Reserved for future Govee integration |
| `govee_device_id` | str | `""` | Reserved |

### `performance`

| Key | Type | Default | Notes |
|---|---|---|---|
| `worker_threads` | int | `5` | Number of WorkerPool daemon threads |
| `command_queue_size` | int | `50` | Max commands before `put()` returns `False` |
| `enable_profiling` | bool | `false` | Reserved; not yet implemented |

---

## 11. Voice Command Map

`VoiceProcessor.parse_command()` does case-insensitive substring matching.
First match wins.

| Returns | Trigger phrases |
|---|---|
| `FORWARD` | forward, go forward, move forward, drive forward, go ahead, move ahead, straight, go straight, advance, lets go, let's go, move |
| `BACKWARD` | back, backward, backwards, go back, move back, reverse, back up, go backward |
| `LEFT` | left, turn left, go left, rotate left, spin left, face left |
| `RIGHT` | right, turn right, go right, rotate right, spin right, face right |
| `STOP` | stop, halt, freeze, wait, hold on, stay, cancel, enough, cease |

Any text that doesn't match goes to the LLM for a conversational response.

---

## 12. Error Handling & Graceful Degradation

| Failure | Effect |
|---|---|
| Roomba not found / serial error | `roomba` property returns `None`; movement commands silently no-op |
| Camera not available | `_cap` is `None`; vision accessor returns the `VisionProcessor` object but `get_frame()` returns `None` |
| Camera read error during loop | `VisionLoop` stops; `get_frame()` returns last successful frame |
| MediaPipe not installed | Falls back to Haar cascade only |
| pyttsx3 init failure | `_engine = None`; `speak()` no-ops; WARNING logged |
| Google STT request error | `listen()` returns `None`; ERROR logged |
| Ollama not running | `_llm = None`; `get_response()` speaks `"I cannot think right now."` |
| pycaw not installed | Volume control silently falls back to pyttsx3 volume only |
| TTS queue full | `queue.Full` is not caught by `speak()` – `_tts_queue` is unbounded (`queue.Queue()`) |
| Command queue full | `queue_command()` returns `False`; caller can check |
| WorkerPool queue full | `submit()` returns `False`; task is dropped and WARNING logged |
| State machine invalid transition | Returns `False`; WARNING logged; state unchanged |
| State machine entering ERROR | Callback fires `roomba.send_command("STOP")` |
| Any unhandled exception in main loop | ERROR logged; loop continues |
| Fatal exception before main loop | CRITICAL logged; `droid.stop()` attempted; `sys.exit(1)` |

---

## 13. Log Files

All logs are in `logs/` (created automatically).

| File | Module | Notable content |
|---|---|---|
| `logs/main.log` | `main` logger | Startup, shutdown, main loop errors |
| `logs/DroidController.log` | `DroidController` | Command handling, module init status |
| `logs/StateMachine.log` | `StateMachine` | All state transitions (DEBUG) |
| `logs/CommandQueue.log` | `CommandQueue` | Queue full drops, missing handler warnings |
| `logs/WorkerPool.log` | `WorkerPool` | Worker start/stop, task errors |
| `logs/RoombaInterface.log` | `RoombaInterface` | Connection, watchdog events, serial errors |
| `logs/VisionProcessor.log` | `VisionProcessor` | Camera init, frame errors |
| `logs/VoiceProcessor.log` | `VoiceProcessor` | STT results, TTS errors, LLM token counts |

Each file rotates at **5 MB** with **3 backups**. Console shows `INFO+`; files capture `DEBUG+`.

---

## 14. Running & Testing

### First run

```bash
cd Droid
python -m venv droid_env
# Windows:
droid_env\Scripts\activate
# Linux/macOS:
source droid_env/bin/activate

pip install -r requirements.txt

# Pre-flight check (always do this first):
python diagnostic.py

# Start the droid:
python main.py
```

### Test suite

```bash
python test_system.py        # Integration tests (no hardware required for most)
python diagnostic.py         # Dependency + config + component checks
python batch_example.py      # Priority queue demo (no hardware needed)
```

### What `diagnostic.py` tests

1. All required imports present
2. `config.json` loads and key paths resolve
3. Logger creates files
4. `StateMachine` performs a valid transition
5. `CommandQueue` put/get with priority ordering
6. All three module classes import successfully
7. `DroidController.__init__()` completes without error

### What `test_system.py` tests

1. Logger (multi-level messages)
2. Config (get, missing key default)
3. StateMachine (valid transitions, invalid transition rejection)
4. CommandQueue (put/get, priority ordering, handler execution)
5. Controller init, start, stop
6. Command queueing and processing
7. Roomba connection attempt (expected to fail without hardware)
8. Audio output via `winsound.Beep()`
9. VoiceProcessor init, TTS engine, STT recognizer, microphone enumeration, LLM availability

---

## 15. Known Limitations & Caveats

| Area | Issue |
|---|---|
| **Lights module** | `smart_lights.py` does not exist. `config.json` has a `lights` section and some old docs mention `droid.set_light()` and `droid.lights` – these are not implemented. |
| **TRACKING / EXECUTING states** | Defined in the state machine and transition table but no controller logic drives them. Vision-guided tracking is scaffolded but unimplemented. |
| **LLM model** | Default `"neural-chat"` must be pulled: `ollama pull neural-chat`. First response after a long idle can be slow (~28 s) while the model loads into RAM. |
| **Google STT requires internet** | `voice.listen()` sends audio to Google's servers. An offline alternative (e.g. Whisper) is not implemented. |
| **TTS is blocking per utterance** | `TTSWorker` processes one `speak()` call at a time. During a long LLM response (many sentence chunks), queued items accumulate. The queue is unbounded so this won't drop messages, but playback will lag behind generation. |
| **Windows-only audio features** | `winsound`, `pycaw`, and SAPI5 speaker routing are Windows-only. On Linux/macOS the droid runs but beeps and volume control are silently disabled. A different TTS backend (e.g. `espeak`) would be needed. |
| **Roomba FULL mode not used** | The driver starts the Roomba in SAFE mode (opcode 131), which keeps cliff sensors active. If you want to disable all safety overrides, change to `_OPC_FULL` (132). Be careful. |
| **Race on LLM + state** | After `_handle_listen` submits the LLM call to the WorkerPool it immediately transitions to IDLE. If a movement command arrives while the LLM is speaking, both execute concurrently. The TTS queue serialises speech, but Roomba movement and LLM speech can overlap. |
| **`pycaw` API variation** | Newer versions of pycaw wrap `IMMDevice` in an `AudioDevice` object. The code handles this with `getattr(speakers, "_dev", speakers)` but may need updating if pycaw changes its internal API again. |
| **mediapipe ≥ 0.10 on Windows** | The legacy `mp.solutions` API was dropped on Windows in mediapipe 0.10. The code guards with `hasattr(mp, 'solutions')` and falls back to Haar cascade only. |

---

## 16. Extension Points

### Adding a new command type

1. Write a handler function: `def _handle_mycommand(self, data: dict) -> None`
2. Register it in `DroidController._register_handlers()`:
   ```python
   self.command_queue.register_handler("mycommand", self._handle_mycommand)
   ```
3. Add a convenience method if desired:
   ```python
   def mycommand(self, param: str) -> bool:
       return self.queue_command("mycommand", {"param": param})
   ```

### Adding a new state

1. Add the variant to `DroidState` in `core/state_machine.py`
2. Add its valid transitions to `StateMachine.VALID_TRANSITIONS`
3. Register callbacks if needed

### Adding an LLM model

Change `llm.model` in `config.json` to any model available in your local Ollama:

```bash
ollama pull mistral
# then set "model": "mistral" in config.json
```

### Adding persistent config settings

`config.set("my_module.my_key", value)` writes through to `config.json` immediately.

### Adding a hardware module

Follow the pattern of existing modules:
1. Create `modules/my_module.py` with `__init__`, `stop()`, and relevant methods.
2. Add a `_my_module: Optional[MyModule]` attribute and `_my_module_failed` sentinel to `DroidController`.
3. Add a `@property` with lazy init and failure guard.
4. Add init and stop calls to `initialize()` and `stop()`.
5. Add config defaults to `Config._defaults()` in `utils/config.py`.

---

*Last updated: 2026-04-28. Reflects the actual source files as they exist in this repository.*
