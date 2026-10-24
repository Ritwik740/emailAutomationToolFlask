from flask import Flask, request, redirect, flash
import sqlite3
import sys
import pymysql
import smtplib
from email.mime.text import MIMEText
import traceback
from flask import Flask, render_template, request, redirect, flash, jsonify, session, url_for, abort
import os
from dotenv import load_dotenv
import pandas as pd
from flask_mail import Mail, Message
from werkzeug.utils import secure_filename
import random
import subprocess
import string
import math
import threading
import time
from datetime import datetime, timedelta
import sqlite3
import pytz
from threading import Event
import uuid
import razorpay
import json
import hmac
import hashlib
import functools
import smtplib
from email.mime.text import MIMEText
import logging
from logging.handlers import RotatingFileHandler
import pymysql
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from werkzeug.security import generate_password_hash, check_password_hash
from email.mime.base import MIMEBase
from email import encoders
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
import re
import threading
from datetime import datetime
from flask import session, render_template
import time

scheduler_running = False
scheduler_start_time = None
scheduler_running_lock = threading.Lock()

# Load environment variables from .env file
load_dotenv()

# Configure environment-specific settings
is_production = os.environ.get('FLASK_ENV') == 'production'
is_on_hostinger = os.environ.get('HOSTINGER') == 'true'

# Configure paths based on environment
if is_on_hostinger:
    base_path = os.environ.get('HOSTINGER_DATA_PATH', '/home/username/data')
elif 'RENDER' in os.environ:
    base_path = "/opt/render/project/src/data" if os.path.exists("/opt/render/project/src/data") else "/opt/render/project/src"
else:
    base_path = "."

UPLOAD_FOLDER = os.path.join(base_path, "uploads")
DB_FOLDER = os.path.join(base_path, "database")
LOG_FOLDER = os.path.join(base_path, "logs")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DB_FOLDER, exist_ok=True)
os.makedirs(LOG_FOLDER, exist_ok=True)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY')

csrf = CSRFProtect(app)

if not app.secret_key:
    if is_production:
        raise ValueError("SECRET_KEY environment variable must be set in production")
    else:
        app.secret_key = 'dev_secret_key_for_testing_only'

app.config['SESSION_TYPE'] = 'filesystem'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Razorpay Configuration
RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID')
RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET')

if not (RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET):
    if is_production:
        raise ValueError("Razorpay credentials must be set in production")
    else:
        RAZORPAY_KEY_ID = 'rzp_test_dummy_key'
        RAZORPAY_KEY_SECRET = 'dummy_secret'

razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

# Admin email
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')

if not (ADMIN_EMAIL and ADMIN_PASSWORD) and is_production:
    raise ValueError("Admin email credentials must be set in production")

SUBSCRIPTION_AMOUNT = int(os.environ.get('SUBSCRIPTION_AMOUNT', '1900'))

# Flask-Mail Configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = 'default_email@example.com'
app.config['MAIL_PASSWORD'] = 'default_password'
app.config['MAIL_DEFAULT_SENDER'] = 'default_email@example.com'
mail = Mail(app)

# Path to SQLite DB (used in development)
DB_PATH = os.path.join(DB_FOLDER, "emails.db")

# Initialize rate limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

def get_db_connection():
    """Get database connection based on environment"""
    if is_production:
        db_user = os.environ.get('DB_USER')
        db_password = os.environ.get('DB_PASSWORD')
        db_host = os.environ.get('DB_HOST', 'localhost')
        db_name = os.environ.get('DB_NAME')
        db_port = os.environ.get('DB_PORT', 3306)
        
        if not all([db_user, db_password, db_name]):
            raise ValueError("Database credentials must be set in production")
        
        conn = pymysql.connect(
            host=db_host,
            user=db_user,
            password=db_password,
            database=db_name,
            port=int(db_port),
            cursorclass=pymysql.cursors.DictCursor
        )
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

    return conn

def init_db():
    """Initialize the database schema"""
    conn = get_db_connection()
    c = conn.cursor()
    
    if is_production:
        # MySQL schema
        c.execute('''
            CREATE TABLE IF NOT EXISTS emails (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT,
                sender_email VARCHAR(255) NOT NULL,
                sender_password VARCHAR(255) NOT NULL,
                recipient_email VARCHAR(255) NOT NULL,
                recipient_name VARCHAR(255) NOT NULL,
                subject VARCHAR(255) NOT NULL,
                body TEXT NOT NULL,
                sent_date DATETIME NOT NULL,
                followup_date DATETIME,
                followup_sent TINYINT(1) DEFAULT 0,
                followup_body TEXT
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS credentials (
                email VARCHAR(255) PRIMARY KEY,
                password VARCHAR(255) NOT NULL
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                full_name VARCHAR(255) NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                secret_key VARCHAR(255) NOT NULL,
                registration_date DATETIME NOT NULL,
                payment_id VARCHAR(255),
                payment_status VARCHAR(50),
                subscription_end_date DATETIME,
                active TINYINT(1) DEFAULT 1
            )
        ''')
    else:
        # SQLite schema
        c.execute('''
            CREATE TABLE IF NOT EXISTS emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                sender_email TEXT NOT NULL,
                sender_password TEXT NOT NULL,
                recipient_email TEXT NOT NULL,
                recipient_name TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                sent_date TEXT NOT NULL,
                followup_date TEXT,
                followup_sent INTEGER DEFAULT 0,
                followup_body TEXT
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS credentials (
                email TEXT PRIMARY KEY,
                password TEXT NOT NULL
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                secret_key TEXT NOT NULL,
                registration_date TEXT NOT NULL,
                payment_id TEXT,
                payment_status TEXT,
                subscription_end_date TEXT,
                active INTEGER DEFAULT 1
            )
        ''')

    conn.commit()
    conn.close()
    app.logger.info("Database initialized")

init_db()
db_lock = threading.Lock()

