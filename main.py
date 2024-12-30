from flask import Flask, render_template, Response, request, redirect, url_for, session, flash, jsonify
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, ValidationError
from flask_pymongo import PyMongo
import bcrypt
import cv2
import numpy as np
from util import get_parking_spots_bboxes, empty_or_not
import random
import razorpay
import os
import dotenv

# ----------------------
# App Initialization
# ----------------------
app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# Setup MongoDB URI
app.config["MONGO_URI"] = "mongodb://localhost:27017/your_database_name"
mongo = PyMongo(app)

dotenv.load_dotenv()
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
mask_path = r'D:\new_model_park\parking\mask_1920_1080.png'
video_path = r'D:\new_model_park\parking\parking_1920_1080.mp4'

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

global free_spots


# ----------------------
# Video Frame Generator
# ----------------------
def calc_diff(im1, im2):
    return np.abs(np.mean(im1) - np.mean(im2))

# Update the generate_frames function
def generate_frames():
    global previous_frame, frame_nmr, spots_status
    while True:
        success, frame = cap.read()
        if not success:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # Restart video if end is reached
            continue

        # Green frame logic inside here
        green_frame = np.zeros_like(frame)  # Create a black frame of the same size as the original frame

        if frame_nmr % step == 0:
            if previous_frame is not None:
                for spot_indx, spot in enumerate(spots):
                    x1, y1, w, h = spot
                    spot_crop = frame[y1:y1 + h, x1:x1 + w]
                    diffs[spot_indx] = calc_diff(spot_crop, previous_frame[y1:y1 + h, x1:x1 + w])

                for spot_indx in range(len(spots)):
                    x1, y1, w, h = spots[spot_indx]
                    spot_crop = frame[y1:y1 + h, x1:x1 + w]
                    spot_status = empty_or_not(spot_crop)
                    spots_status[spot_indx] = spot_status
                    print(f"Spot {spot_indx}: {spot_status}")  # Debug print

        previous_frame = frame.copy()

        for spot_indx, (x1, y1, w, h) in enumerate(spots):
            spot_status = spots_status[spot_indx]
            color = (0, 255, 0) if spot_status else (0, 0, 255)  # Red for empty spots
            cv2.rectangle(frame, (x1, y1), (x1 + w, y1 + h), color, 2)
            cv2.putText(frame, str(spot_numbers[spot_indx]), (x1, y1 + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

            # For green frame, draw only empty spots
            if not spot_status:  # If the spot is empty
                cv2.rectangle(green_frame, (x1, y1), (x1 + w, y1 + h), (0, 0, 255), 2)  # Red for empty
                cv2.putText(green_frame, str(spot_numbers[spot_indx]), (x1 + 5, y1 + 15),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        # Show the green frame in a separate window
        cv2.namedWindow('Empty Parking Spots', cv2.WINDOW_NORMAL)
        cv2.imshow('Empty Parking Spots', green_frame)

        available_spots = sum(1 for status in spots_status if not status)  # Count empty spots
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
    if 'user_id' in session:
        return render_template('first.html')
    else:
        return render_template('first.html')

@app.route('/display')
def display():
    # Find free spots and their numbers

    free_spots = [{"spot_number": spot_numbers[i], "bbox": spots[i]} for i, status in enumerate(spots_status) if status]
    
    return render_template('display.html', free_spots=free_spots)
    # return {"free_spots": free_spots  , "total_spots": spots_status}


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

@app.route('/index')
def index():
    return render_template('index.html')

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

@app.route('/get_parking')
def get_parking():
    # Find the free spots and their numbers
    free_spots = [{"spot_number": spot_numbers[i], "bbox": spots[i]} for i, status in enumerate(spots_status) if status]

    # Print the data to check the result
    print(f"Free spots: {free_spots}")

    return jsonify({"free_spots": free_spots})

# @app.route('/display', methods=['GET'])
# def display_parking_spots():
#     # Generate data for available spots dynamically
#     free_spots = [{"spot_number": spot_numbers[i], "bbox": spots[i]} for i, status in enumerate(spots_status) if not status]
    
#     return render_template('display.html', free_spots=free_spots)
#     # return jsonify({"free_spots": free_spots})

# Main Execution

global client
client = razorpay.Client(auth=(os.getenv('id'), os.getenv('key')))
@app.route('/pay' ,methods=[ "POST"])
def pay():
    amount = request.form['amount']
    amount=int(amount)
    amount *=100
    if amount > 100:
        
        data = { "amount": amount, "currency": "INR", "receipt": "order_rcptid_11" }
        payment = client.order.create(data=data)
        pdata=[amount, payment["id"]]
        mongo.db.users.update_one(
            {'user_id': session['user_id']},
        {'$set': session['book_details']}
    )
        return render_template("payment.html", pdata=pdata)
    return redirect("/success")

@app.route('/success', methods=["POST"])
def success():
    if request.method == "POST":

        pid=request.form.get("razorpay_payment_id")
        ordid=request.form.get("razorpay_order_id")
        sign=request.form.get("razorpay_signature")
        print(f"The payment id : {pid}, order id : {ordid} and signature : {sign}")
        params={
        'razorpay_order_id': ordid,
        'razorpay_payment_id': pid,
        'razorpay_signature': sign
        }
        final=client.utility.verify_payment_signature(params)
        if final == True:
            return redirect("/display", code=301)
        return "Something Went Wrong Please Try Again"
    return 'get in success'

razorpay_client = razorpay.Client(auth=(os.getenv('id'), os.getenv('key')))

@app.route('/payment', methods=['POST'])
def payment2():
    return render_template('payment2.html')

@app.route('/book_history')
def book_history():
    if 'user_id' not in session:
        return redirect(url_for('login'))  # Ensure the user is logged in

    # Fetch booking history from MongoDB for the logged-in user
    bookings_cursor = mongo.db.bookings.find({"email": session['user_id']})

    # Print bookings for debugging
    bookings = list(bookings_cursor)  # Convert the cursor to a list

    print(f"Bookings found: {bookings}")

    # Convert the bookings data to a list to pass to the template
    booking_list = []
    for booking in bookings:
        booking_data = {
            "name": booking["name"],
            "phone": booking["phone"],
            "start_time": booking["start_time"],
            "hours": booking["hours"],
            "status": booking["status"],
            "slot_id": booking["slot_id"]
        }
        booking_list.append(booking_data)

    return render_template('book_history.html', bookings=booking_list)

# def payment(spot_number, user_id, cost):

#     spot_number = int(spot_number)
#     user_id = user_id

#     # Check if the seat is still available
#     # spot = next((s for s in free_spots if s['spot_number'] == spot_number), None)
#     # if spot and spot.get('status') != 'paid':

#         # Proceed to payment processing (simulate with a simple check)
#         # make_payment(cost)  # Update parking lot status after successful payment
#         # if random.choice([True, False]):
#         #     # Update spot status after successful payment
#         #     spot['status'] = False
#         #     spot['user_id'] = user_id

#         #     return jsonify({'status': True, 'message': 'Payment successful'})
#         # else:
#         #     return jsonify({'status': False, 'message': 'Payment failed'})
#     else:
#         return jsonify({'status':False, 'message': 'Seat is no longer available'})

@app.route('/find_seat', methods=['POST'])
def find_seat():
    # return request.form
    free_spots = [{"spot_number": spot_numbers[i], "bbox": spots[i]} for i, status in enumerate(spots_status) if status]

    if not free_spots:
        return jsonify({'status': 'error', 'message': 'No free spots available'})

    # Simulate finding an empty seat
    spot = random.choice(free_spots)
    spot_number = spot['spot_number']

    # Update the spot status to 'selected'
    try:
            
        for s in free_spots:
            if s['spot_number'] == spot_number:
                s['status'] = 'selected'
                break
    except Exception as e:
        return jsonify({'status': 'error', 'message fing free slot': str(e)})
    
    

    session['book_details']={
        'status': 'success',
        'message': 'Seat found',
        'spot_number': spot_number,
        'user_id': session['user_id'],
        'license_plate':request.form['license_plate'],
        'phone':request.form['phone'],
        'cost':f'Rs: {request.form["cost"]}/-' ,

    }
    # return redirect(url_for('pay', amount=10))
    return render_template('details.html', slot =  s['spot_number']  )
    


if __name__ == '__main__':
    app.run(debug=True, threaded=True)
