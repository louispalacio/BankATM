from flask import Flask, render_template, request, url_for, session, redirect, Response , flash
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json
import os
import csv
import io
from reportlab.platypus import SimpleDocTemplate, Table
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
import random
import smtplib
from email.mime.text import MIMEText

EMAIL_ADDRESS = "jokermamba7@gmail.com"
EMAIL_PASSWORD = "ikrn efad zell xchv"

def send_email_notif(receiver, subject, message):
    
    msg = MIMEText(message)
    msg["Subject"] = subject
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = receiver
    
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(EMAIL_ADDRESS,EMAIL_PASSWORD)
            smtp.send_message(msg)
    except Exception as e:
        print("Email error:", e)

app = Flask(__name__)
app.secret_key = 'privateKey'

DATA_FILE = 'storage.json'
accounts = []


class Account:
    def __init__(self, name, balance, email, pin, account_number=None, is_hashed = False):
        self.name = name
        self.balance = balance
        self.email = email
        self.account_number = account_number if account_number else self.generate_account_number()
        
        if is_hashed:
            self.__pin_hash= pin
        else:
            self.__pin_hash = generate_password_hash(str(pin)) 
        self.transaction = []

   
    def _get_timestamp(self):
        return datetime.now().strftime("%Y-%m-%dT%H:%M")

    @staticmethod
    def generate_account_number():
        return str(random.randint(100000000000,999999999999))

    def verify_pin(self, pin):
        return check_password_hash(self.__pin_hash, str(pin))

    def deposit(self, amount):
        if amount > 0:
            self.balance += amount
            self.transaction.append(f"[{self._get_timestamp()}] | Deposit: ${amount} to account")
            return True
        return False

    def withdraw(self, amount):
        if 0 < amount <= self.balance:
            self.balance -= amount
            self.transaction.append(f"[{self._get_timestamp()}] | Withdraw: ${amount} to account")
            return True
        return False

    def fund_transfer(self, receiver, amount):
        if amount <= 0 or amount > self.balance:
            return False
        time_str = self._get_timestamp()
        self.balance -= amount
        receiver.balance += amount
        self.transaction.append(f"[{ time_str }]Transferred: ${amount} to {receiver.name}.")
        receiver.transaction.append(f"[{ time_str }] Receiced ${amount} from {self.name}.")
        return True

    def to_dict(self):
        return {
            'name': self.name,
            'balance': self.balance,
            'email': self.email,
            'account_number': self.account_number,
            'pin': self.__pin_hash,
            'transaction': self.transaction
        }

    @staticmethod
    def from_dict(data):
        acc = Account(data['name'], data['balance'], data['email'], data['pin'], data['account_number'], is_hashed = True)
        acc.transaction = data.get('transaction', [])
        return acc

def load_accounts():
    global accounts
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as file:
                content = file.read()
                if not content:
                    accounts = []
                    return
                data = json.loads(content)
                accounts = [Account.from_dict(acc) for acc in data]

        except (json.JSONDecodeError, ValueError):
           accounts = []
                # data = json.load(file)
                # accounts = [Account.from_dict(acc) for acc in data]


def save_accounts():
    with open(DATA_FILE, 'w') as file:
        json.dump([acc.to_dict() for acc in accounts], file)


def find_account(name):
    for acc in accounts:
        if acc.name == name:
            return acc
    return None


load_accounts()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/create', methods=['GET', 'POST'])
def create():
    if request.method == 'POST':
        name = request.form['name']
        balance = float(request.form['balance'])
        email = request.form['email']
        pin = request.form['pin']

        if find_account(name):
            flash("Account already exists", 'error')
            return redirect(url_for('create')) 

        accounts.append(Account(name, balance, email, pin))
        save_accounts()
        flash('Account Created Successfully', 'success')
        return redirect(url_for('index'))

    return render_template('create_account.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        name = request.form['name']
        pin = request.form['pin']

        account = find_account(name)
        if account and account.verify_pin(pin):
            session['user'] = name
            flash(f'Logged in as {name}', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid Login Credentials','error')
        return render_template('login.html')

    return render_template('login.html')


@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))

    account = find_account(session['user'])

    if request.method == 'POST':
        action = request.form['action']
        amount = float(request.form['amount'])

        if action == "deposit":
            if account.deposit(amount):
                send_email_notif( 
                                 account.email,
                                 "Deposit Successful",
                                 f"""
                                 Dear {account.name},
                                 
                                 Your account has been credited
                                 with Amount: ${amount}
                                 New Balance: ${account.balance}
                                 
                                 Thank You!
                                 This is an auto-generated email""")

        # if action == 'deposit':
        #     account.deposit(amount)
            
        elif action == 'withdraw':
            account.withdraw(amount)

        save_accounts()

    return render_template('dashboard.html', 
                           balance = account.balance, 
                           transaction = account.transaction, 
                           account=account)

@app.route('/transfer', methods=['GET', 'POST'])
def transfer():
    if 'user' not in session:
        return redirect(url_for('login'))

    sender = find_account(session['user'])

    if request.method == 'POST': 
        receiver_name = request.form['receiver']
        amount = float(request.form['amount'])

        receiver = find_account(receiver_name)

        if receiver and sender.fund_transfer(receiver, amount):
            save_accounts()
            return redirect(url_for('dashboard'))

        return 'Transfer Failed'

    return render_template('transfer.html', account=accounts)

@app.route('/logout')
def logout():
    session.pop('user', None)
    flash('Successfully Logged Out', 'success')
    return redirect(url_for('login'))

@app.route('/download_statement')
def download_statement():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    account = find_account(session['user'])
    if not account:
        flash('Account not Found', 'error')
        return redirect(url_for('login'))
    
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(['Date/Time', 'Transaction Details'])

    for tx in account.transaction:
        if "]" in tx:
            # [2026-02-28T03:28], Rece
            parts = tx.split("]", 1)
            date = parts[0].replace("[","")
            details = parts[1].strip()
            writer.writerow([date, details])
        else:
            writer.writerow(["N/A", tx])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=soa.csv"}
    )

@app.route("/download_pdf_format")
def download_pdf_format():

    if "user" not in session:
        return redirect(url_for("login"))
    
    account = find_account(session["user"])
    buffer = io.BytesIO()
    data = [["Date/Time", "Transaction Details"]]

    for tx in account.transaction:
        if "]" in tx:
            # [2026-02-28T03:28], Rece
            parts = tx.split("]", 1)
            date = parts[0].replace("[","")
            details = parts[1].strip()
            data.append([date, details])

    pdf = SimpleDocTemplate(buffer, pagesize=letter)
    table = Table(data)
    pdf.build([table])

    buffer.seek(0)

    return Response(
        buffer.getvalue(),
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=soa.csv"}
    )

@app.route("/admin")
def admin():
    if "user" not in session:
        return redirect(url_for("login"))
    if session["user"] != "admin_user":
        return "Unauthorized"
    
    return render_template("admin.html", account = accounts)

@app.route("/my_profile")
def profile():
    if "user" not in session:
        return redirect(url_for("login"))

    account = find_account(session["user"])
    
    return render_template("profile.html", account = account)

if __name__ == '__main__':
    app.run(debug=True)
