"""
HuskyLens 2 — UART example usage
=================================
Run:
    pip install pyserial
    python example_usage.py
"""

import time
from huskylens2 import (
    HuskyLens2,
    ALGORITHM_FACE_RECOGNITION,
    ALGORITHM_OBJECT_TRACKING,
    ALGORITHM_COLOR_RECOGNITION,
    ALGORITHM_LINE_TRACKING,
)

# ── Edit this to match your system ───────────────────────────────────────────
PORT = "/dev/cu.usbserial-0001"   # Linux / macOS: /dev/ttyUSB0, /dev/tty.usbserial-*
                         # Windows: "COM3", "COM4", etc.
# ─────────────────────────────────────────────────────────────────────────────


def demo_face_recognition(hl: HuskyLens2) -> None:
    print("\n── Face Recognition ──────────────────────────────────")
    hl.set_algorithm(ALGORITHM_FACE_RECOGNITION)
    time.sleep(0.3)

    for _ in range(10):
        blocks = hl.request_blocks()
        if blocks:
            for b in blocks:
                label = f"ID {b.id}" if b.id else "unknown"
                print(f"  Face [{label}]  center=({b.x},{b.y})  size={b.w}x{b.h}")
        else:
            print("  No faces detected.")
        time.sleep(0.5)


def demo_object_tracking(hl: HuskyLens2) -> None:
    print("\n── Object Tracking ───────────────────────────────────")
    hl.set_algorithm(ALGORITHM_OBJECT_TRACKING)
    time.sleep(0.3)

    for _ in range(10):
        blocks = hl.request_blocks()
        if blocks:
            for b in blocks:
                print(f"  Tracking ID {b.id}  {b}")
        else:
            print("  Nothing being tracked.")
        time.sleep(0.5)


def demo_line_tracking(hl: HuskyLens2) -> None:
    print("\n── Line Tracking ─────────────────────────────────────")
    hl.set_algorithm(ALGORITHM_LINE_TRACKING)
    time.sleep(0.3)

    for _ in range(10):
        arrows = hl.request_arrows()
        if arrows:
            for a in arrows:
                print(f"  {a}")
        else:
            print("  No line detected.")
        time.sleep(0.5)


def demo_color_recognition(hl: HuskyLens2) -> None:
    print("\n── Color Recognition ─────────────────────────────────")
    hl.set_algorithm(ALGORITHM_COLOR_RECOGNITION)
    time.sleep(0.3)

    for _ in range(10):
        blocks = hl.request_learned()
        learned_blocks, _ = blocks
        if learned_blocks:
            for b in learned_blocks:
                print(f"  Learned color ID {b.id}  {b}")
        else:
            print("  No learned colors detected.")
        time.sleep(0.5)


def main() -> None:
    print(f"Connecting to HuskyLens 2 on {PORT} @ 115200 …")

    with HuskyLens2(port=PORT, baudrate=115200) as hl:
        print("Connected!")

        # ── Uncomment the demos you want to run ──────────────────────────────
        demo_face_recognition(hl)
        # demo_object_tracking(hl)
        # demo_line_tracking(hl)
        # demo_color_recognition(hl)

        # ── Save / load model example ─────────────────────────────────────────
        # print("\nSaving model to slot 1 …", hl.save_model(1))
        # print("Loading model from slot 1 …", hl.load_model(1))

        # ── Custom name example ───────────────────────────────────────────────
        # hl.set_custom_name(1, "Alice")

    print("\nDone.")


if __name__ == "__main__":
    main()
