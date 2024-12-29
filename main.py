from flask import Flask, render_template, Response, request, redirect, url_for, session, flash, jsonify
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, ValidationError
from flask_pymongo import PyMongo
import bcrypt
import cv2
import numpy as np
from util import get_parking_spots_bboxes, empty_or_not

# ----------------------
# App Initialization
# ----------------------
app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# Setup MongoDB URI
app.config["MONGO_URI"] = "mongodb://localhost:27017/your_database_name"
mongo = PyMongo(app)

# ----------------------
# Authentication Forms
# ----------------------
class RegisterForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired()])
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Register")

    def validate_email(self, field):
        user = mongo.db.users.find_one({"email": field.data})
        if user:
            raise ValidationError('Email Already Taken')

class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Login")

# ----------------------
# Parking Detection Config
# ----------------------
mask_path = r'D:\parkvision\parking-space-counter\mask_1920_1080.png'
video_path = r'DD:\parkvision\parking-space-counter\parking_1920_1080.mp4'

mask = cv2.imread(mask_path, 0)
cap = cv2.VideoCapture(video_path)
connected_components = cv2.connectedComponentsWithStats(mask, 4, cv2.CV_32S)
spots = get_parking_spots_bboxes(connected_components)
spot_numbers = [i for i in range(len(spots))]
spots_status = [None for _ in spots]
diffs = [None for _ in spots]
previous_frame = None
frame_nmr = 0
step = 30

# ----------------------
# Video Frame Generator
# ----------------------
def calc_diff(im1, im2):
    return np.abs(np.mean(im1) - np.mean(im2))

def generate_frames():
    global previous_frame, frame_nmr, spots_status
    while True:
        success, frame = cap.read()
        if not success:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # Restart video if end is reached
            continue

        if frame_nmr % step == 0:
            if previous_frame is not None:
                for spot_indx, spot in enumerate(spots):
                    x1, y1, w, h = spot
                    spot_crop = frame[y1:y1 + h, x1:x1 + w]
                    diffs[spot_indx] = calc_diff(spot_crop, previous_frame[y1:y1 + h, x1:x1 + w])

                for spot_indx in range(len(spots)):
                    x1, y1, w, h = spots[spot_indx]
                    spot_crop = frame[y1:y1 + h, x1:x1 + w]
                    spots_status[spot_indx] = empty_or_not(spot_crop)

        previous_frame = frame.copy()

        for spot_indx, (x1, y1, w, h) in enumerate(spots):
            spot_status = spots_status[spot_indx]
            color = (0, 255, 0) if spot_status else (0, 0, 255)
            cv2.rectangle(frame, (x1, y1), (x1 + w, y1 + h), color, 2)
            cv2.putText(frame, str(spot_numbers[spot_indx]), (x1, y1 + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        available_spots = sum(1 for status in spots_status if status)
        total_spots = len(spots_status)
        cv2.rectangle(frame, (80, 20), (550, 80), (0, 0, 0), -1)
        cv2.putText(frame, f'Available spots: {available_spots} / {total_spots}', (100, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

        _, buffer = cv2.imencode('.jpg', frame)
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

        frame_nmr += 1

# ----------------------
# Routes
# ----------------------
@app.route('/')
def home():
    return redirect(url_for('register'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        name = form.name.data
        email = form.email.data
        password = form.password.data
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

        mongo.db.users.insert_one({
            "name": name,
            "email": email,
            "password": hashed_password
        })

        session['user_id'] = email
        flash("Registration successful! Welcome to the system.", "success")
        return redirect(url_for('dashboard'))
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data
        password = form.password.data

        user = mongo.db.users.find_one({"email": email})

        if user and bcrypt.checkpw(password.encode('utf-8'), user["password"]):
            session['user_id'] = user["email"]
            return redirect(url_for('dashboard'))
        else:
            flash("Login failed. Check email and password.", "danger")
    return render_template('login.html', form=form)

@app.route('/dashboard')
def dashboard():
    if 'user_id' in session:
        total_spots = len(spots_status)
        available_spots = sum(1 for status in spots_status if status)

        return render_template('index.html', total_spots=total_spots, available_spots=available_spots)
    return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/space_count', methods=['GET'])
def space_count():
    free_spaces_count = mongo.db.slots.count_documents({"status": "free"})
    return jsonify({"free_spaces": free_spaces_count})

@app.route('/book', methods=['GET', 'POST'])
def book():
    if request.method == 'POST':
        # Handle the booking logic
        name = request.form['name']
        phone = request.form['phone']
        start_time = request.form['start_time']
        hours = request.form['hours']
        
        # Check if there is a free parking slot
        free_slot = mongo.db.slots.find_one({"status": "free"})
        if free_slot:
            # Update the slot status to booked
            mongo.db.slots.update_one({"_id": free_slot["_id"]}, {"$set": {"status": "booked"}})
            
            # Create a booking record
            mongo.db.bookings.insert_one({
                "slot_id": free_slot["slot_id"],
                "name": name,
                "phone": phone,
                "start_time": start_time,
                "hours": hours
            })
            
            return redirect(url_for('payment'))  # Redirect to the payment page
        else:
            return render_template('book.html', free_spaces=0, error="No free slots available")

    # Handle GET request (initial page load)
    return render_template('book.html', free_spaces=0)

@app.route('/get_parking_data')
def get_parking_data():
    total_spots = len(spots_status)
    available_spots = sum(1 for status in spots_status if status)
    return jsonify(total_spots=total_spots, available_spots=available_spots)

# Main Execution
if __name__ == '__main__':
    app.run(debug=True, threaded=True)