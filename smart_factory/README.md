# Smart Factory Vision Inspection System

A beginner-friendly Industry 4.0 college project prototype. It combines browser-webcam bottle inspection with simulated machine monitoring and a manager decision brief. It explains what happened, the possible cause, predicted impact, and recommended response.

Features include repeated webcam inspection, clean-product calibration, bottle contour detection, dark-mark detection, annotated defect output, GOOD/DEFECTIVE/NO BOTTLE results, accurate inspection history, NORMAL/WARNING/CRITICAL machine simulation, temperature/vibration/pressure/health cards, predictive maintenance status, machine history, production incident analysis for M04, and interactive response scenarios A/B/C.

## Project structure

```text
smart_factory/
├── app.py
├── requirements.txt
├── README.md
├── templates/
│   └── index.html
└── static/
    ├── style.css
    └── script.js
```

## Install on Windows

Open a terminal in the `smart_factory` folder:

```powershell
python -m venv venv
venv\Scripts\activate
python -m pip install -r requirements.txt
```

If Windows uses the Microsoft Store alias for `python`, install Python from python.org or use the Python launcher installed on your machine.

## Run

```powershell
python app.py
```

Open:

```text
http://127.0.0.1:5000/
```

Allow camera permission when prompted. The `/inspect` endpoint accepts a JSON body with an image data URL, `/calibrate` stores a clean-bottle baseline, `/simulate` returns machine state, `/incident` returns the synthetic 10,000-to-8,000-unit incident, and `/reset` clears the in-memory statistics and history.

## Demonstration

1. Place a clean plastic bottle upright in the center of the camera frame with even lighting.
2. Click **Start camera**, place a clean upright bottle inside the frame, and click **Calibrate good product**.
3. Click **Capture & inspect** as many times as needed. The result should be `GOOD PRODUCT`.
4. Put a large black tape mark or dark sticker on the bottle surface.
5. Capture again repeatedly. OpenCV should return `DEFECTIVE PRODUCT`, annotate the mark, and recommend sending the product for rework.
6. Click **Run factory incident** to show the manager flow and compare scenarios A, B, and C. Scenario C shifts 30% of work to M02 and performs M04 maintenance.
7. Use **Normal**, **Warning**, and **Critical** to demonstrate predictive maintenance.
8. Use **Reset statistics** before a fresh presentation.

The detection constants `DARK_PIXEL_THRESHOLD` and `ABNORMAL_AREA_THRESHOLD` are near the top of `app.py` so they can be tuned for the room lighting and bottle used in the demonstration.

This is a prototype vision inspection using computer vision. It does not detect every real-world manufacturing defect and its confidence is an estimated demo score, not scientifically validated AI confidence.
