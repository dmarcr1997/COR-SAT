Extract camera-mission requirements from the user's request. Return only one JSON
object with exactly these fields:

{
  "capture_count": positive integer,
  "interval_seconds": positive number,
  "heartbeat_each_capture": boolean,
  "optical_flow_groups": non-negative integer,
  "optical_flow_outputs": non-negative integer,
  "require_shutdown_handling": boolean
}

Set both optical-flow values to zero unless sparse Lucas-Kanade optical flow is
requested. For optical flow, use the requested number of frame groups and JPEG
visualizations. Current hardware support is limited to camera capture; do not
invent communications, IMU, or actuator requirements.
