from datetime import datetime
import base64
import random
import threading

import cv2
import numpy as np
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# Easy-to-tune prototype thresholds for the classroom demonstration.
DARK_PIXEL_THRESHOLD = 62
ABNORMAL_AREA_THRESHOLD = 0.055
MIN_BOTTLE_AREA_RATIO = 0.035
MAX_BOTTLE_AREA_RATIO = 0.72
MAX_HISTORY_ITEMS = 12

stats = {"total": 0, "good": 0, "defective": 0}
history = []
machine_history = []
good_baseline = None
stats_lock = threading.Lock()

machine = {"temperature": 55.0, "vibration": 2.5, "pressure": 3.5}

incident_data = {
    "target": 10000,
    "output": 8000,
    "drop_percent": 20,
    "machine": "M04",
    "cause": "Possible M04 degradation",
    "evidence": ["Temperature increased 18%", "Vibration increased 24%", "Maintenance overdue by 14 days", "M04 downtime increased"],
    "failure_risk": 87,
    "downtime_hours": 11,
    "units_at_risk": 2150,
    "quality_signal": "Defect rate increasing to 4.8%",
    "recommendation": "Perform M04 maintenance and shift 30% of workload to M02",
    "why": "This gives the lowest expected production loss while reducing failure risk.",
}


def machine_state(values: dict) -> dict:
    """Convert simulated sensor values into status, health, and maintenance advice."""
    temperature, vibration, pressure = values["temperature"], values["vibration"], values["pressure"]
    critical = temperature > 85 or vibration > 7 or pressure > 7 or pressure < 2
    warning = temperature > 70 or vibration > 4 or pressure > 5
    status = "CRITICAL" if critical else "WARNING" if warning else "NORMAL"
    health = 94 if status == "NORMAL" else 72 if status == "WARNING" else 38
    maintenance = {"NORMAL": "MAINTENANCE NOT REQUIRED", "WARNING": "MAINTENANCE RECOMMENDED", "CRITICAL": "MAINTENANCE REQUIRED"}[status]
    explanation = {"NORMAL": "Machine operating within normal parameters.", "WARNING": "One or more sensor values need attention.", "CRITICAL": "Critical sensor condition detected. Immediate maintenance required."}[status]
    return {**values, "status": status, "health": health, "maintenance": maintenance, "explanation": explanation}


def record_machine(values: dict) -> dict:
    state = machine_state(values)
    with stats_lock:
        machine_history.insert(0, {"time": datetime.now().strftime("%H:%M:%S"), **state})
        del machine_history[MAX_HISTORY_ITEMS:]
    return state


def decode_image(image_data: str) -> np.ndarray | None:
    """Decode a browser data URL or raw base64 string into an OpenCV frame."""
    try:
        encoded = image_data.split(",", 1)[1] if "," in image_data else image_data
        image_bytes = base64.b64decode(encoded)
        frame = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        return frame
    except (ValueError, TypeError, base64.binascii.Error):
        return None


def encode_image(frame: np.ndarray) -> str:
    """Return a JPEG frame as a browser-friendly data URL."""
    success, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if not success:
        return ""
    return f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('ascii')}"


