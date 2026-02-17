# 📊 Evaluation Strategy

## Purpose

Define measurable criteria to determine image quality improvement.

---

## Metrics

### 1. CLIP Alignment Score

Measures semantic similarity between:
- Prompt text
- Generated image

Implementation:
- Encode prompt using CLIP text encoder
- Encode image using CLIP image encoder
- Compute cosine similarity

Range: 0–1

---

### 2. Face Detection Confidence

Used when prompt implies human presence.

Implementation:
- Mediapipe face detection
- Confidence thresholding

Score scaled 0–1.

---

### 3. Sharpness Score

Detects blur and texture degradation.

Implementation:
- OpenCV Laplacian variance
- Normalized to 0–1

---

## Combined Quality Score

quality_score =
    w1 * alignment +
    w2 * face_score +
    w3 * sharpness

Weights configurable.

---

## Threshold Policy

If quality_score < threshold:
- Trigger adaptive regeneration

Default threshold: 0.65

---

## Limitations

- CLIP may misjudge creative styles.
- Sharpness does not measure composition.
- Face detection irrelevant for landscapes.

Future improvement:
- Learned distortion classifier.
