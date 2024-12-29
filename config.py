import cv2
from util import get_parking_spots_bboxes

# ----------------------
# Parking Detection Config
# ----------------------
mask_path = 'mask_1920_1080.png'
video_path = 'D:\\parkvision\\parking_1920_1080.mp4'

mask = cv2.imread(mask_path, 0)
cap = cv2.VideoCapture(video_path)
connected_components = cv2.connectedComponentsWithStats(mask, 4, cv2.CV_32S)
spots = get_parking_spots_bboxes(connected_components)

# Initialize spots_status
spots_status = [None for _ in spots]  # Define spots_status as a list of None values, one per spot
spot_numbers = [i for i in range(len(spots))]
diffs = [None for _ in spots]
previous_frame = None
frame_nmr = 0
step = 30