def find_bottle_mask(frame: np.ndarray) -> tuple[np.ndarray | None, tuple[int, int, int, int] | None]:
    """Find the largest centered, bottle-like foreground contour."""
    height, width = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (7, 7), 0)
    # Compare the center with the border background. This handles transparent or
    # low-contrast bottles better than edge-only detection.
    border_pixels = np.concatenate((blurred[:max(8, height // 12), :].ravel(), blurred[-max(8, height // 12):, :].ravel(), blurred[:, :max(8, width // 12)].ravel(), blurred[:, -max(8, width // 12):].ravel()))
    background_level = float(np.median(border_pixels))
    foreground = cv2.inRange(cv2.absdiff(blurred, np.full_like(blurred, background_level)), 18, 255)
    foreground = cv2.morphologyEx(foreground, cv2.MORPH_CLOSE, np.ones((11, 11), np.uint8))
    foreground = cv2.morphologyEx(foreground, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    foreground_contours, _ = cv2.findContours(foreground, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    edges = cv2.Canny(blurred, 35, 120)
    edges = cv2.dilate(edges, np.ones((5, 5), np.uint8), iterations=2)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    frame_area = height * width
    candidates = []
    for contour in foreground_contours:
        area = cv2.contourArea(contour)
        x, y, w, h = cv2.boundingRect(contour)
        ratio = area / frame_area
        center_distance = abs((x + w / 2) - width / 2) / width
        if MIN_BOTTLE_AREA_RATIO <= ratio <= MAX_BOTTLE_AREA_RATIO and h > w * 1.15 and center_distance < 0.30:
            candidates.append((area * (1 - center_distance), contour, (x, y, w, h)))
    if candidates:
        _, contour, box = max(candidates, key=lambda item: item[0])
        mask = np.zeros((height, width), dtype=np.uint8)
        cv2.drawContours(mask, [contour], -1, 255, -1)
        return mask, box
    candidates = []
    for contour in contours:
        area = cv2.contourArea(contour)
        x, y, w, h = cv2.boundingRect(contour)
        ratio = area / frame_area
        center_distance = abs((x + w / 2) - width / 2) / width
        if (MIN_BOTTLE_AREA_RATIO <= ratio <= MAX_BOTTLE_AREA_RATIO
                and h > w * 1.15 and center_distance < 0.30):
            score = area * (1 - center_distance)
            candidates.append((score, contour, (x, y, w, h)))
    if not candidates:
        return None, None
    _, contour, box = max(candidates, key=lambda item: item[0])
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.drawContours(mask, [contour], -1, 255, -1)
    return mask, box


def inspect_bottle(frame: np.ndarray, baseline: dict | None = None) -> dict:
    """Inspect a centered bottle using simple, explainable computer vision.

    The demo assumes the bottle is held near the center of the camera view.
    A real production system would use a calibrated camera and a trained model.
    """
    height, width = frame.shape[:2]
    bottle_mask, box = find_bottle_mask(frame)
    if bottle_mask is None or box is None:
        return {
            "status": "NO BOTTLE DETECTED", "good": False, "confidence": 96,
            "reason": "Place one upright bottle fully inside the inspection area.",
            "defect": "Product not found", "location": "None",
            "recommended_action": "Center the bottle and capture again",
            "abnormal_area_percent": 0, "image": encode_image(frame),
        }

    box_x, box_y, box_width, box_height = box
    roi = frame[box_y:box_y + box_height, box_x:box_x + box_width]
    roi_mask = bottle_mask[box_y:box_y + box_height, box_x:box_x + box_width]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (7, 7), 0)
    # Analyze only pixels inside the detected bottle contour, not the background.
    dark_mask = cv2.inRange(blurred, 0, DARK_PIXEL_THRESHOLD)
    dark_mask[roi_mask == 0] = 0
    kernel = np.ones((5, 5), np.uint8)
    dark_mask = cv2.morphologyEx(dark_mask, cv2.MORPH_OPEN, kernel)
    dark_mask = cv2.morphologyEx(dark_mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(dark_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    roi_area = max(cv2.countNonZero(roi_mask), 1)
    significant_regions = []
    abnormal_pixels = 0
    for contour in contours:
        area = cv2.contourArea(contour)
        if area > roi_area * 0.0007:
            significant_regions.append(contour)
            abnormal_pixels += int(area)

    abnormal_ratio = abnormal_pixels / roi_area
    baseline_ratio = baseline.get("dark_ratio", 0) if baseline else 0
    is_defective = abnormal_ratio > max(ABNORMAL_AREA_THRESHOLD, baseline_ratio + 0.025)
    status = "DEFECTIVE PRODUCT" if is_defective else "GOOD PRODUCT"
    reason = "Visible surface abnormality detected inside the bottle contour." if is_defective else "Bottle contour found; no significant surface defect detected."
    defect = "Dark surface mark / abnormal region" if is_defective else "None detected"
    confidence = int(np.clip(84 + abnormal_ratio * 180 if is_defective else 96 - abnormal_ratio * 80, 70, 99))
    action = "Send for rework" if is_defective else "Release product"

    annotated = roi.copy()
    for contour in significant_regions:
        defect_x, defect_y, defect_width, defect_height = cv2.boundingRect(contour)
        cv2.rectangle(annotated, (defect_x, defect_y), (defect_x + defect_width, defect_y + defect_height), (40, 40, 220), 3)
    frame[box_y:box_y + box_height, box_x:box_x + box_width] = annotated
    cv2.rectangle(frame, (box_x, box_y), (box_x + box_width, box_y + box_height), (40, 150, 80), 2)

    return {
        "status": status,
        "good": status == "GOOD PRODUCT",
        "confidence": confidence,
        "reason": reason,
        "defect": defect,
        "location": "Center inspection region" if significant_regions else "None",
        "recommended_action": action,
        "abnormal_area_percent": round(abnormal_ratio * 100, 2),
        "image": encode_image(frame),
    }


def calibrate_bottle(frame: np.ndarray) -> dict:
    """Store the clean bottle's dark-pixel ratio as a personal baseline."""
    global good_baseline
    bottle_mask, box = find_bottle_mask(frame)
    if bottle_mask is None or box is None:
        return {"success": False, "message": "No bottle detected. Center a clean bottle first."}
    x, y, w, h = box
    roi = frame[y:y + h, x:x + w]
    mask = bottle_mask[y:y + h, x:x + w]
    gray = cv2.GaussianBlur(cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY), (7, 7), 0)
    dark = cv2.inRange(gray, 0, DARK_PIXEL_THRESHOLD)
    dark[mask == 0] = 0
    good_baseline = {"dark_ratio": cv2.countNonZero(dark) / max(cv2.countNonZero(mask), 1), "time": datetime.now().strftime("%H:%M:%S")}
    return {"success": True, "message": "Good product baseline calibrated.", "baseline": good_baseline}


def record_result(result: dict) -> None:
    with stats_lock:
        stats["total"] += 1
        stats["good" if result["good"] else "defective"] += 1
        history.insert(0, {
            "time": datetime.now().strftime("%H:%M:%S"),
            "status": result["status"],
            "confidence": result["confidence"],
            "defect": result["defect"],
        })
        del history[MAX_HISTORY_ITEMS:]


@app.get("/")
def dashboard():
    return render_template("index.html")


@app.post("/inspect")
def inspect():
    payload = request.get_json(silent=True) or {}
    image_data = payload.get("image", "")
    if not image_data:
        return jsonify({"error": "No camera image was received."}), 400

    frame = decode_image(image_data)
    if frame is None:
        return jsonify({"error": "The captured image could not be decoded."}), 400

    result = inspect_bottle(frame, good_baseline)
    if result["status"] != "NO BOTTLE DETECTED":
        record_result(result)
    return jsonify({**result, "stats": stats, "history": history})


@app.post("/calibrate")
def calibrate():
    payload = request.get_json(silent=True) or {}
    frame = decode_image(payload.get("image", ""))
    if frame is None:
        return jsonify({"success": False, "message": "No valid camera image was received."}), 400
    return jsonify(calibrate_bottle(frame))


@app.post("/simulate")
def simulate():
    mode = (request.get_json(silent=True) or {}).get("mode", "random")
    if mode == "normal":
        values = {"temperature": round(random.uniform(48, 66), 1), "vibration": round(random.uniform(1.2, 3.6), 1), "pressure": round(random.uniform(2.5, 4.6), 1)}
    elif mode == "warning":
        values = {"temperature": round(random.uniform(72, 83), 1), "vibration": round(random.uniform(4.3, 6.5), 1), "pressure": round(random.uniform(5.2, 6.6), 1)}
    elif mode == "critical":
        values = {"temperature": round(random.uniform(87, 96), 1), "vibration": round(random.uniform(7.4, 9.8), 1), "pressure": round(random.uniform(7.2, 9.2), 1)}
    else:
        mode = random.choice(["normal", "warning", "critical"])
        return simulate_with_mode(mode)
    machine.update(values)
    state = record_machine(machine)
    return jsonify({"mode": mode, "machine": state, "history": machine_history})


def simulate_with_mode(mode: str):
    with app.test_request_context(json={"mode": mode}):
        return simulate()


@app.get("/stats")
def get_stats():
    with stats_lock:
        return jsonify({"stats": stats, "history": history})


@app.get("/incident")
def incident():
    """Return the synthetic disruption story for a reliable manager demo."""
    return jsonify({
        "incident": incident_data,
        "scenarios": [
            {"id": "A", "name": "Do nothing", "loss": 2150, "risk": "87% failure risk remains"},
            {"id": "B", "name": "Stop M04 immediately", "loss": 1800, "risk": "Risk contained, high downtime"},
            {"id": "C", "name": "Shift 30% + maintain M04", "loss": 650, "risk": "Risk reduced, lowest loss", "recommended": True},
        ],
    })


@app.post("/reset")
def reset():
    with stats_lock:
        stats.update(total=0, good=0, defective=0)
        history.clear()
        machine_history.clear()
        global good_baseline
        good_baseline = None
    return jsonify({"message": "Inspection statistics reset.", "stats": stats, "history": history, "machine_history": machine_history})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
