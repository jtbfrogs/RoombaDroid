"""Lightweight vision processor with frame skipping."""
import cv2
import threading
import time
from typing import Optional, Tuple
from core.logger import logger
from utils.config import config

try:
    import mediapipe as mp
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    MEDIAPIPE_AVAILABLE = False

class VisionProcessor:
    """Fast vision with face/pose detection and frame skipping."""
    
    def __init__(self):
        self.log = logger.get_logger("VisionProcessor")
        
        # Camera setup
        self.camera_index = config.get("vision.camera_index", 0)
        self.frame_width = config.get("vision.frame_width", 640)
        self.frame_height = config.get("vision.frame_height", 480)
        self.fps = config.get("vision.fps", 30)
        self.frame_skip = config.get("vision.frame_skip", 2)
        
        # State
        self.cap: Optional[cv2.VideoCapture] = None
        self.running = False
        self.current_frame: Optional[any] = None
        self.frame_count = 0
        
        # Detection
        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        
        self.pose_detector = None
        self.pose_detector = None
        self.face_detector = None
        if MEDIAPIPE_AVAILABLE:
            try:
                mp_pose = mp.solutions.pose
                mp_face = mp.solutions.face_detection
                self.pose_detector = mp_pose.Pose(min_detection_confidence=0.5)
                self.face_detector = mp_face.FaceDetection(min_detection_confidence=0.5)
                self.log.info("✓ MediaPipe modules loaded")
            except Exception as e:
                self.log.warning(f"MediaPipe load error: {e} (cascade detection will still work)")
                self.pose_detector = None
                self.face_detector = None
        
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        
        self._init_camera()
    
    def _init_camera(self):
        """Initialize camera."""
        try:
            self.cap = cv2.VideoCapture(self.camera_index)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.frame_width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.frame_height)
            self.cap.set(cv2.CAP_PROP_FPS, self.fps)
            
            if self.cap.isOpened():
                self.log.info(f"✓ Camera initialized")
            else:
                self.log.error("✗ Camera failed to open")
                self.cap = None
        except Exception as e:
            self.log.error(f"Camera error: {e}")
            self.cap = None
    
    def start(self):
        """Start vision processing."""
        if self.running or not self.cap:
            return
        
        self.running = True
        self._thread = threading.Thread(target=self._process_loop, daemon=True)
        self._thread.start()
        self.log.info("Vision processing started")
    
    def stop(self):
        """Stop vision processing."""
        self.running = False
        
        if self._thread:
            self._thread.join(timeout=1)
        
        if self.cap:
            self.cap.release()
        
        self.log.info("Vision stopped")
    
    def _process_loop(self):
        """Main processing loop with frame skipping."""
        while self.running and self.cap:
            ret, frame = self.cap.read()
            if not ret:
                continue
            
            # Skip frames for performance
            self.frame_count += 1
            if self.frame_count % self.frame_skip != 0:
                continue
            
            # Process frame
            processed = self._detect_objects(frame)
            
            with self._lock:
                self.current_frame = processed
    
    def _detect_objects(self, frame) -> dict:
        """Detect faces and poses."""
        results = {
            "faces": [],
            "poses": [],
            "frame": frame
        }
        
        # Face detection (fast cascade)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, 1.3, 5)
        results["faces"] = [{"x": x, "y": y, "w": w, "h": h} for x, y, w, h in faces]
        
        # Pose detection (if available)
        if self.pose_detector:
            try:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pose_results = self.pose_detector.process(rgb_frame)
                if pose_results.pose_landmarks:
                    results["poses"] = pose_results.pose_landmarks
            except:
                pass
        
        return results
    
    def get_frame(self) -> Optional[dict]:
        """Get current processed frame."""
        with self._lock:
            return self.current_frame
    
    def detect_face(self) -> Tuple[bool, Optional[dict]]:
        """Check if face detected."""
        frame = self.get_frame()
        if frame and frame.get("faces"):
            return True, frame["faces"][0]
        return False, None
