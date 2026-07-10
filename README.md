#AI Virtual Mouse & Gesture Controller

An advanced, real-time AI-powered virtual mouse and gesture controller implemented in Python. By leveraging computer vision and machine learning (Google MediaPipe and OpenCV), this system detects hand landmarks via webcam and translates them into fluid mouse movements, clicks, scrolling, volume, and brightness adjustments.

---

## 🚀 Features

- **Smooth Cursor Movement:** Uses index and middle fingers in a V-gesture to move the cursor. The movement is stabilized using ratio-dampened interpolation to eliminate jitter.
- **Mouse Clicks:**
  - **Left Click:** Lift only the middle finger.
  - **Right Click:** Lift only the index finger.
  - **Double Click:** Keep index and middle fingers closed together.
- **Drag and Drop:** Form a fist to grab (click and hold) and move to drag; release the fist to drop.
- **System Control (Major Hand - Right Hand by default):**
  - **Volume & Brightness:** Perform a pinch gesture and slide up/down to adjust system volume, or slide left/right to adjust screen brightness.
- **Scroll Control (Minor Hand - Left Hand by default):**
  - **Vertical & Horizontal Scroll:** Perform a pinch gesture and slide up/down to scroll vertically, or slide left/right to scroll horizontally.
- **Visual Feedback:** Live webcam overlay tracking hand connections and landmark joints in real-time.
- **Automatic Asset Download:** Automatically downloads the pre-trained MediaPipe Hand Landmarker model on the first execution.

---

## 🛠️ Tech Stack & Dependencies

- **Language:** Python 3.8+
- **Computer Vision & ML:**
  - [OpenCV (opencv-python)](https://opencv.org/) - Camera input & UI overlay
  - [MediaPipe](https://google.github.io/mediapipe/) - Hand Landmark Detection
- **System Interactions:**
  - [PyAutoGUI](https://pyautogui.readthedocs.io/) - OS-level mouse and scroll simulation
  - [Pycaw](https://github.com/AndreMiras/pycaw) - Windows Audio Endpoint Control
  - [screen-brightness-control](https://github.com/capjamesg/screen-brightness-control) - Display brightness control
  - `ctypes` & `comtypes` - Direct Windows API integration for smoother cursor placement
