"""Camera capture and object detection with configurable frame skipping."""
import threading
from typing import Dict, List, Optional, Tuple

import cv2

from core.logger import logger
from utils.config import config

try:
    import mediapipe as mp
    _MEDIAPIPE = True
except ImportError:
    _MEDIAPIPE = False


class VisionProcessor:
    """Captures camera frames in a background thread.

    Detection pipeline:
      1. Haar-cascade face detection (always available via OpenCV).
      2. MediaPipe pose + face detection (used when the package is installed).

    Frame skipping (``vision.frame_skip``) reduces CPU load by only running
    detection on every Nth captured frame.
    """

    def __init__(self) -> None:
        self.log = logger.get_logger("VisionProcessor")

        self.camera_index = config.get("vision.camera_index", 0)
        self.frame_width  = config.get("vision.frame_width", 640)
        self.frame_height = config.get("vision.frame_height", 480)
        self.fps          = config.get("vision.fps", 30)
        self.frame_skip   = config.get("vision.frame_skip", 2)

        self._cap: Optional[cv2.VideoCapture] = None
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._frame_count = 0
        self._current: Optional[Dict] = None
        self.running = False

        # Haar cascade  -  always loaded
        self._face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )

        # MediaPipe detectors  -  optional
        self._pose_detector = None
        self._face_detector = None
        if _MEDIAPIPE:
            if not hasattr(mp, 'solutions'):
                self.log.warning(
                    "MediaPipe installed but solutions API unavailable "
                    "(version too new)  -  using cascade only"
                )
            else:
                conf = config.get("vision.min_detection_confidence", 0.5)
                try:
                    self._pose_detector = mp.solutions.pose.Pose(
                        min_detection_confidence=conf
                    )
                    self._face_detector = mp.solutions.face_detection.FaceDetection(
                        min_detection_confidence=conf
                    )
                    self.log.info("[OK] MediaPipe detectors loaded")
                except Exception as exc:
                    self.log.warning(
                        "MediaPipe init failed (%s)  -  using cascade only", exc
                    )

        self._init_camera()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _init_camera(self) -> None:
        # Suppress OpenCV's C++ backend probing messages (FFMPEG, obsensor
        # etc.) that go directly to stderr and bypass Python logging.
        try:
            cv2.setLogLevel(6)  # 6 = LOG_LEVEL_SILENT
        except Exception:
            pass

        try:
            cap = cv2.VideoCapture(self.camera_index)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self.frame_width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.frame_height)
            cap.set(cv2.CAP_PROP_FPS,          self.fps)
            if cap.isOpened():
                self._cap = cap
                self.log.info("[OK] Camera %d initialised", self.camera_index)
            else:
                self.log.warning("Camera %d not available", self.camera_index)
        except Exception as exc:
            self.log.warning("Camera init error: %s", exc)

    def start(self) -> None:
        """Start the background capture loop."""
        if self.running or not self._cap:
            return
        self.running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="VisionLoop"
        )
        self._thread.start()
        self.log.info("Vision processing started")

    def stop(self) -> None:
        """Stop the capture loop and release the camera."""
        self.running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        if self._cap:
            self._cap.release()
        self.log.info("Vision stopped")

    # ------------------------------------------------------------------
    # Processing loop
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        while self.running and self._cap:
            ret, frame = self._cap.read()
            if not ret:
                continue

            self._frame_count += 1
            if self._frame_count % self.frame_skip != 0:
                continue  # skip this frame

            result = self._detect(frame)
            with self._lock:
                self._current = result

    def _detect(self, frame) -> Dict:
        """Run face and pose detection; return a results dict."""
        result: Dict = {"faces": [], "poses": [], "frame": frame}

        # Haar cascade face detection
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        raw_faces = self._face_cascade.detectMultiScale(gray, 1.3, 5)
        result["faces"] = [
            {"x": int(x), "y": int(y), "w": int(w), "h": int(h)}
            for x, y, w, h in raw_faces
        ]

        # MediaPipe pose detection
        if self._pose_detector:
            try:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pose_res = self._pose_detector.process(rgb)
                if pose_res.pose_landmarks:
                    result["poses"] = pose_res.pose_landmarks
            except Exception:
                pass  # non-fatal; cascade results still returned

        return result

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    def get_frame(self) -> Optional[Dict]:
        """Return the latest processed frame dict, or None."""
        with self._lock:
            return self._current

    def detect_face(self) -> Tuple[bool, Optional[Dict]]:
        """Return (True, face_dict) if a face is detected, else (False, None)."""
        frame = self.get_frame()
        if frame and frame.get("faces"):
            return True, frame["faces"][0]
        return False, None
