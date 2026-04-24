# PixelForge Evaluation Strategy

This document defines how image quality is evaluated in PixelForge and how that score drives adaptive retries.

## 1. Evaluation Objective

Measure whether generated images are both:

- semantically aligned with prompt intent
- visually coherent and sharp enough for acceptance

## 2. Implemented Metrics

### CLIP Alignment Score

- Model: openai/clip-vit-base-patch32
- Method: cosine similarity between normalized text and image embeddings
- Output normalization: remap from [-1, 1] to [0, 1]

### Sharpness Score

- Method: OpenCV Laplacian variance on grayscale image
- Output normalization: capped into [0, 1]

### Face Score (Deferred)

- Current runtime value: 0.0 with default face weight 0.0
- Planned: add real face quality/confidence metric

## 3. Combined Score

```text
quality = (w_clip * clip + w_face * face + w_sharpness * sharpness) / total_weight
```

Current defaults in QualityEvaluator:

- w_clip = 0.5
- w_face = 0.0
- w_sharpness = 0.5

## 4. Threshold Policy

- App-level adaptive threshold default: 0.65
- Sampler-level class default: 0.80
- Effective threshold is what create_app passes to AdaptiveSampler (currently 0.65).

If score < threshold, retry logic adjusts parameters and regenerates.

## 5. Evaluation Artifacts

For each attempt, metadata stores:

- seed
- steps
- guidance scale
- width/height
- quality score
- generation time
- artifact key

## 6. Limitations

- CLIP can reward semantic alignment even when anatomy is imperfect.
- Sharpness cannot evaluate composition quality.
- Face-specific quality signal is not implemented yet.

## 7. Planned Enhancements

- Add optional face metric when w_face > 0.
- Add distortion classifier to better detect structural artifacts.
- Add offline benchmark prompt suites for regression scoring.
