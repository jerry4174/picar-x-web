'''
****************** Functionality ************************

Function	                    Status
----------------------------------------
Proportional joystick            	✅
Progressive speed curve	            ✅
Smooth driving without false stops	✅
Forward / reverse	                ✅
Steering	                        ✅
Ultrasonic emergency stop	        ✅
Reverse escape	                    ✅
STOP button	                        ✅
Cliff detection	                    ✅ 
Battery check                       ✅
warning beep with 3 Wave's          ✅
*****************************************************************

'''


import warnings
from robot_hat import utils
from flask import Flask, render_template, jsonify, request, Response
from picarx import Picarx
from picamera2 import Picamera2
import threading
import time
import cv2
from picarx.music import Music
import os
import subprocess
import numpy as np
import socket

# Set global socket timeout to prevent zombie connections from hanging Flask
# socket.setdefaulttimeout(10)

# Set ALSA sound hardware volume to maximum 0dB gain
os.system('amixer -c sndrpihifiberry sset "robot-hat speaker" 100% > /dev/null 2>&1')

# Create the music instance
music = Music()

app = Flask(__name__)
CRITICAL_VOLTAGE = 7.15
MOTION_THRESHOLD = 500000  # Adjust sensitivity based on room lighting/distance
COOLDOWN_SECONDS = 5       # Minimum time between motion alerts

motion_detection_enabled = False

prev_gray = None
last_alert_time = 0

# Use absolute path to ensure root/sudo can open the file cleanly
SOUND_START = '/home/jiri/picar-x/sounds/start.wav'
SOUND_CLIFF = '/home/jiri/picar-x/sounds/cliff.wav'
SOUND_OBSTACLE = '/home/jiri/picar-x/sounds/obstacle.wav'
SOUND_DOG = '/home/jiri/picar-x/sounds/dog.wav'


# =====================================================
# PiCar-X
# =====================================================

px = Picarx()

speed = 40


lock = threading.Lock()

# =====================================================
# Safety
# =====================================================

SAFETY_DISTANCE = 20.0
REQUIRED_READINGS = 2

danger_count = 0

obstacle_stop = False
cliff_stop = False

# Current motor state:
# "stopped", "forward", "backward"
motion_state = "stopped"

# =====================================================
# The DOG Motion
# =====================================================

def process_motion(frame):
    global prev_gray, last_alert_time, motion_detection_enabled

    # Ignore motion processing completely if disabled
    if not motion_detection_enabled:
        prev_gray = None  # Reset frame history while off
        return False

    # Convert Picamera RGB/BGR array to grayscale & blur
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (21, 21), 0)

    if prev_gray is None:
        prev_gray = gray
        return False

    frame_diff = cv2.absdiff(prev_gray, gray)
    thresh = cv2.threshold(frame_diff, 25, 255, cv2.THRESH_BINARY)[1]

    motion_score = np.sum(thresh)
    prev_gray = gray

    current_time = time.time()
    if motion_score > MOTION_THRESHOLD:
        if (current_time - last_alert_time) > COOLDOWN_SECONDS:
            print(f">>> DOG MOVED! Score: {motion_score} <<<", flush=True)
            play_warning_beep(SOUND_DOG)
            last_alert_time = current_time
            return True

    return False


# =====================================================
# Sounds
# =====================================================

