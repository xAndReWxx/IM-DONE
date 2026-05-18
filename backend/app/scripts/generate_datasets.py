"""
============================================================
PhysioAI Pro V2 - Generate Exercise Datasets CLI
============================================================
USAGE
    cd backend
    python -m app.scripts.generate_datasets

    Or:
    python app/scripts/generate_datasets.py

WHAT IT DOES
    1. Scans exercise_videos/ for .mp4, .mov, .avi files
    2. For each video:
       a. Processes frames through MediaPipe Pose
       b. Normalizes landmarks (hip-centered, torso-scaled)
       c. Extracts 15+ joint angles per frame
       d. Detects movement phases automatically
       e. Generates AI motion templates
       f. Exports structured JSON dataset
       g. Exports compact NPZ binary

OUTPUT
    exercise_datasets/{exercise_id}.json  — full structured dataset
    exercise_datasets/{exercise_id}.npz   — compact binary
    exercise_videos/datasets/{exercise_id}.npz + .json — motion template
============================================================
"""

import sys
import time
from pathlib import Path

# Ensure the backend root is on sys.path.
backend_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(backend_root))


def main():
    from app.services.exercise_engine.dataset_generator import (
        generate_all_datasets,
    )
    from app.services.exercise_engine.video_processor import discover_videos

    videos_dir = backend_root / "exercise_videos"
    output_dir = backend_root / "exercise_datasets"

    print("=" * 60)
    print("  PhysioAI Pro V2 — Exercise Dataset Generator")
    print("=" * 60)
    print()

    if not videos_dir.exists():
        print(f"[ERROR] Videos directory not found: {videos_dir}")
        sys.exit(1)

    video_files = discover_videos(videos_dir)
    if not video_files:
        print(f"[INFO] No video files found in {videos_dir}")
        print("[HINT] Add exercise videos (.mp4, .mov, .avi) to:")
        print(f"       {videos_dir}")
        print()
        print("[HINT] Supported folder structure:")
        print("       exercise_videos/")
        print("       ├── t_fly/")
        print("       │   └── T-Fly.mp4")
        print("       ├── shoulder_release/")
        print("       │   └── shoulder_release.mp4")
        print("       └── chin_tuck.mp4")
        sys.exit(0)

    print(f"[SCAN] Found {len(video_files)} video(s):")
    for vf in video_files:
        size_mb = vf.stat().st_size / (1024 * 1024)
        exercise_id = vf.parent.name if vf.parent.name != "exercise_videos" else vf.stem
        print(f"       > {exercise_id}: {vf.name} ({size_mb:.2f} MB)")
    print()

    # ── Run the pipeline ──
    start = time.monotonic()
    results = generate_all_datasets(
        videos_dir=videos_dir,
        output_dir=output_dir,
    )
    elapsed = time.monotonic() - start

    # ── Report ──
    print()
    print("=" * 60)
    print("  RESULTS")
    print("=" * 60)

    for r in results:
        status = "[OK] SUCCESS" if r.success else "[!!] FAILED"
        print(f"\n  {status}: {r.exercise_id}")
        if r.success:
            print(f"    Frames:  {r.frame_count}")
            print(f"    Reps:    {r.rep_count}")
            print(f"    Failed:  {r.failed_frames} frames")
            print(f"    Time:    {r.processing_time:.2f}s")
            if r.json_path:
                size_kb = r.json_path.stat().st_size / 1024
                print(f"    JSON:    {r.json_path.name} ({size_kb:.1f} KB)")
            if r.npz_path:
                size_kb = r.npz_path.stat().st_size / 1024
                print(f"    NPZ:     {r.npz_path.name} ({size_kb:.1f} KB)")
            if r.template:
                print(f"    Template: GENERATED")
            else:
                print(f"    Template: SKIPPED (no reps detected)")
        else:
            print(f"    Error: {r.error}")

    # Summary.
    succeeded = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)

    print()
    print("-" * 60)
    print(f"  Total: {len(results)} videos | {succeeded} succeeded | {failed} failed")
    print(f"  Time:  {elapsed:.2f}s")
    print(f"  Output: {output_dir}")
    print("-" * 60)
    print()


if __name__ == "__main__":
    main()
