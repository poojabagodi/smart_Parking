var options = {
    amount: 50000,  // Amount in the smallest currency unit (paise or cents)
    currency: "INR",
    receipt: "order_rcptid_11",
  };
  
  razorpay.orders.create(options, function(err, order) {
    console.log(order);
  });

  var options = {
    "key": "YOUR_RAZORPAY_KEY",  // Replace with your Razorpay Key ID
    "amount": 50000,
    "currency": "INR",
    "order_id": "order_rcptid_11",
    "name": "Merchant Name",
    "description": "Purchase Description",
    "image": "https://example.com/your_logo.png",
    "handler": function (response) {
      alert(response.razorpay_payment_id);
      alert(response.razorpay_order_id);
      alert(response.razorpay_signature);
    }
  };
  
  var rzp1 = new Razorpay(options);
  rzp1.open();