ALLOWED_EXTENSIONS = {'xlsx', 'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'}
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def generate_secret_key(length=16):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def send_admin_email(to_email, subject, body):
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = ADMIN_EMAIL
        msg['To'] = to_email
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(ADMIN_EMAIL, ADMIN_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"Error sending admin email: {str(e)}")
        return False

def login_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function
# ---------------------- User Authentication & Payment ---------------------- #

@app.route('/')
def index():
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        secret_key = request.form.get('secret_key')

        if not email or not secret_key:
            flash('Please provide both email and secret key', 'error')
            return render_template('login.html')

        try:
            conn = get_db_connection()
            if is_production:
                sql = 'SELECT * FROM users WHERE email = %s AND active = 1'
            else:
                sql = 'SELECT * FROM users WHERE email = ? AND active = 1'

            cursor = conn.cursor()
            cursor.execute(sql, (email,))
            row = cursor.fetchone()
            user = dict(row) if row else None
            conn.close()

            if user and check_password_hash(user['secret_key'], secret_key):
                
                
                if user['subscription_end_date']:
                    # Check if subscription_end_date is a datetime object
                    end_date = user['subscription_end_date'] if isinstance(user['subscription_end_date'], datetime) else datetime.strptime(user['subscription_end_date'], '%Y-%m-%d %H:%M:%S')
                    # Compare the datetime objects directly
                    if end_date < datetime.utcnow():
                        flash('Your subscription has expired. Please renew your subscription.', 'error')
                        return redirect(url_for('login'))
                session['user_id'] = user['id']
                session['user_email'] = user['email']
                session['user_name'] = user['full_name']
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid email or secret key', 'error')

        except Exception as e:
            flash(f'Login error: {str(e)}', 'error')

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def register():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        full_name = request.form.get('full_name')
        email = request.form.get('email')

        if not full_name or not email:
            flash('Please provide both full name and email', 'error')
            return render_template('register.html')

        full_name = full_name.strip()
        email = email.strip().lower()

        email_regex = r'^[\w\.-]+@[\w\.-]+\.\w+$'
        if not re.match(email_regex, email):
            flash('Invalid email format', 'error')
            return render_template('register.html')

        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT email FROM users WHERE email = %s', (email,))
        user = cursor.fetchone()
        conn.close()
        if user:
            flash('User with this email already exists, please login or use a different email', 'error')
            return render_template('register.html')
        
        session['temp_user_data'] = {'full_name': full_name, 'email': email}
        return redirect(url_for('payment'))

    return render_template('register.html')


@app.route('/payment')
def payment():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if 'temp_user_data' not in session:
        flash('Please register before proceeding to payment', 'error')
        return redirect(url_for('register'))

    try:
        order_amount = SUBSCRIPTION_AMOUNT
        order_currency = 'USD'
        order_receipt = f"rcpt_{int(time.time())}"

        razorpay_order = razorpay_client.order.create({
            'amount': order_amount,
            'currency': order_currency,
            'receipt': order_receipt,
        })

        payment_data = {
            'key': RAZORPAY_KEY_ID,
            'amount': order_amount,
            'currency': order_currency,
            'name': 'Email Automation Tool',
            'description': 'Monthly Subscription',
            'order_id': razorpay_order['id'],
            'prefill': session['temp_user_data'],
            'theme': {'color': '#3498db'}
        }

        return render_template('payment.html', payment=payment_data)

    except Exception as e:
        flash(f'Payment initialization error: {str(e)}', 'error')
        return redirect(url_for('register'))