def play_warning_beep(sound):
    """Fires native aplay in an independent OS process (guaranteed sound)."""
    try:
        subprocess.Popen(
            ['aplay', '-D', 'robothat', sound],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception as e:
        print(f"APLAY EXECUTION ERROR: {e}")


# =====================================================
# Camera servo angles
# =====================================================

cam_pan_angle = 0
cam_tilt_angle = 0


def set_cam_pan(angle):

    global cam_pan_angle

    cam_pan_angle = max(-30, min(30, angle))

    with lock:
        px.set_cam_pan_angle(cam_pan_angle)


def set_cam_tilt(angle):

    global cam_tilt_angle

    cam_tilt_angle = max(-30, min(30, angle))

    with lock:
        px.set_cam_tilt_angle(cam_tilt_angle)


# =====================================================
# Motor control
# =====================================================

def stop():

    global motion_state

    with lock:
        px.stop()
        motion_state = "stopped"

def forward(value):

    global motion_state

    with lock:

        # Safety systems can block forward motion.
        if obstacle_stop or cliff_stop:
            return False

        px.forward(value)
        motion_state = "forward"

    return True


def backward(value):

    global motion_state

    with lock:

        # Reverse is always allowed.
        # This lets the car escape from an obstacle or cliff.
        px.backward(value)
        motion_state = "backward"

    return True


def steering(angle):

    with lock:
        px.set_dir_servo_angle(angle)


# =====================================================
# Ultrasonic safety watchdog
# =====================================================

def ultrasonic_watchdog():

    global danger_count
    global obstacle_stop

    print("")
    print("Ultrasonic safety watchdog started")
    print(f"Safety distance: {SAFETY_DISTANCE:.1f} cm")
    print("")

    while True:

        try:

            distance = px.get_distance()

            # Ignore invalid readings
            if (
                distance is None
                or distance <= 0
                or distance > 300
            ):

                danger_count = 0

                time.sleep(0.1)
                continue

            # Obstacle too close
            if distance <= SAFETY_DISTANCE:

                danger_count += 1

                if danger_count >= REQUIRED_READINGS:

                    with lock:

                        if not obstacle_stop:

                            obstacle_stop = True
                            print("")
                            print("================================")
                            print(">>> EMERGENCY STOP <<<")
                            play_warning_beep(SOUND_OBSTACLE)
                            print(
                                f"Obstacle distance: "
                                f"{distance:.1f} cm"
                            )
                            print("================================")
                            print("")

            else:

                danger_count = 0

                if obstacle_stop:

                    with lock:

                        obstacle_stop = False

                    print(
                        f"Safety reset - distance: "
                        f"{distance:.1f} cm"
                    )

            time.sleep(0.1)

        except Exception as e:

            print("Ultrasonic error:", e)

            time.sleep(0.5)


# =====================================================
# Cliff safety watchdog
# =====================================================

def cliff_watchdog():
    global cliff_stop

    px.set_cliff_reference([200, 200, 200])

    print("")
    print("Cliff safety watchdog started")
    print("")

    last_state = "safe"
    cliff_count = 0
    total_cliff = 0

    while True:
        try:
            gm_val_list = px.get_grayscale_data()
            total_cliff = sum(gm_val_list)

            # Total 3 sensors < 100  = immediate stop (cliff)
            if total_cliff < 100:
                total_cliff = sum(gm_val_list)
                print("")
                print("Total sensors: ", total_cliff)
                print("")

                with lock:
                    cliff_stop = True
                    px.backward(80)
                    time.sleep(0.5)
                    px.forward(0)
                    play_warning_beep(SOUND_CLIFF)

                if last_state == "safe":
                    print("")
                    print("================================")
                    print(">>> CLIFF DETECTED <<<")
                    print(f"Sensor values: {gm_val_list}")
                    print("================================")
                    print()
                    print("")
                    last_state = "danger"

            else:
                if last_state == "danger":
                    with lock:
                        cliff_stop = False

                    print(f"Cliff cleared: {gm_val_list}")
                    last_state = "safe"

            time.sleep(0.1)

        except Exception as e:
            print("Cliff safety error:", e)

            with lock:
                cliff_stop = True

            time.sleep(0.5)




# =====================================================
# Central motor safety
# =====================================================

def motor_safety_watchdog():

    global motion_state

    print("")
    print("Central motor safety watchdog started")
    print("")

    while True:

        try:

            with lock:

                # Safety systems stop FORWARD motion.
                # Reverse remains available so the car
                # can escape from danger.

                if motion_state == "forward":

                    if obstacle_stop or cliff_stop:

                        px.stop()
                        motion_state = "stopped"

            time.sleep(0.05)

        except Exception as e:

            print("Motor safety error:", e)

            with lock:

                px.stop()
                motion_state = "stopped"

            time.sleep(0.5)


# =====================================================
# Web page
# =====================================================

@app.route("/")
def index():

    return render_template("index.html")

# =====================================================
# Switch dog function
# =====================================================


@app.route('/toggle_motion', methods=['POST'])
def toggle_motion():
    global motion_detection_enabled
    data = request.get_json()
    motion_detection_enabled = data.get('enabled', False)
    status_str = "ENABLED" if motion_detection_enabled else "DISABLED"
    print(f"Motion Detection: {status_str}", flush=True)
    return jsonify({"success": True, "enabled": motion_detection_enabled})



# =====================================================
# Battery check
# =====================================================


@app.route('/api/battery')
def get_battery_status():
    voltage = utils.get_battery_voltage()

    # Evaluate safety conditions
    if voltage <= CRITICAL_VOLTAGE:
        status = "Critical (Charge Now!)"
        healthy = False
    else:
        status = "Healthy"
        healthy = True

    return jsonify({
        "voltage": round(voltage, 2),
        "status": status,
        "healthy": healthy
    })
# if __name__ == '__main__':
#    app.run(host='0.0.0.0', port=5000)


# =====================================================
# Camera Move
# =====================================================

@app.route("/camera_move", methods=["POST"])
def camera_move_command():

    data = request.get_json(silent=True) or {}

    if data.get("reset"):

        set_cam_pan(0)
        set_cam_tilt(0)

    else:

        pan_step = int(data.get("pan_step", 0))
        tilt_step = int(data.get("tilt_step", 0))

        set_cam_pan(cam_pan_angle + pan_step)
        set_cam_tilt(cam_tilt_angle + tilt_step)

    return jsonify(
        status="ok",
        pan=cam_pan_angle,
        tilt=cam_tilt_angle
    )


# =====================================================
# Drive
# =====================================================

@app.route("/drive", methods=["POST"])
def drive_command():

    data = request.get_json(silent=True) or {}

    throttle = float(
        data.get("throttle", 0)
    )

    throttle = max(-1.0, min(1.0, throttle))

    # Joystick near center
    if abs(throttle) < 0.08:

        stop()

        return jsonify(
            status="stopped"
        )
##################################
    throttle_abs = abs(throttle)

    # Progressive motor response
    motor_power = throttle_abs ** 1.7

    motor_speed = int(
        motor_power * speed
    )
###################################
    if motor_speed < 5:

        stop()

        return jsonify(
            status="stopped"
        )

    if throttle > 0:

        allowed = forward(motor_speed)

    else:

        allowed = backward(motor_speed)

    if not allowed:

        return jsonify(
            status="blocked",
            reason="safety"
        )

    return jsonify(
        status="drive",
        throttle=throttle,
        motor_speed=motor_speed
    )


# =====================================================
# Stop
# =====================================================

@app.route("/stop", methods=["POST"])
def stop_command():

    stop()

    return jsonify(
        status="stopped"
    )


# =====================================================
# Steering
# =====================================================

@app.route("/steer", methods=["POST"])
def steer_command():

    data = request.get_json(silent=True) or {}

    angle = float(
        data.get("angle", 0)
    )

    angle = max(
        -30,
        min(30, angle)
    )

    steering(angle)

    return jsonify(
        status="steering",
        angle=angle
    )


# =====================================================
# Speed
# =====================================================

@app.route("/speed", methods=["POST"])
def speed_command():

    global speed

    data = request.get_json(silent=True) or {}

    speed = int(
        data.get("speed", 40)
    )

    speed = max(
        0,
        min(100, speed)
    )

    return jsonify(
        status="speed",
        speed=speed
    )


# =====================================================
# Camera
# =====================================================

camera = Picamera2()

camera_config = camera.create_video_configuration(
    main={
        "size": (640, 480),
        "format": "RGB888"
    }
)

camera.configure(camera_config)

camera.start()

time.sleep(2)

def generate_frames():
    while True:
        frame = camera.capture_array()

        # 1. Process frame for motion detection before JPEG encoding
        process_motion(frame)

        # 2. Encode to JPEG for the web feed
        ret, jpeg = cv2.imencode(
            ".jpg",
            frame,
            [cv2.IMWRITE_JPEG_QUALITY, 75]
        )

        if not ret:
            continue

        # 3. Stream frame & catch client disconnect cleanly
        try:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + jpeg.tobytes()
                + b"\r\n"
            )
        except GeneratorExit:
            # Client closed tab or phone went to sleep; exit loop to free thread
            print("Client stream closed. Thread released.", flush=True)
            break

        time.sleep(0.03)

