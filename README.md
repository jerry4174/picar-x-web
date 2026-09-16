# PiCar-X Flask Web Controller

A responsive, lightweight web dashboard for controlling the **SunFounder PiCar-X** (powered by a Raspberry Pi 3) in real-time. Built with **Python**, **Flask**, and **OpenCV**, this interface provides low-latency MJPEG video streaming, camera servo controls, and battery safety monitoring.

> *Note: Developed with architectural and design assistance from AI Gemini.*

---

## Key Features

- **Live Camera Feed:** Real-time MJPEG video stream processed with OpenCV.
- **Pan-Tilt Servos:** Independent web controls to adjust camera orientation.
- **Driving & Speed Controls:** Dynamic motor speed adjustments and direction control.
- **Dog Guard Mode:** Toggleable motion detection directly integrated into the video frame pipeline.
- **Battery & Safety Monitor:** Real-time voltage checks targeting 2S Li-ion setups ($7.15\text{V}$ critical threshold alert).
- **Graceful Threading:** Thread-safe streaming using `GeneratorExit` handlers to prevent server deadlocks upon client disconnect.

---

## Project Structure

```text
/home/picar-web/
├── app.py              # Main Flask application & motor/camera logic
├── start.sh            # Launch script
├── requirements.txt    # Python package dependencies
├── sounds/             # Audio alert assets
├── static/
│   └── style.css       # Custom Web UI layout & styling
└── templates/
    └── index.html      # Control panel dashboard interface

```

---

## Getting Started

### Prerequisites

* Raspberry Pi 3 running Linux (e.g., Ubuntu / Raspbian)
* SunFounder PiCar-X Robot Kit
* Python 3.x with `venv` module installed

### Installation

1. **Clone the repository:**
```bash
git clone [https://github.com/jerry4174/picar-x-web.git](https://github.com/jerry4174/picar-x-web.git)
cd picar-x-web

```


2. **Create and activate the virtual environment:**
```bash
python3 -m venv venv
source venv/bin/activate

```


3. **Install dependencies:**
```bash
pip install -r requirements.txt

```


4. **Make the launch script executable and run:**
```bash
chmod +x start.sh
./start.sh

```


5. Open your web browser and navigate to:
```text
http://<your-raspberry-pi-ip>:5000

```



---

## Hardware Notes & Power Management

* **Power Supply:** Operating on a 2S Li-ion battery configuration (nominal $7.4\text{V}$, max $8.4\text{V}$).
* **Under-Voltage Cutoff:** To protect cells against deep discharge, monitoring is configured with a threshold at **$7.15\text{V}$**.

---

## License

Distributed under the MIT License. Feel free to modify and share!



```