@app.route('/payment/callback', methods=['POST'])
def payment_callback():
    if 'temp_user_data' not in session:
        flash('Invalid payment session', 'error')
        return redirect(url_for('register'))

    try:
        payment_id = request.form.get('razorpay_payment_id', '')
        order_id = request.form.get('razorpay_order_id', '')
        signature = request.form.get('razorpay_signature', '')

        params_dict = {
            'razorpay_payment_id': payment_id,
            'razorpay_order_id': order_id,
            'razorpay_signature': signature
        }

        try:
            razorpay_client.utility.verify_payment_signature(params_dict)
            payment_verified = True
        except Exception:
            payment_verified = False

        if payment_verified:
            full_name = session['temp_user_data']['full_name']
            email = session['temp_user_data']['email']
            secret_key = generate_secret_key()
            hashed_secret = encrypt_password(secret_key)
            subscription_end_date = (datetime.utcnow() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
            registration_date = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

            conn = get_db_connection()
            cursor = conn.cursor()

            if is_production:
                sql = '''
                    INSERT INTO users (full_name, email, secret_key, registration_date, payment_status, subscription_end_date, active)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                '''
            else:
                sql = '''
                    INSERT INTO users (full_name, email, secret_key, registration_date, payment_status, subscription_end_date, active)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                '''

            cursor.execute(sql, (
                full_name, email, hashed_secret,
                registration_date, 'completed',
                subscription_end_date, 1
            ))

            conn.commit()
            conn.close()

            # Send credentials email
            subject = "Your Email Automation Tool Credentials"
            body = f"""
Hello {full_name},

Thank you for subscribing to Email Automation Tool!

Your login credentials:
Email: {email}
Secret Key: {secret_key}

Please keep this information secure.

Best regards,
Email Automation Tool Team
"""
            send_admin_email(email, subject, body)
            session.pop('temp_user_data', None)
            flash('Payment successful! Your account has been created. Please check your email for credentials.', 'success')
            return redirect(url_for('login'))

        else:
            flash('Payment verification failed. Please try again.', 'error')
            return redirect(url_for('payment'))

    except Exception as e:
        flash(f'Payment processing error: {str(e)}', 'error')
        return redirect(url_for('register'))


@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out successfully", "success")
    return redirect(url_for('login'))

# ---------------------- Subscription Renewal ---------------------- #

@app.route('/renew')
@login_required
def renew():
    conn = get_db_connection()
    user = conn.execute('SELECT subscription_end_date FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    conn.close()
    
    # end_date = user['subscription_end_date'] if isinstance(user['subscription_end_date'], datetime) else datetime.strptime(user['subscription_end_date'], '%Y-%m-%d %H:%M:%S')
    
    
    if user and user['subscription_end_date'] and datetime.strptime(user['subscription_end_date'], '%Y-%m-%d %H:%M:%S') >= datetime.utcnow():
        flash('Your subscription is still active.', 'info')
        return redirect(url_for('dashboard'))
    try:
        order_amount = SUBSCRIPTION_AMOUNT
        order_currency = 'USD'
        order_receipt = f"renew_{session['user_id']}_{int(time.time())}"
        razorpay_order = razorpay_client.order.create({
            'amount': order_amount,
            'currency': order_currency,
            'receipt': order_receipt,
        })
        payment_data = {
            'key': RAZORPAY_KEY_ID,
            'amount': order_amount,
            'currency': order_currency,
            'name': 'Email Automation Tool Renewal',
            'description': 'Subscription Renewal',
            'order_id': razorpay_order['id']
        }
        return render_template('renew.html', payment=payment_data)
    except Exception as e:
        flash(f'Renewal initialization error: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

@app.route('/renew/callback', methods=['POST'])
@login_required
def renew_callback():
    try:
        payment_id = request.form.get('razorpay_payment_id', '')
        order_id = request.form.get('razorpay_order_id', '')
        signature = request.form.get('razorpay_signature', '')
        params_dict = {
            'razorpay_payment_id': payment_id,
            'razorpay_order_id': order_id,
            'razorpay_signature': signature
        }
        try:
            razorpay_client.utility.verify_payment_signature(params_dict)
            payment_verified = True
        except Exception:
            payment_verified = False
        if payment_verified:
            subscription_end_date = (datetime.utcnow() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
            conn = get_db_connection()
            if is_production:
                sql = '''
                    UPDATE users SET subscription_end_date = %s, payment_id = %s, payment_status = %s WHERE id = %s
                '''
            else:
                sql = '''
                    UPDATE users SET subscription_end_date = ?, payment_id = ?, payment_status = ? WHERE id = ?
                '''
            conn.execute(sql, (subscription_end_date, payment_id, 'renewed', session['user_id']))
            conn.commit()
            conn.close()
            flash('Subscription renewed successfully!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Renewal payment verification failed. Please try again.', 'error')
            return redirect(url_for('renew'))
    except Exception as e:
        flash(f'Renewal processing error: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

# ---------------------- Dashboard & Email Automation ---------------------- #

@app.route('/dashboard', methods=["GET", "POST"])
@login_required
def dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()

    if is_production:
        cursor.execute('SELECT subscription_end_date FROM users WHERE id = %s', (session['user_id'],))
    else:
        cursor.execute('SELECT subscription_end_date FROM users WHERE id = ?', (session['user_id'],))

    user = cursor.fetchone()
    conn.close()

    subscription_active = False
    user_subscription_end = "N/A"
    if user and user['subscription_end_date']:
        sub_date = user['subscription_end_date'] if isinstance(user['subscription_end_date'], datetime) else datetime.strptime(user['subscription_end_date'], '%Y-%m-%d %H:%M:%S')
        user_subscription_end = sub_date.strftime('%B %d, %Y')
        if sub_date >= datetime.utcnow():
            subscription_active = True
    # If subscription is expired, show renew option (and no email-sending form)
    if not subscription_active:
        flash("Your subscription has expired. Please renew to send emails.", "error")
        return render_template('dashboard.html', subscription_active=False, user_subscription_end=user_subscription_end)
    # If subscription active and POST, process email sending
    if request.method == "POST":
        subject = request.form.get("subject")
        body = request.form.get("body")
        followup_days = request.form.get("followup_days")
        followup_datetime = request.form.get("followup_datetime")
        use_days = request.form.get("use-days") == "on"
        followup_body = request.form.get("followup_body")
        has_followup = False
        if followup_body:
            has_followup = True
            if use_days and followup_days:
                try:
                    followup_days = int(followup_days)
                except ValueError:
                    flash("Follow-up days must be a number", "error")
                    return redirect("/dashboard")
            elif not use_days and followup_datetime:
                try:
                    datetime.strptime(followup_datetime, '%Y-%m-%dT%H:%M')
                except ValueError:
                    flash("Invalid follow-up date/time format", "error")
                    return redirect("/dashboard")
            else:
                flash("Please provide valid follow-up timing", "error")
                return redirect("/dashboard")
        # Recipients file
        recipients_file = request.files["xlsx_file"]
        if not (recipients_file and allowed_file(recipients_file.filename)):
            flash("Please upload a valid XLSX file with recipients", "error")
            return redirect("/dashboard")
        rec_filename = secure_filename(recipients_file.filename)
        rec_path = os.path.join(app.config["UPLOAD_FOLDER"], rec_filename)
        recipients_file.save(rec_path)
        try:
            recipients_df = pd.read_excel(rec_path)
            if "name" not in recipients_df.columns or "email" not in recipients_df.columns:
                flash("Recipients XLSX must contain 'name' and 'email' columns!", "error")
                return redirect("/dashboard")
        except Exception as e:
            flash(f"Error reading recipients XLSX: {e}", "error")
            return redirect("/dashboard")
        # Sender login file
        login_file = request.files["login_file"]
        if not (login_file and allowed_file(login_file.filename)):
            flash("Please upload a valid XLSX file with login credentials", "error")
            return redirect("/dashboard")
        login_filename = secure_filename(login_file.filename)
        login_path = os.path.join(app.config["UPLOAD_FOLDER"], login_filename)
        login_file.save(login_path)
        try:
            login_df = pd.read_excel(login_path)
            if "email" not in login_df.columns or "password" not in login_df.columns:
                flash("Login XLSX must contain 'email' and 'password' columns!", "error")
                return redirect("/dashboard")
            if len(login_df) == 0:
                flash("Login file must contain at least one email account!", "error")
                return redirect("/dashboard")
        except Exception as e:
            flash(f"Error reading login XLSX: {e}", "error")
            return redirect("/dashboard")
        # Process attachments (optional)
        attachments = []
        if "attachments" in request.files:
            files = request.files.getlist("attachments")
            for file in files:
                if file.filename == '':
                    continue
                if file and allowed_file(file.filename):
                    fname = secure_filename(file.filename)
                    file_path = os.path.join(app.config["UPLOAD_FOLDER"], fname)
                    file.save(file_path)
                    attachments.append(file_path)
                    flash(f"Uploaded attachment: {fname}", "success")
                else:
                    flash(f"Skipped file: {file.filename} (invalid type)", "warning")
        total_recipients = len(recipients_df)
        total_senders = len(login_df)
        recipients_per_sender = math.ceil(total_recipients / total_senders)
        sender_index = 0
        emails_sent = 0
        errors = 0
        conn = get_db_connection()
        c = conn.cursor()
        now = datetime.now()
        current_date = now.strftime("%Y-%m-%d %H:%M:%S")
        followup_date = None
        if has_followup:
            if use_days and followup_days:
                followup_date = (now + timedelta(days=followup_days)).strftime("%Y-%m-%d %H:%M:%S")
            elif not use_days and followup_datetime:
                try:
                    specific_datetime = datetime.strptime(followup_datetime, '%Y-%m-%dT%H:%M')
                    followup_date = specific_datetime.strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    flash("Invalid follow-up date/time format", "error")
                    return redirect("/dashboard")
        # Store sender credentials in DB
        for _, row in login_df.iterrows():
            em = row["email"]
            pw = row["password"]
            if is_production:
                sql = 'INSERT INTO credentials (email, password) VALUES (%s, %s) ON DUPLICATE KEY UPDATE password = VALUES(password)'
            else:
                sql = 'INSERT OR REPLACE INTO credentials (email, password) VALUES (?, ?)'
            c.execute(sql, (em, pw))
        conn.commit()
        # Iterate through recipients, sending emails and storing records with the current user's id.
        for i, rec_row in recipients_df.iterrows():
            sender_row = login_df.iloc[sender_index]
            sender_email = sender_row["email"]
            sender_password = sender_row["password"]
            app.config['MAIL_USERNAME'] = sender_email
            app.config['MAIL_PASSWORD'] = sender_password
            app.config['MAIL_DEFAULT_SENDER'] = sender_email
            mail = Mail(app)
            try:
                msg = Message(subject, recipients=[rec_row["email"]])
                msg.body = f"Hello {rec_row['name']},\n\n{body}"
                for attach in attachments:
                    with open(attach, "rb") as f:
                        msg.attach(os.path.basename(attach), "application/octet-stream", f.read())
                mail.send(msg)
                emails_sent += 1
                if is_production:
                    sql = '''
                        INSERT INTO emails (user_id, sender_email, sender_password, recipient_email, recipient_name, subject, body, sent_date, followup_date, followup_body)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    '''
                else:
                    sql = '''
                        INSERT INTO emails (user_id, sender_email, sender_password, recipient_email, recipient_name, subject, body, sent_date, followup_date, followup_body)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    '''
                c.execute(sql, (
                    session['user_id'],
                    sender_email,
                    sender_password,
                    rec_row["email"],
                    rec_row["name"],
                    subject,
                    body,
                    current_date,
                    followup_date,
                    followup_body if has_followup else None
                ))
                conn.commit()
                if (i + 1) % recipients_per_sender == 0 and sender_index < total_senders - 1:
                    sender_index += 1
                    flash(f"Switched to sender: {login_df.iloc[sender_index]['email']}", "info")
            except Exception as e:
                errors += 1
                flash(f"Error sending email to {rec_row['email']}: {e}", "error")
                if sender_index < total_senders - 1:
                    sender_index += 1
                    flash(f"Error with sender, switched to: {login_df.iloc[sender_index]['email']}", "warning")
        conn.close()
        flash(f"Email sending complete: {emails_sent} sent, {errors} failed", "success")
        if has_followup:
            if use_days:
                flash(f"Follow-up emails scheduled for {followup_days} days later", "info")
            else:
                followup_dt = datetime.strptime(followup_date, "%Y-%m-%d %H:%M:%S")
                formatted_date = followup_dt.strftime("%B %d, %Y at %I:%M %p")
                flash(f"Follow-up emails scheduled for {formatted_date}", "info")
        return redirect(url_for('dashboard'))
    else:
        # GET: show dashboard with email-sending form only (email tracking is on /emails)
        return render_template('dashboard.html', subscription_active=True, user_subscription_end=user_subscription_end)

# ---------------------- Follow-Up Scheduler & Manual Trigger ---------------------- #

# def followup_scheduler():
#     print("Follow-up scheduler started")
#     loop_count = 0
#     while True:
#         loop_count += 1
#         print(f"Scheduler check #{loop_count} at {datetime.now()}")
#         try:
#             conn = get_db_connection()
            
#             # Set row_factory only if SQLite is used
#             is_production = os.environ.get('FLASK_ENV') == 'production'
#             if not is_production:
#                 conn.row_factory = sqlite3.Row  # Only set this for SQLite
            
#             c = conn.cursor()
#             now = datetime.now()
#             current_time = now.strftime("%Y-%m-%d %H:%M:%S")
#             print(f"Current time for comparison: {current_time}")
            
#             # Check for the existence of the 'emails' table
#             try:
#                 c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='emails'")  # This is specific to SQLite
#                 if not c.fetchone():
#                     print("Error: 'emails' table does not exist in the database.")
#                     time.sleep(60)
#                     continue
#             except Exception as db_err:
#                 print(f"Database structure check error: {str(db_err)}")
#                 time.sleep(60)
#                 continue

#             # Check the database type (MySQL or SQLite) based on environment variable or config
#             if is_production:  # MySQL
#                 query = '''
#                     SELECT id, sender_email, sender_password, recipient_email, recipient_name, subject, followup_body, followup_date
#                     FROM emails 
#                     WHERE followup_date <= %s 
#                     AND followup_sent = 0
#                     AND followup_body IS NOT NULL
#                 '''
#             else:  # SQLite
#                 query = '''
#                     SELECT id, sender_email, sender_password, recipient_email, recipient_name, subject, followup_body, followup_date
#                     FROM emails 
#                     WHERE followup_date <= ? 
#                     AND followup_sent = 0
#                     AND followup_body IS NOT NULL
#                 '''

#             c.execute(query, (current_time,))
#             emails_to_followup = c.fetchall()
#             print(f"Found {len(emails_to_followup)} emails due for follow-up")
            
#             for email in emails_to_followup:
#                 email_id = email['id']
#                 sender_email = email['sender_email']
#                 sender_password = email['sender_password']
#                 recipient_email = email['recipient_email']
#                 recipient_name = email['recipient_name']
#                 subject = email['subject']
#                 followup_body = email['followup_body']
#                 print(f"Sending follow-up to {recipient_email} from {sender_email}")
#                 try:
#                     with app.app_context():
#                         mail_config = {
#                             'MAIL_SERVER': 'smtp.gmail.com',
#                             'MAIL_PORT': 587,
#                             'MAIL_USE_TLS': True,
#                             'MAIL_USE_SSL': False,
#                             'MAIL_USERNAME': sender_email,
#                             'MAIL_PASSWORD': sender_password,
#                             'MAIL_DEFAULT_SENDER': sender_email
#                         }
#                         mail_app = Flask(f"mail_app_{email_id}")
#                         for key, value in mail_config.items():
#                             mail_app.config[key] = value
#                         with mail_app.app_context():
#                             mail_instance = Mail(mail_app)
#                             followup_subject = f"Follow-up: {subject}"
#                             msg = Message(followup_subject, recipients=[recipient_email])
#                             msg.body = f"Hello {recipient_name},\n\n{followup_body}"
#                             mail_instance.send(msg)
#                              # Update followup_sent status after sending
#                             if is_production:  # MySQL
#                                 c.execute('UPDATE emails SET followup_sent = %s WHERE id = %s', (1, email_id))
#                             else:  # SQLite
#                                 c.execute('UPDATE emails SET followup_sent = ? WHERE id = ?', (1, email_id))
                            
#                             conn.commit()
#                             print(f"Successfully sent follow-up to {recipient_email}")
#                 except Exception as e:
#                     print(f"Error sending follow-up to {recipient_email}: {str(e)}")
#             conn.close()
#             time.sleep(60)
#         except Exception as e:
#             print(f"Error in follow-up scheduler: {str(e)}")
#             time.sleep(30)


def followup_scheduler():
    print("Follow-up scheduler started")
    loop_count = 0
    while True:
        loop_count += 1
        print(f"Scheduler check #{loop_count} at {datetime.now()}")
        try:
            conn = get_db_connection()
            
            # Set row_factory only if SQLite is used
            is_production = os.environ.get('FLASK_ENV') == 'production'
            if not is_production:
                conn.row_factory = sqlite3.Row
            
            c = conn.cursor()
            now = datetime.now()
            current_time = now.strftime("%Y-%m-%d %H:%M:%S")
            print(f"Current time for comparison: {current_time}")

            # Check for table existence (SQLite specific)
            if not is_production:
                c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='emails'")
                if not c.fetchone():
                    print("Error: 'emails' table does not exist in the database.")
                    time.sleep(60)
                    continue

            # Query for pending follow-ups
            if is_production:
                query = '''
                SELECT 
                    emails.id, 
                    emails.sender_email, 
                    emails.sender_password, 
                    emails.recipient_email, 
                    emails.recipient_name, 
                    emails.subject, 
                    emails.followup_body
                FROM 
                    emails
                JOIN 
                    users ON emails.id = users.id
                WHERE 
                    emails.followup_date <= %s
                    AND emails.followup_sent = 0
                    AND emails.followup_body IS NOT NULL
                    AND users.subscription_end_date >= CURRENT_TIMESTAMP
                '''
                    # SELECT id, sender_email, sender_password, recipient_email, recipient_name, subject, followup_body
                    # FROM emails 
                    # WHERE followup_date <= %s 
                    # AND followup_sent = 0
                    # AND followup_body IS NOT NULL
            else:
                query = '''
                    SELECT id, sender_email, sender_password, recipient_email, recipient_name, subject, followup_body
                    FROM emails 
                    WHERE followup_date <= ? 
                    AND followup_sent = 0
                    AND followup_body IS NOT NULL
                '''

            c.execute(query, (current_time,))
            emails_to_followup = c.fetchall()
            print(f"Found {len(emails_to_followup)} emails due for follow-up")
            
            for email in emails_to_followup:
                email_id = email['id']
                sender_email = email['sender_email']
                sender_password = email['sender_password']
                recipient_email = email['recipient_email']
                recipient_name = email['recipient_name']
                subject = email['subject']
                followup_body = email['followup_body']

                print(f"Sending follow-up to {recipient_email} from {sender_email}")
                try:
                    msg = MIMEText(f"Hello {recipient_name},\n\n{followup_body}")
                    msg['Subject'] = f"Follow-up: {subject}"
                    msg['From'] = sender_email
                    msg['To'] = recipient_email

                    with smtplib.SMTP('smtp.gmail.com', 587) as server:
                        server.starttls()
                        server.login(sender_email, sender_password)
                        server.sendmail(sender_email, recipient_email, msg.as_string())

                    # Update followup_sent status
                    if is_production:
                        c.execute('UPDATE emails SET followup_sent = %s WHERE id = %s', (1, email_id))
                    else:
                        c.execute('UPDATE emails SET followup_sent = ? WHERE id = ?', (1, email_id))
                    
                    conn.commit()
                    print(f"✅ Successfully sent follow-up to {recipient_email}")
                except Exception as e:
                    print(f"❌ Error sending follow-up to {recipient_email}: {str(e)}")

            conn.close()
            time.sleep(60)

        except Exception as e:
            print(f"🔥 Error in follow-up scheduler: {str(e)}")
            time.sleep(30)


def start_scheduler():
    global scheduler_running, scheduler_start_time
    with scheduler_running_lock:
        if scheduler_running:
            print("Scheduler already running, not starting a new thread")
            return

        scheduler_running = True
        scheduler_start_time = datetime.now()
        print("start_scheduler function called")
        
        # scheduler_thread = threading.Thread(target=followup_scheduler)
        # scheduler_thread.daemon = True
        # scheduler_thread.start()
        # print("Scheduler thread started")
        subprocess.Popen([sys.executable, 'scheduler.py'])
        # subprocess.Popen(['python', 'scheduler.py'])
        print("Scheduler.py started")

@app.route('/emails')
@login_required
def view_emails():
    conn = get_db_connection()
    cursor = conn.cursor()
    user_email = session.get('user_email')  # Ensure this session variable is set after login
    if 'user_id' not in session:
        return "Error: User not logged in.", 403

    if is_production:
        cursor.execute(
            'SELECT id, recipient_email as email, subject, sent_date, followup_sent, followup_date, body, followup_body '
            'FROM emails WHERE user_id = %s ORDER BY sent_date DESC',
            (session['user_id'],)
        )
    else:
        cursor.execute(
            'SELECT id, recipient_email as email, subject, sent_date, followup_sent, followup_date, body, followup_body '
            'FROM emails WHERE user_id = ? ORDER BY sent_date DESC',
            (session['user_id'],)
        )

    emails = cursor.fetchall()
    conn.close()
    
    conn = get_db_connection()
    cursor = conn.cursor()

    if is_production:
        cursor.execute('SELECT subscription_end_date FROM users WHERE id = %s', (session['user_id'],))
    else:
        cursor.execute('SELECT subscription_end_date FROM users WHERE id = ?', (session['user_id'],))

    user = cursor.fetchone()
    conn.close()

    user_subscription_end = "N/A"
    if user and user['subscription_end_date']:
        sub_date = user['subscription_end_date'] if isinstance(user['subscription_end_date'], datetime) else datetime.strptime(user['subscription_end_date'], '%Y-%m-%d %H:%M:%S')
        user_subscription_end = sub_date.strftime('%B %d, %Y')
    return render_template('emails.html', emails=emails,user_subscription_end=user_subscription_end)

    
# @app.route('/send-followup/<int:email_id>', methods=['GET'])
# def send_followup(email_id):
#     try:
#         conn = get_db_connection()

#         # Conditionally use row_factory if using SQLite
#         if not is_production:
#             conn.row_factory = sqlite3.Row

#         c = conn.cursor()

#         # Use different query placeholder syntax based on DB
#         if is_production:
#             c.execute('SELECT * FROM emails WHERE id = %s', (email_id,))
#         else:
#             c.execute('SELECT * FROM emails WHERE id = ?', (email_id,))

#         row = c.fetchone()

#         if not row:
#             flash(f"Email ID {email_id} not found", "error")
#             return redirect('/emails')

#         # Handle row access depending on DB
#         if is_production:
#             email = dict(zip([desc[0] for desc in c.description], row))
#         else:
#             email = row

#         def send_single_followup():
#             if email['followup_sent'] == 1:
#                 flash(f"Follow-up for email ID {email_id} was already sent", "warning")
#                 return False
#             if not email['followup_body']:
#                 flash(f"Email ID {email_id} has no follow-up message", "error")
#                 return False
#             try:
#                 sender_password = email['sender_password']
#                 mail_config = {
#                     'MAIL_SERVER': 'smtp.gmail.com',
#                     'MAIL_PORT': 587,
#                     'MAIL_USE_TLS': True,
#                     'MAIL_USE_SSL': False,
#                     'MAIL_USERNAME': email['sender_email'],
#                     'MAIL_PASSWORD': sender_password,
#                     'MAIL_DEFAULT_SENDER': email['sender_email']
#                 }
#                 mail_app = Flask(f"mail_app_{email_id}")
#                 for key, value in mail_config.items():
#                     mail_app.config[key] = value

#                 with mail_app.app_context():
#                     mail_instance = Mail(mail_app)
#                     followup_subject = f"Follow-up: {email['subject']}"
#                     msg = Message(followup_subject, recipients=[email['recipient_email']])
#                     msg.body = f"Hello {email['recipient_name']},\n\n{email['followup_body']}"
#                     mail_instance.send(msg)

#                     # Use proper placeholder again with lock
#                     with db_lock:
#                         if is_production:
#                             c.execute('UPDATE emails SET followup_sent = 1 WHERE id = %s', (email_id,))
#                         else:
#                             c.execute('UPDATE emails SET followup_sent = 1 WHERE id = ?', (email_id,))
                        
#                         conn.commit()
#                     flash(f"Follow-up email sent to {email['recipient_email']}", "success")
#                     return True
#             except Exception as e:
#                 flash(f"Error sending follow-up: {str(e)}", "error")
#                 return False

#         send_single_followup()
#         conn.close()
#         return redirect('/emails')
#     except Exception as e:
#         flash(f"Error processing follow-up: {str(e)}", "error")
#         return redirect('/emails')


@app.route('/send-followup/<int:email_id>', methods=['GET'])
def send_followup(email_id):
    try:
        conn = get_db_connection()

        # Conditionally use row_factory if using SQLite
        if not is_production:
            conn.row_factory = sqlite3.Row

        c = conn.cursor()

        # Use correct placeholder style
        if is_production:
            c.execute('SELECT * FROM emails WHERE id = %s', (email_id,))
        else:
            c.execute('SELECT * FROM emails WHERE id = ?', (email_id,))

        row = c.fetchone()

        if not row:
            flash(f"Email ID {email_id} not found", "error")
            return redirect('/emails')

        # Handle row access depending on DB type
        # if is_production:
        #     email = dict(zip([desc[0] for desc in c.description], row))
        # else:
        #     email = row

        # row is already a dict in production if DictCursor is used
        email = dict(row) if not is_production else row


        def send_single_followup():
            if email['followup_sent'] == 1:
                flash(f"Follow-up for email ID {email_id} was already sent", "warning")
                return False
            if not email['followup_body']:
                flash(f"Email ID {email_id} has no follow-up message", "error")
                return False

            try:
                sender_email = email['sender_email']
                sender_password = email['sender_password']
                # print("Email dict content:", email)
                # print(f"Logging in as: {sender_email}")
                # print(f"Password: {sender_password}")

                recipient_email = email['recipient_email']
                subject = f"Follow-up: {email['subject']}"
                body = f"Hello {email['recipient_name']},\n\n{email['followup_body']}"

                # Construct email
                msg = MIMEText(body)
                msg['Subject'] = subject
                msg['From'] = sender_email
                msg['To'] = recipient_email

                # Send using smtplib
                with smtplib.SMTP('smtp.gmail.com', 587) as server:
                    server.starttls()
                    server.login(sender_email, sender_password)
                    server.sendmail(sender_email, [recipient_email], msg.as_string())

                # Update followup_sent status
                with db_lock:
                    if is_production:
                        c.execute('UPDATE emails SET followup_sent = 1 WHERE id = %s', (email_id,))
                    else:
                        c.execute('UPDATE emails SET followup_sent = 1 WHERE id = ?', (email_id,))
                    conn.commit()

                flash(f"Follow-up email sent to {recipient_email}", "success")
                return True

            except Exception as e:
                traceback.print_exc()
                flash(f"Error sending follow-up: {str(e)}", "error")
                return False

        send_single_followup()
        conn.close()
        return redirect('/emails')

    except Exception as e:
        traceback.print_exc()
        flash(f"Error processing follow-up: {str(e)}", "error")
        return redirect('/emails')


# @app.route('/check-followups')
# def check_followups():
#     try:
#         conn = get_db_connection()
#         conn.row_factory = sqlite3.Row
#         c = conn.cursor()
#         now = datetime.now()
#         current_time = now.strftime("%Y-%m-%d %H:%M:%S")
#         c.execute('''
#             SELECT id, sender_email, sender_password, recipient_email, recipient_name, subject, followup_body 
#             FROM emails 
#             WHERE followup_date <= ? 
#             AND followup_sent = 0
#             AND followup_body IS NOT NULL
#         ''', (current_time,))
#         emails_to_followup = c.fetchall()
#         sent_count = 0
#         errors = []
#         for email in emails_to_followup:
#             email_id = email['id']
#             sender_email = email['sender_email']
#             sender_password = email['sender_password']
#             recipient_email = email['recipient_email']
#             recipient_name = email['recipient_name']
#             subject = email['subject']
#             followup_body = email['followup_body']
#             try:
#                 with app.app_context():
#                     mail_config = {
#                         'MAIL_SERVER': 'smtp.gmail.com',
#                         'MAIL_PORT': 587,
#                         'MAIL_USE_TLS': True,
#                         'MAIL_USE_SSL': False,
#                         'MAIL_USERNAME': sender_email,
#                         'MAIL_PASSWORD': sender_password,
#                         'MAIL_DEFAULT_SENDER': sender_email
#                     }
#                     mail_app = Flask(f"mail_app_{email_id}")
#                     for key, value in mail_config.items():
#                         mail_app.config[key] = value
#                     with mail_app.app_context():
#                         mail_instance = Mail(mail_app)
#                         followup_subject = f"Follow-up: {subject}"
#                         msg = Message(followup_subject, recipients=[recipient_email])
#                         msg.body = f"Hello {recipient_name},\n\n{followup_body}"
#                         mail_instance.send(msg)
                        
#                         # Use lock for database updates
#                         with db_lock:
#                             c.execute('UPDATE emails SET followup_sent = 1 WHERE id = ?', (email_id,))
#                             conn.commit()
#                         sent_count += 1
#             except Exception as e:
#                 errors.append(f"Error sending follow-up to {recipient_email}: {str(e)}")
#         conn.close()
#         if sent_count > 0:
#             flash(f"Manually sent {sent_count} follow-up emails", "success")
#         if errors:
#             for error in errors:
#                 flash(error, "error")
#         if sent_count == 0 and not errors:
#             flash("No follow-up emails needed to be sent at this time", "info")
#     except Exception as e:
#         flash(f"Error checking follow-ups: {str(e)}", "error")
#     return redirect('/server-status')



@app.route('/check-followups')
def check_followups():
    try:
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        now = datetime.now()
        current_time = now.strftime("%Y-%m-%d %H:%M:%S")
        c.execute('''
            SELECT id, sender_email, sender_password, recipient_email, recipient_name, subject, followup_body 
            FROM emails 
            WHERE followup_date <= ? 
            AND followup_sent = 0
            AND followup_body IS NOT NULL
        ''', (current_time,))
        emails_to_followup = c.fetchall()
        sent_count = 0
        errors = []

        for email in emails_to_followup:
            email_id = email['id']
            sender_email = email['sender_email']
            sender_password = email['sender_password']
            recipient_email = email['recipient_email']
            recipient_name = email['recipient_name']
            subject = email['subject']
            followup_body = email['followup_body']

            try:
                msg = MIMEText(f"Hello {recipient_name},\n\n{followup_body}")
                msg['Subject'] = f"Follow-up: {subject}"
                msg['From'] = sender_email
                msg['To'] = recipient_email

                with smtplib.SMTP('smtp.gmail.com', 587) as server:
                    server.starttls()
                    server.login(sender_email, sender_password)
                    server.sendmail(sender_email, recipient_email, msg.as_string())

                # Update followup_sent with lock
                with db_lock:
                    c.execute('UPDATE emails SET followup_sent = 1 WHERE id = ?', (email_id,))
                    conn.commit()
                sent_count += 1
            except Exception as e:
                errors.append(f"Error sending follow-up to {recipient_email}: {str(e)}")

        conn.close()
        if sent_count > 0:
            flash(f"Manually sent {sent_count} follow-up emails", "success")
        if errors:
            for error in errors:
                flash(error, "error")
        if sent_count == 0 and not errors:
            flash("No follow-up emails needed to be sent at this time", "info")

    except Exception as e:
        flash(f"Error checking follow-ups: {str(e)}", "error")

    return redirect('/server-status')




@app.route('/server-status')
def server_status():
    status = {
        'scheduler_running': scheduler_running,
        'server_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'database_path': DB_PATH
    }
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM emails")
        total_emails = c.fetchone()[0]
        status['total_emails'] = total_emails
        c.execute("SELECT COUNT(*) FROM emails WHERE followup_date IS NOT NULL AND followup_sent = 0")
        pending_followups = c.fetchone()[0]
        status['pending_followups'] = pending_followups
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('''
            SELECT id, sender_email, recipient_email, followup_date, sent_date
            FROM emails 
            WHERE followup_date IS NOT NULL AND followup_sent = 0
            ORDER BY followup_date
        ''')
        status['pending_followups_list'] = [dict(row) for row in c.fetchall()]
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute('''
            SELECT COUNT(*) FROM emails 
            WHERE followup_date <= ? AND followup_sent = 0
        ''', (current_time,))
        past_due = c.fetchone()[0]
        status['past_due_followups'] = past_due
        conn.close()
        status['database_connection'] = 'success'
    except Exception as e:
        status['database_connection'] = f'error: {str(e)}'
    return render_template('server_status.html', status=status)

def configure_logging():
    """Configure application logging"""
    log_level = logging.INFO if is_production else logging.DEBUG
    
    # Configure file handler
    if not os.path.exists(LOG_FOLDER):
        os.mkdir(LOG_FOLDER)
    
    log_file = os.path.join(LOG_FOLDER, 'emailapp.log')
    file_handler = RotatingFileHandler(log_file, maxBytes=1024000, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(log_level)
    
    # Configure console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s'
    ))
    
    # Add handlers to app logger
    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)
    app.logger.setLevel(log_level)
    
    # Set up werkzeug logger too
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.setLevel(log_level)
    werkzeug_logger.addHandler(file_handler)
    
    app.logger.info('Email Automation Tool startup in ' + 
                   ('PRODUCTION' if is_production else 'DEVELOPMENT') + ' mode')

# Update password storage and checking methods
def encrypt_password(password):
    """Encrypt password for storage"""
    return generate_password_hash(password)

def verify_password(stored_password, provided_password):
    """Verify password against stored hash"""
    return check_password_hash(stored_password, provided_password)

def send_email(sender_email, sender_password, recipient_email, recipient_name, subject, body, attachments=None):
    """Centralized email sending function with improved error handling and retries"""
    app.logger.info(f"Sending email to {recipient_email} from {sender_email}")
    
    try:
        # Create SMTP connection with timeout
        server = smtplib.SMTP('smtp.gmail.com', 587, timeout=30)
        server.starttls()
        server.login(sender_email, sender_password)
        
        # Create email message
        msg = MIMEText(f"Hello {recipient_name},\n\n{body}")
        msg['Subject'] = subject
        msg['From'] = sender_email
        msg['To'] = recipient_email
        
        # Add attachments if provided
        if attachments:
            for attachment_path in attachments:
                try:
                    with open(attachment_path, 'rb') as file:
                        part = MIMEBase('application', 'octet-stream')
                        part.set_payload(file.read())
                        encoders.encode_base64(part)
                        part.add_header('Content-Disposition', 
                                        f'attachment; filename="{os.path.basename(attachment_path)}"')
                        msg.attach(part)
                except Exception as att_err:
                    app.logger.error(f"Error attaching file {attachment_path}: {str(att_err)}")
        
        # Send email
        server.send_message(msg)
        server.quit()
        app.logger.info(f"Email sent successfully to {recipient_email}")
        return True, None
    
    except smtplib.SMTPAuthenticationError:
        app.logger.error(f"SMTP Authentication failed for {sender_email}")
        return False, "Email authentication failed. Check sender email and password."
    
    except smtplib.SMTPException as smtp_err:
        app.logger.error(f"SMTP error sending to {recipient_email}: {str(smtp_err)}")
        return False, f"SMTP error: {str(smtp_err)}"
    
    except Exception as e:
        app.logger.error(f"Error sending email to {recipient_email}: {str(e)}")
        return False, f"Error: {str(e)}"

# Add a custom error handler
@app.errorhandler(404)
def page_not_found(e):
    app.logger.info(f"404 error: {request.path}")
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    app.logger.error(f"500 error: {str(e)}")
    return render_template('500.html'), 500

# Add basic error templates
@app.route('/test-error/<error_type>')
def test_error(error_type):
    """Test route for error pages"""
    if error_type == '404':
        abort(404)
    elif error_type == '500':
        abort(500)
    else:
        return "Valid error types: 404, 500"

if __name__ == '__main__':
    if os.environ.get('FLASK_ENV') == 'production':
        configure_logging()
        print("Calling start_scheduler()...") 
        start_scheduler()
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get('FLASK_ENV') != 'production'
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
