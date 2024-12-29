from flask import Flask
from flask_pymongo import PyMongo
import cv2
from util import get_parking_spots_bboxes

app = Flask(__name__)
app.config['MONGO_URI'] = 'mongodb://localhost:27017/parkingdb'
mongo = PyMongo(app)

# Load the mask and spots
mask_path = 'mask_1920_1080.png'
mask = cv2.imread(mask_path, 0)
connected_components = cv2.connectedComponentsWithStats(mask, 4, cv2.CV_32S)
spots = get_parking_spots_bboxes(connected_components)

# Initialize Parking Slots
with app.app_context():
    for i in range(len(spots)):
        mongo.db.slots.update_one(
            {"slot_id": i},
            {"$setOnInsert": {"status": "free"}},
            upsert=True
        )
    print("Parking slots initialized successfully.")
