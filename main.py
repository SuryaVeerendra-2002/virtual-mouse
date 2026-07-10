
import ctypes
import os
import sys

# Monkeypatch ctypes.CDLL to handle 'free' attribute on Windows before importing mediapipe
if os.name == 'nt':
    original_CDLL = ctypes.CDLL
    class PatchedCDLL(original_CDLL):
        def __getattr__(self, name):
            try:
                return super().__getattr__(name)
            except AttributeError as e:
                if name == 'free':
                    return ctypes.CDLL('msvcrt').free
                raise e
    ctypes.CDLL = PatchedCDLL

import cv2
import mediapipe as mp
import pyautogui
import math
from enum import IntEnum
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
import screen_brightness_control as sbcontrol
import urllib.request
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

pyautogui.FAILSAFE = False

# Gesture Encodings 
class Gest(IntEnum):
    # Binary Encoded
    FIST = 0
    PINKY = 1
    RING = 2
    MID = 4
    LAST3 = 7
    INDEX = 8
    FIRST2 = 12
    LAST4 = 15
    THUMB = 16    
    PALM = 31
    
    # Extra Mappings
    V_GEST = 33
    TWO_FINGER_CLOSED = 34
    PINCH_MAJOR = 35
    PINCH_MINOR = 36

# Multi-handedness Labels
class HLabel(IntEnum):
    MINOR = 0
    MAJOR = 1

# Convert Mediapipe Landmarks to recognizable Gestures
class HandRecog:
    
    def __init__(self, hand_label):
        self.finger = 0
        self.ori_gesture = Gest.PALM
        self.prev_gesture = Gest.PALM
        self.frame_count = 0
        self.hand_result = None
        self.hand_label = hand_label
    
    def update_hand_result(self, hand_result):
        self.hand_result = hand_result

    def get_signed_dist(self, point):
        sign = -1
        if self.hand_result[point[0]].y < self.hand_result[point[1]].y:
            sign = 1
        dist = (self.hand_result[point[0]].x - self.hand_result[point[1]].x)**2
        dist += (self.hand_result[point[0]].y - self.hand_result[point[1]].y)**2
        dist = math.sqrt(dist)
        return dist*sign
    
    def get_dist(self, point):
        dist = (self.hand_result[point[0]].x - self.hand_result[point[1]].x)**2
        dist += (self.hand_result[point[0]].y - self.hand_result[point[1]].y)**2
        dist = math.sqrt(dist)
        return dist
    
    def get_dz(self, point):
        return abs(self.hand_result[point[0]].z - self.hand_result[point[1]].z)
    
    # Function to find Gesture Encoding using current finger_state.
    # Finger_state: 1 if finger is open, else 0
    def set_finger_state(self):
        if self.hand_result is None:
            return

        points = [[8,5,0],[12,9,0],[16,13,0],[20,17,0]]
        self.finger = 0
        self.finger = self.finger | 0 #thumb
        for idx, point in enumerate(points):
            
            dist = self.get_signed_dist(point[:2])
            dist2 = self.get_signed_dist(point[1:])
            
            try:
                ratio = round(dist/dist2,1)
            except:
                ratio = round(dist/0.01,1)

            self.finger = self.finger << 1
            if ratio > 0.5 :
                self.finger = self.finger | 1
    

    # Handling Fluctuations due to noise
    def get_gesture(self):
        if self.hand_result is None:
            return Gest.PALM

        current_gesture = Gest.PALM
        if self.finger in [Gest.LAST3, Gest.LAST4] and self.get_dist([8,4]) < 0.05:
            if self.hand_label == HLabel.MINOR :
                current_gesture = Gest.PINCH_MINOR
            else:
                current_gesture = Gest.PINCH_MAJOR

        elif Gest.FIRST2 == self.finger :
            point = [[8,12],[5,9]]
            dist1 = self.get_dist(point[0])
            dist2 = self.get_dist(point[1])
            ratio = dist1/dist2
            print(f"V-gesture calibration: finger distance ratio is {ratio:.2f} (target threshold is 1.3)", flush=True)
            if ratio > 1.3:
                current_gesture = Gest.V_GEST
            else:
                if self.get_dz([8,12]) < 0.1:
                    current_gesture =  Gest.TWO_FINGER_CLOSED
                else:
                    current_gesture =  Gest.MID
            
        else:
            current_gesture =  self.finger
        
        if current_gesture == self.prev_gesture:
            self.frame_count += 1
        else:
            self.frame_count = 0

        self.prev_gesture = current_gesture

        if self.frame_count > 4 :
            self.ori_gesture = current_gesture
        return self.ori_gesture

