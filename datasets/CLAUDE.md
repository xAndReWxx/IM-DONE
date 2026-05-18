# `datasets/` — CLAUDE.md

Drop the training CSVs here if you want to keep them in-repo:

- `dataset_all_points.csv` — 2,700 snapshots × 33 MediaPipe
  landmarks (x, y, z, visibility), labeled with the user's
  position class (`rest`, `biceps`, `shoulders`, `triceps`).
- `data.csv` — 45,000 rows of `angle_y`, `angle_z`, `emg`,
  `posture`, `recommendation`.

These were used to derive
`ai-engine/reference/good_posture_reference.json` (and its
mirror at `backend/app/reference/`), which is what the posture
analyzer reads at runtime.

If you re-generate the reference JSON (e.g. with new data),
remember to copy the result into the backend so it takes effect:

```bash
cp ai-engine/reference/good_posture_reference.json \
   backend/app/reference/good_posture_reference.json
```

The folder is empty by default so the repo stays light.
