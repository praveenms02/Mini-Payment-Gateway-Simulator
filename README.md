# Northern-Trust-hackathon-Project

# Mini-Payment-Gateway-Simulator

Northern Trust hackathon project

A full-stack payment gateway simulation built by a team of 5. It mimics real UPI-style payments with async processing, random bank failures, live status polling, and a multi-party refund approval system. Built with Flask, MySQL, and vanilla JavaScript.

---

# Quick Note Before You Start

After you log in, the dashboard opens on the create payment tab by default. Scroll down after login to see the Receiver ID field, Amount, PIN input, and the Send Payment button.

---

# Getting Started

### Prerequisites

- Python 3.8 or higher
- pip
- MySQL Server

### Installation

```bash
git clone https://github.com/YOUR_ORG/payflow.git
cd payflow
pip install -r requirements.txt
```

Set these environment variables before running the app:

```bash
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=payments
```

Then run:

```bash
python app.py
```

Open your browser and go to: `http://localhost:5000`

The MySQL database and tables are created automatically on first run, with 5 demo accounts seeded for testing.

---

# Demo Accounts

Use any of these to log in and test the app:

| User ID | PIN  | Name         | Starting Balance |
| ------- | ---- | ------------ | ---------------- |
| USER001 | 1234 | Arjun Sharma | Rs. 50,000       |
| USER002 | 5678 | Priya Patel  | Rs. 30,000       |
| USER003 | 9999 | Ravi Kumar   | Rs. 75,000       |
| USER004 | 1111 | Sneha Mehta  | Rs. 20,000       |
| USER005 | 0000 | Demo User    | Rs. 1,50,000     |

---

# Features

# Send Money

Enter a receiver's User ID, an amount, and confirm with your PIN. The payment goes through a simulated bank pipeline with a deliberate 3-second delay and a 15% random failure rate to mimic real banking behavior. A live modal shows status changes from `CREATED -> PROCESSING -> SUCCESS` or `FAILED`.

If a payment fails, a Retry button pre-fills the form so you can try again without re-entering everything.

# Transaction History

See every payment you have sent or received. Sent payments show in red, received payments show in green. Successful sent payments within the last 10 minutes show a live countdown refund button.

# Check Payment Status

Look up any payment by its ID in the format `PAY` followed by 10 characters. Useful for checking payments you did not initiate or for debugging.

# Analytics

A global view of all transactions, including total count, success and failure split, total processed volume, and a chart-ready failure breakdown.

# Refunds

A two-party refund system. The sender requests a refund, the receiver gets notified and must approve or reject it. Both sides confirm with their PIN.

Rules:

- Only the original sender can request
- Only works on successful payments
- Must be requested within 10 minutes of payment completion
- One refund request per payment, with no duplicates
- The receiver must have enough balance to approve

---

# Payment State Machine

Every payment moves through these states:

```text
CREATED -> PROCESSING -> SUCCESS
                       -> FAILED
```

- `CREATED`: payment record saved and background thread started
- `PROCESSING`: bank picked it up
- `SUCCESS`: money transferred between balances
- `FAILED`: rejected by the simulated bank engine

Failure reasons include `INSUFFICIENT_BALANCE`, `BANK_SERVER_TIMEOUT`, `NETWORK_ERROR`, `DAILY_LIMIT_EXCEEDED`, `INVALID_AMOUNT`, and `AMOUNT_EXCEEDS_LIMIT`.

---

# Refund State Machine

```text
payment.refund_status: none -> pending -> accepted
                                  -> rejected
```

The refund column in transaction history reflects this in real time without a page refresh.

---

# Database Schema

Three tables are stored in MySQL and created automatically on first run.

**users**

```text
id       VARCHAR(20)   PRIMARY KEY
name     VARCHAR(100)
pin      VARCHAR(10)
balance  DECIMAL(12,2) DEFAULT 10000.0
```

**payments**

```text
payment_id      VARCHAR(20)   PRIMARY KEY
sender_id       VARCHAR(20)   -> users.id
receiver_id     VARCHAR(20)   -> users.id
amount          DECIMAL(12,2)
currency        VARCHAR(10)   DEFAULT 'INR'
status          VARCHAR(20)   DEFAULT 'CREATED'
failure_reason  VARCHAR(100)  NULL
refund_status   VARCHAR(20)   DEFAULT 'none'
created_at      VARCHAR(32)
updated_at      VARCHAR(32)
```

**refund_requests**

```text
refund_id      VARCHAR(20)   PRIMARY KEY
payment_id     VARCHAR(20)   -> payments.payment_id
requester_id   VARCHAR(20)   -> users.id
receiver_id    VARCHAR(20)   -> users.id
amount         DECIMAL(12,2)
currency       VARCHAR(10)   DEFAULT 'INR'
status         VARCHAR(20)   DEFAULT 'PENDING'
created_at     VARCHAR(32)
updated_at     VARCHAR(32)
```

---

# API Reference

### Auth

| Method | Endpoint     | Description |
| ------ | ------------ | ----------- |
| POST   | `/api/auth`  | Verify User ID and PIN. Returns name and balance. |
| GET    | `/api/users` | List all users with id and name only. |

### Payments

| Method | Endpoint                  | Description |
| ------ | ------------------------- | ----------- |
| POST   | `/api/payment/create`     | Create a new payment and start processing. |
| GET    | `/api/payment/<id>`       | Get status of a single payment. |
| GET    | `/api/payments/user/<id>` | Get all payments for a user. |

### Refunds

| Method | Endpoint                   | Description |
| ------ | -------------------------- | ----------- |
| POST   | `/api/refund/request`      | Sender requests a refund with PIN verification. |
| GET    | `/api/refund/pending/<id>` | Get refund requests waiting for this user's approval. |
| GET    | `/api/refund/all/<id>`     | Get all refunds related to a user. |
| POST   | `/api/refund/action`       | Receiver approves or rejects a refund with PIN verification. |

### Analytics

| Method | Endpoint       | Description |
| ------ | -------------- | ----------- |
| GET    | `/api/summary` | Global stats for transaction totals, status split, volume, and failure breakdown. |

---

# Project Structure

```text
payflow/
|-- app.py
|-- requirements.txt
|-- .env.example
|-- static/
|   |-- script.js
|   `-- styles.css
`-- templates/
    `-- index.html
```

# Known Quirks

- Scroll down after login because the Send Money form loads below the visible area.
- The 15% failure rate is intentional to simulate real bank errors.
- The 10-minute refund window is real and enforced in the backend.
- The app creates the configured MySQL database and tables automatically if they do not already exist.

---

# requirements.txt

```text
flask>=2.3.0
flask-cors>=4.0.0
mysql-connector-python>=9.0.0
python-dotenv>=1.0.1
```