# Executes commands according to detected gestures
class Controller:
    tx_old = 0
    ty_old = 0
    trial = True
    flag = False
    grabflag = False
    pinchmajorflag = False
    pinchminorflag = False
    pinchstartxcoord = None
    pinchstartycoord = None
    pinchdirectionflag = None
    prevpinchlv = 0
    pinchlv = 0
    framecount = 0
    prev_hand = None
    pinch_threshold = 0.3
    
    def getpinchylv(hand_result):
        dist = round((Controller.pinchstartycoord - hand_result[8].y)*10,1)
        return dist

    def getpinchxlv(hand_result):
        dist = round((hand_result[8].x - Controller.pinchstartxcoord)*10,1)
        return dist
    
    def changesystembrightness():
        currentBrightnessLv = sbcontrol.get_brightness()/100.0
        currentBrightnessLv += Controller.pinchlv/50.0
        if currentBrightnessLv > 1.0:
            currentBrightnessLv = 1.0
        elif currentBrightnessLv < 0.0:
            currentBrightnessLv = 0.0       
        sbcontrol.fade_brightness(int(100*currentBrightnessLv) , start = sbcontrol.get_brightness())
    
    def changesystemvolume():
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        currentVolumeLv = volume.GetMasterVolumeLevelScalar()
        currentVolumeLv += Controller.pinchlv/50.0
        if currentVolumeLv > 1.0:
            currentVolumeLv = 1.0
        elif currentVolumeLv < 0.0:
            currentVolumeLv = 0.0
        volume.SetMasterVolumeLevelScalar(currentVolumeLv, None)
    
    def scrollVertical():
        pyautogui.scroll(120 if Controller.pinchlv>0.0 else -120)
        
    
    def scrollHorizontal():
        pyautogui.keyDown('shift')
        pyautogui.keyDown('ctrl')
        pyautogui.scroll(-120 if Controller.pinchlv>0.0 else 120)
        pyautogui.keyUp('ctrl')
        pyautogui.keyUp('shift')

    # Locate Hand to get Cursor Position
    # Stabilize cursor by Dampening
    def get_position(hand_result):
        point = 9
        position = [hand_result[point].x ,hand_result[point].y]
        sx,sy = pyautogui.size()
        x_old,y_old = pyautogui.position()
        x = int(position[0]*sx)
        y = int(position[1]*sy)
        if Controller.prev_hand is None:
            Controller.prev_hand = x,y
        delta_x = x - Controller.prev_hand[0]
        delta_y = y - Controller.prev_hand[1]

        distsq = delta_x**2 + delta_y**2
        ratio = 1
        Controller.prev_hand = [x,y]

        if distsq <= 25:
            ratio = 0
        elif distsq <= 900:
            ratio = 0.07 * (distsq ** (1/2))
        else:
            ratio = 2.1
        x , y = x_old + delta_x*ratio , y_old + delta_y*ratio
        return (x,y)

    def pinch_control_init(hand_result):
        Controller.pinchstartxcoord = hand_result[8].x
        Controller.pinchstartycoord = hand_result[8].y
        Controller.pinchlv = 0
        Controller.prevpinchlv = 0
        Controller.framecount = 0

    # Hold final position for 5 frames to change status
    def pinch_control(hand_result, controlHorizontal, controlVertical):
        if Controller.framecount == 5:
            Controller.framecount = 0
            Controller.pinchlv = Controller.prevpinchlv

            if Controller.pinchdirectionflag == True:
                controlHorizontal() #x

            elif Controller.pinchdirectionflag == False:
                controlVertical() #y

        lvx =  Controller.getpinchxlv(hand_result)
        lvy =  Controller.getpinchylv(hand_result)
            
        if abs(lvy) > abs(lvx) and abs(lvy) > Controller.pinch_threshold:
            Controller.pinchdirectionflag = False
            if abs(Controller.prevpinchlv - lvy) < Controller.pinch_threshold:
                Controller.framecount += 1
            else:
                Controller.prevpinchlv = lvy
                Controller.framecount = 0

        elif abs(lvx) > Controller.pinch_threshold:
            Controller.pinchdirectionflag = True
            if abs(Controller.prevpinchlv - lvx) < Controller.pinch_threshold:
                Controller.framecount += 1
            else:
                Controller.prevpinchlv = lvx
                Controller.framecount = 0

    def handle_controls(gesture, hand_result):        
        x,y = None,None
        if gesture != Gest.PALM :
            x,y = Controller.get_position(hand_result)
        
        # flag reset
        if gesture != Gest.FIST and Controller.grabflag:
            Controller.grabflag = False
            pyautogui.mouseUp(button = "left")

        if gesture != Gest.PINCH_MAJOR and Controller.pinchmajorflag:
            Controller.pinchmajorflag = False

        if gesture != Gest.PINCH_MINOR and Controller.pinchminorflag:
            Controller.pinchminorflag = False

        # implementation
        if gesture == Gest.V_GEST:
            Controller.flag = True
            print(f"Moving cursor to: ({int(x)}, {int(y)})", flush=True)
            try:
                import win32api
                win32api.SetCursorPos((int(x), int(y)))
            except:
                pyautogui.moveTo(x, y, duration = 0)

        elif gesture == Gest.FIST:
            if not Controller.grabflag : 
                Controller.grabflag = True
                pyautogui.mouseDown(button = "left")
            print(f"Dragging cursor to: ({int(x)}, {int(y)})", flush=True)
            try:
                import win32api
                win32api.SetCursorPos((int(x), int(y)))
            except:
                pyautogui.moveTo(x, y, duration = 0)

        elif gesture == Gest.MID and Controller.flag:
            pyautogui.click()
            Controller.flag = False

        elif gesture == Gest.INDEX and Controller.flag:
            pyautogui.click(button='right')
            Controller.flag = False

        elif gesture == Gest.TWO_FINGER_CLOSED and Controller.flag:
            pyautogui.doubleClick()
            Controller.flag = False

        elif gesture == Gest.PINCH_MINOR:
            if Controller.pinchminorflag == False:
                Controller.pinch_control_init(hand_result)
                Controller.pinchminorflag = True
            Controller.pinch_control(hand_result,Controller.scrollHorizontal, Controller.scrollVertical)
        
        elif gesture == Gest.PINCH_MAJOR:
            if Controller.pinchmajorflag == False:
                Controller.pinch_control_init(hand_result)
                Controller.pinchmajorflag = True
            Controller.pinch_control(hand_result,Controller.changesystembrightness, Controller.changesystemvolume)
        