@app.route("/camera")
def camera_stream():

    return Response(
        generate_frames(),
        mimetype=(
            "multipart/x-mixed-replace; "
            "boundary=frame"
        )
    )


# =====================================================
# Main
# =====================================================

if __name__ == "__main__":

    watchdog = threading.Thread(
        target=ultrasonic_watchdog,
        daemon=True
    )

    cliff = threading.Thread(
        target=cliff_watchdog,
        daemon=True
    )

    safety = threading.Thread(
        target=motor_safety_watchdog,
        daemon=True
    )



    watchdog.start()
    cliff.start()
    safety.start()
    print("")
    print("================================")
    print(" PiCar-X Web Controller")
    print("================================")
    print("")
    print("Camera:  http://<Pi-IP>:5000/camera")
    print("Control: http://<Pi-IP>:5000")
    print("")
    print("Ultrasonic safety: ACTIVE")
    print("Cliff safety: ACTIVE")
    print(f"Safety distance: {SAFETY_DISTANCE} cm")
    print("")
    play_warning_beep(SOUND_START)

    if __name__ == '__main__':
        try:
            # Keep your existing runner call with threaded=True
            app.run(
                host="0.0.0.0",
                port=5000,
                threaded=True,
                use_reloader=False  # Prevents duplicate hardware initialization
            )
        except KeyboardInterrupt:
            print("\nShutdown signal received...")
        finally:
            print("")
            print("Stopping PiCar-X...")

            with lock:
                px.stop()

            camera.stop()
            px.close()

            print("PiCar-X stopped.")
