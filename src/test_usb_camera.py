import cv2
import sys

def test_webcam(camera_index=0):
    print(f"Attempting to open USB webcam at index {camera_index}...")
    
    # Standard OpenCV initialization for USB webcams
    cap = cv2.VideoCapture(camera_index)

    if not cap.isOpened():
        print(f"\n[ERROR] Could not open camera at index {camera_index}.")
        print("Raspberry Pi 5 often assigns USB cameras to index 1, 2, or 3.")
        print("Edit the bottom of this script to change the index and try again.")
        sys.exit(1)

    print("\n[SUCCESS] Camera opened!")
    print("Make sure you click on the video window first, then press 'q' to quit.")

    while True:
        # Capture frame-by-frame
        ret, frame = cap.read()

        if not ret or frame is None:
            print("\n[ERROR] Camera opened, but failed to grab a frame.")
            break

        # Display the frame on your monitor
        cv2.imshow('USB Webcam Test', frame)

        # Wait for 1ms, check if 'q' is pressed
        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("\nQuitting...")
            break

    # Clean up
    cap.release()
    cv2.destroyAllWindows()

if __name__ == '__main__':
    # CHANGE THIS NUMBER if index 0 fails (try 1, 2, or 3)
    test_webcam(1)