def draw_landmarks(image, hand_landmarks):
    # Connections map for 21 hand landmarks:
    connections = [
        # Thumb
        (0, 1), (1, 2), (2, 3), (3, 4),
        # Index finger
        (0, 5), (5, 6), (6, 7), (7, 8),
        # Middle finger
        (9, 10), (10, 11), (11, 12),
        # Ring finger
        (13, 14), (14, 15), (15, 16),
        # Pinky
        (0, 17), (17, 18), (18, 19), (19, 20),
        # Knuckle connection
        (5, 9), (9, 13), (13, 17)
    ]
    h, w, _ = image.shape
    # Draw connections
    for start_idx, end_idx in connections:
        start_pt = hand_landmarks[start_idx]
        end_pt = hand_landmarks[end_idx]
        start_x, start_y = int(start_pt.x * w), int(start_pt.y * h)
        end_x, end_y = int(end_pt.x * w), int(end_pt.y * h)
        cv2.line(image, (start_x, start_y), (end_x, end_y), (0, 255, 0), 2)
    # Draw landmarks
    for pt in hand_landmarks:
        cx, cy = int(pt.x * w), int(pt.y * h)
        cv2.circle(image, (cx, cy), 5, (0, 0, 255), cv2.FILLED)


class GestureController:
    gc_mode = 0
    cap = None
    CAM_HEIGHT = None
    CAM_WIDTH = None
    hr_major = None # Right Hand by default
    hr_minor = None # Left hand by default
    dom_hand = True

    def __init__(self):
        GestureController.gc_mode = 1
        GestureController.cap = cv2.VideoCapture(0)
        GestureController.CAM_HEIGHT = GestureController.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        GestureController.CAM_WIDTH = GestureController.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    
    def classify_hands(results):
        left , right = None,None
        
        # results.handedness: list of list of Category
        # results.hand_landmarks: list of list of NormalizedLandmarks
        for idx, handedness_list in enumerate(results.handedness):
            hand_label = handedness_list[0].category_name
            print(f"Detected hand_label: '{hand_label}'", flush=True)
            landmarks = results.hand_landmarks[idx]
            
            if hand_label.lower() == 'right':
                right = landmarks
            else:
                left = landmarks
        
        if GestureController.dom_hand == True:
            GestureController.hr_major = right
            GestureController.hr_minor = left
        else :
            GestureController.hr_major = left
            GestureController.hr_minor = right

    def start(self):
        
        handmajor = HandRecog(HLabel.MAJOR)
        handminor = HandRecog(HLabel.MINOR)

        # Download model if not exists
        model_path = os.path.join(os.path.dirname(__file__), 'hand_landmarker.task')
        if not os.path.exists(model_path):
            print(f"Downloading hand landmarker model to {model_path}...")
            url = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
            urllib.request.urlretrieve(url, model_path)
            print("Download complete!")

        # Initialize detector
        base_options = python.BaseOptions(model_asset_path=model_path)
        options = vision.HandLandmarkerOptions(
            base_options=base_options,
            num_hands=2,
            min_hand_detection_confidence=0.5,
            min_hand_presence_confidence=0.5,
            min_tracking_confidence=0.5
        )
        detector = vision.HandLandmarker.create_from_options(options)

        while GestureController.cap.isOpened() and GestureController.gc_mode:
            success, image = GestureController.cap.read()

            if not success:
                print("Ignoring empty camera frame.")
                continue
            
            image = cv2.flip(image, 1)
            rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_image)
            
            results = detector.detect(mp_image)

            if results.hand_landmarks:                   
                GestureController.classify_hands(results)
                if len(results.hand_landmarks) == 1:
                    GestureController.hr_major = results.hand_landmarks[0]
                    GestureController.hr_minor = None
                handmajor.update_hand_result(GestureController.hr_major)
                handminor.update_hand_result(GestureController.hr_minor)

                handmajor.set_finger_state()
                handminor.set_finger_state()
                gest_name = handminor.get_gesture()

                if gest_name == Gest.PINCH_MINOR:
                    print(f"Minor Hand Gesture: PINCH_MINOR | finger: {handminor.finger}", flush=True)
                    Controller.handle_controls(gest_name, handminor.hand_result)
                else:
                    gest_name = handmajor.get_gesture()
                    if gest_name != Gest.PALM:
                        try:
                            gest_str = Gest(gest_name).name
                        except ValueError:
                            gest_str = f"UNKNOWN ({gest_name})"
                        print(f"Major Hand Gesture: {gest_str} | finger: {handmajor.finger}", flush=True)
                    Controller.handle_controls(gest_name, handmajor.hand_result)
                
                for hand_landmarks in results.hand_landmarks:
                    draw_landmarks(image, hand_landmarks)
            else:
                Controller.prev_hand = None
            cv2.imshow('Gesture Controller', image)
            if cv2.waitKey(5) & 0xFF == 13:
                break
        GestureController.cap.release()
        cv2.destroyAllWindows()

# uncomment to run directly
gc1 = GestureController()
gc1.start()