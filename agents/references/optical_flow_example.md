# Lucas-Kanade Optical Flow Mission Reference

This reference shows how generated missions may perform sparse Lucas-Kanade optical flow using captured image files.

It is an implementation reference, not a complete mission.

## Required libraries

```python
import cv2
import numpy as np
```

## Capturing and loading an image

The CubeSat SDK returns a file path.

```python
capture = sat.camera.capture()
image_path = capture["path"]

frame = cv2.imread(image_path)
```

Always check that the image loaded successfully:

```python
if frame is None:
    raise RuntimeError(
        f"Could not load captured image: {image_path}"
    )
```

Convert the image to grayscale:

```python
gray_frame = cv2.cvtColor(
    frame,
    cv2.COLOR_BGR2GRAY,
)
```

## Selecting trackable points

Use Shi-Tomasi corner detection:

```python
feature_params = {
    "maxCorners": 100,
    "qualityLevel": 0.3,
    "minDistance": 7,
    "blockSize": 7,
}

previous_points = cv2.goodFeaturesToTrack(
    previous_gray,
    mask=None,
    **feature_params,
)
```

If no features are found, skip that frame pair or create an unchanged visualization.

Do not call Lucas-Kanade with `None` points.

## Calculating Lucas-Kanade flow

```python
lk_params = {
    "winSize": (15, 15),
    "maxLevel": 2,
    "criteria": (
        cv2.TERM_CRITERIA_EPS
        | cv2.TERM_CRITERIA_COUNT,
        10,
        0.03,
    ),
}
```

Calculate the next point locations:

```python
next_points, status, error = (
    cv2.calcOpticalFlowPyrLK(
        previous_gray,
        current_gray,
        previous_points,
        None,
        **lk_params,
    )
)
```

Check the returned values:

```python
if next_points is None or status is None:
    return current_frame.copy()
```

Keep only successfully tracked points:

```python
good_new = next_points[
    status.flatten() == 1
]

good_old = previous_points[
    status.flatten() == 1
]
```

## Drawing the flow visualization

```python
visualization = current_frame.copy()
```

Draw a line from each old point to its new point:

```python
for new_point, old_point in zip(
    good_new,
    good_old,
):
    new_x, new_y = new_point.ravel()
    old_x, old_y = old_point.ravel()

    cv2.line(
        visualization,
        (int(old_x), int(old_y)),
        (int(new_x), int(new_y)),
        (0, 255, 0),
        2,
    )

    cv2.circle(
        visualization,
        (int(new_x), int(new_y)),
        3,
        (0, 0, 255),
        -1,
    )
```

## Saving an optical-flow image

Create an output directory owned by the mission:

```python
output_directory = Path(
    "outputs/optical-flow"
)

output_directory.mkdir(
    parents=True,
    exist_ok=True,
)
```

Save the visualization:

```python
output_path = (
    output_directory
    / f"flow_{flow_index:03d}.jpg"
)

saved = cv2.imwrite(
    str(output_path),
    visualization,
)

if not saved:
    raise RuntimeError(
        f"Could not save optical-flow image: "
        f"{output_path}"
    )
```

## Processing frames in groups of five

Twenty captured images create four groups:

```text
frames 0–4
frames 5–9
frames 10–14
frames 15–19
```

Each group of five contains four consecutive frame pairs:

```text
frame 0 → frame 1
frame 1 → frame 2
frame 2 → frame 3
frame 3 → frame 4
```

Therefore:

```text
4 groups × 4 comparisons = 16 flow images
```

Grouping helper:

```python
groups = [
    captured_frames[index:index + 5]
    for index in range(
        0,
        len(captured_frames),
        5,
    )
]
```

Process each group independently:

```python
flow_images = []

for group_index, group in enumerate(groups):
    for frame_index in range(
        len(group) - 1
    ):
        previous_frame = group[frame_index]
        current_frame = group[frame_index + 1]

        flow_image = calculate_flow(
            previous_frame,
            current_frame,
        )

        flow_images.append(flow_image)
```

## Important interpretation

“Optical flow images in groups of five” means:

1. Capture twenty images.
2. Split them into four groups of five frames.
3. Calculate flow between consecutive frames inside each group.
4. Produce sixteen optical-flow visualizations.

Do not replace optical flow with simple image grouping.

Do not return only the original images.

Do not claim optical flow was generated unless `cv2.calcOpticalFlowPyrLK()` or another explicitly requested optical-flow algorithm is actually used.
