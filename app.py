"""PayFlow - Mini Payment Gateway Simulator"""

import os
import random
import threading
import time
import uuid
from datetime import datetime

try:
    import mysql.connector
except ModuleNotFoundError as exc:
    raise ModuleNotFoundError(
        "mysql-connector-python is not installed. Run 'pip install -r requirements.txt'."
    ) from exc
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app     = Flask(__name__)
CORS(app)
DB_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "database": os.getenv("MYSQL_DATABASE", "payments"),
}


@app.route("/")
def home():
    return render_template("index.html")


# ================================================
# PART 5 - DB INFRASTRUCTURE
# ================================================

class MySQLCursorWrapper:
    def __init__(self, cursor):
        self.cursor = cursor

    def execute(self, query, params=None):
        self.cursor.execute(query.replace("?", "%s"), params)
        return self

    def executemany(self, query, seq_params):
        self.cursor.executemany(query.replace("?", "%s"), seq_params)
        return self

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

    def close(self):
        self.cursor.close()


class MySQLConnectionWrapper:
    def __init__(self, connection):
        self.connection = connection

    def cursor(self):
        return MySQLCursorWrapper(self.connection.cursor(dictionary=True))

    def execute(self, query, params=None):
        cursor = self.cursor()
        cursor.execute(query, params)
        cursor.close()

    def commit(self):
        self.connection.commit()

    def close(self):
        self.connection.close()


def get_server_connection():
    try:
        return mysql.connector.connect(
            host=DB_CONFIG["host"],
            port=DB_CONFIG["port"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
        )
    except mysql.connector.Error as exc:
        raise RuntimeError(
            "Unable to connect to MySQL server. Check MYSQL_HOST, MYSQL_PORT, "
            "MYSQL_USER, and MYSQL_PASSWORD in your environment or .env file."
        ) from exc


def get_db():
    try:
        return MySQLConnectionWrapper(mysql.connector.connect(**DB_CONFIG))
    except mysql.connector.Error as exc:
        raise RuntimeError(
            "Unable to connect to the MySQL database. Check MYSQL_DATABASE and "
            "your MySQL credentials in the environment or .env file."
        ) from exc


def init_db():
    server_conn = get_server_connection()
    server_cursor = server_conn.cursor()
    server_cursor.execute(
        f"CREATE DATABASE IF NOT EXISTS `{DB_CONFIG['database']}` "
        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )
    server_conn.commit()
    server_cursor.close()
    server_conn.close()

    conn   = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id VARCHAR(20) PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            pin VARCHAR(10) NOT NULL,
            balance DECIMAL(12, 2) NOT NULL DEFAULT 10000.0
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            payment_id VARCHAR(20) PRIMARY KEY,
            sender_id VARCHAR(20) NOT NULL,
            receiver_id VARCHAR(20) NOT NULL,
            amount DECIMAL(12, 2) NOT NULL,
            currency VARCHAR(10) NOT NULL DEFAULT 'INR',
            status VARCHAR(20) NOT NULL DEFAULT 'CREATED',
            failure_reason VARCHAR(100),
            refund_status VARCHAR(20) NOT NULL DEFAULT 'none',
            created_at VARCHAR(32) NOT NULL,
            updated_at VARCHAR(32) NOT NULL,
            FOREIGN KEY(sender_id)   REFERENCES users(id),
            FOREIGN KEY(receiver_id) REFERENCES users(id)
        )
    """)

    # Migration: add refund_status to existing databases that don't have it yet
    try:
        cursor.execute("ALTER TABLE payments ADD COLUMN refund_status VARCHAR(20) NOT NULL DEFAULT 'none'")
        conn.commit()
    except Exception:
        pass  # Column already exists - safe to ignore

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS refund_requests (
            refund_id VARCHAR(20) PRIMARY KEY,
            payment_id VARCHAR(20) NOT NULL,
            requester_id VARCHAR(20) NOT NULL,
            receiver_id VARCHAR(20) NOT NULL,
            amount DECIMAL(12, 2) NOT NULL,
            currency VARCHAR(10) NOT NULL DEFAULT 'INR',
            status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
            created_at VARCHAR(32) NOT NULL,
            updated_at VARCHAR(32) NOT NULL,
            FOREIGN KEY(payment_id)   REFERENCES payments(payment_id),
            FOREIGN KEY(requester_id) REFERENCES users(id),
            FOREIGN KEY(receiver_id)  REFERENCES users(id)
        )
    """)

    cursor.execute("SELECT COUNT(*) AS total FROM users")
    if cursor.fetchone()["total"] == 0:
        cursor.executemany(
            "INSERT INTO users (id, name, pin, balance) VALUES (?, ?, ?, ?)",
            [
                ("USER001", "Arjun Sharma", "1234",  50000.0),
                ("USER002", "Priya Patel",  "5678",  30000.0),
                ("USER003", "Ravi Kumar",   "9999",  75000.0),
                ("USER004", "Sneha Mehta",  "1111",  20000.0),
                ("USER005", "Demo User",    "0000", 150000.0),
            ]
        )

    conn.commit()
    cursor.close()
    conn.close()
    print("Database initialised.")


# ================================================
# PART 1 - AUTH ROUTES
# ================================================

@app.route("/api/auth", methods=["POST"])
def authenticate():
    """Verify user ID + PIN, return name & balance."""
    data    = request.get_json()
    user_id = data.get("userId", "").strip().upper()
    pin     = data.get("pin",    "").strip()

    if not user_id or not pin:
        return jsonify({"success": False, "message": "User ID and PIN are required"}), 400

    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, balance FROM users WHERE id=? AND pin=?", (user_id, pin))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if not user:
        return jsonify({"success": False, "message": "Invalid User ID or PIN"}), 401

    return jsonify({"success": True, "userId": user["id"],
                    "name": user["name"], "balance": float(user["balance"])})


@app.route("/api/users", methods=["GET"])
def list_users():
    """Return all users - id + name only (no PINs)."""
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM users ORDER BY name")
    users  = [{"id": r["id"], "name": r["name"]} for r in cursor.fetchall()]
    cursor.close()
    conn.close()
    return jsonify({"success": True, "users": users})


# ================================================
# PART 2 - PAYMENT CORE
# ================================================

def determine_outcome(sender_id, receiver_id, amount):
    """Rule-based + 15 % random failure engine."""
    conn   = get_db()
    cursor = conn.cursor()

    if amount <= 0:
        cursor.close()
        conn.close(); return False, "INVALID_AMOUNT"
    if amount > 100000:
        cursor.close()
        conn.close(); return False, "AMOUNT_EXCEEDS_LIMIT"

    cursor.execute("SELECT balance FROM users WHERE id=?", (sender_id,))
    sender = cursor.fetchone()
    if not sender or float(sender["balance"]) < amount:
        cursor.close()
        conn.close(); return False, "INSUFFICIENT_BALANCE"

    cursor.execute("SELECT id FROM users WHERE id=?", (receiver_id,))
    if not cursor.fetchone():
        cursor.close()
        conn.close(); return False, "INVALID_ACCOUNT"

    cursor.close()
    conn.close()

    if random.random() < 0.15:
        return False, random.choice(["BANK_SERVER_TIMEOUT", "NETWORK_ERROR", "DAILY_LIMIT_EXCEEDED"])

    return True, None


def process_payment_async(payment_id):
    """
    Simulates bank delay. Runs in a background thread.
    State machine: CREATED -> PROCESSING -> SUCCESS | FAILED
    """
    time.sleep(1)
    conn = get_db()
    now  = datetime.now().isoformat()
    conn.execute("UPDATE payments SET status='PROCESSING', updated_at=? WHERE payment_id=?",
                 (now, payment_id))
    conn.commit()

    cursor = conn.cursor()
    cursor.execute("SELECT * FROM payments WHERE payment_id=?", (payment_id,))
    payment = cursor.fetchone()
    cursor.close()

    time.sleep(2)
    success, reason = determine_outcome(
        payment["sender_id"], payment["receiver_id"], float(payment["amount"])
    )

    now = datetime.now().isoformat()
    if success:
        conn.execute("UPDATE users SET balance = balance - ? WHERE id=?",
                     (float(payment["amount"]), payment["sender_id"]))
        conn.execute("UPDATE users SET balance = balance + ? WHERE id=?",
                     (float(payment["amount"]), payment["receiver_id"]))
        conn.execute("UPDATE payments SET status='SUCCESS', updated_at=? WHERE payment_id=?",
                     (now, payment_id))
    else:
        conn.execute(
            "UPDATE payments SET status='FAILED', failure_reason=?, updated_at=? WHERE payment_id=?",
            (reason, now, payment_id)
        )

    conn.commit()
    conn.close()


@app.route("/api/payment/create", methods=["POST"])
def create_payment():
    """Create payment record (CREATED), kick off async processing thread."""
    data        = request.get_json()
    sender_id   = data.get("senderId",   "").strip().upper()
    receiver_id = data.get("receiverId", "").strip().upper()
    amount      = float(data.get("amount", 0))
    currency    = data.get("currency",   "INR").strip().upper()
    pin         = data.get("pin",        "").strip()

    conn   = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE id=? AND pin=?", (sender_id, pin))
    if not cursor.fetchone():
        cursor.close()
        conn.close()
        return jsonify({"success": False, "message": "Authentication failed. Wrong PIN."}), 401

    cursor.execute("SELECT id FROM users WHERE id=?", (receiver_id,))
    if not cursor.fetchone():
        cursor.close()
        conn.close()
        return jsonify({"success": False, "message": f"Receiver '{receiver_id}' not found"}), 404

    if sender_id == receiver_id:
        cursor.close()
        conn.close()
        return jsonify({"success": False, "message": "Cannot send money to yourself"}), 400

    payment_id = "PAY" + uuid.uuid4().hex[:10].upper()
    now        = datetime.now().isoformat()

    conn.execute("""
        INSERT INTO payments (payment_id, sender_id, receiver_id, amount, currency, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 'CREATED', ?, ?)
    """, (payment_id, sender_id, receiver_id, amount, currency, now, now))
    conn.commit()
    cursor.close()
    conn.close()

    thread = threading.Thread(target=process_payment_async, args=(payment_id,))
    thread.daemon = True
    thread.start()

    return jsonify({"success": True, "paymentId": payment_id,
                    "status": "CREATED", "message": "Payment initiated. Processing..."}), 201


# ================================================
# PART 3 - HISTORY & STATUS
# ================================================

@app.route("/api/payment/<payment_id>", methods=["GET"])
def get_payment_status(payment_id):
    """Fetch a single payment by ID. Also used by the frontend polling loop."""
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.*, s.name AS sender_name, r.name AS receiver_name
        FROM payments p
        JOIN users s ON p.sender_id   = s.id
        JOIN users r ON p.receiver_id = r.id
        WHERE p.payment_id = ?
    """, (payment_id.upper(),))
    payment = cursor.fetchone()
    cursor.close()
    conn.close()

    if not payment:
        return jsonify({"success": False, "message": "Payment not found"}), 404

    return jsonify({
        "success":       True,
        "paymentId":     payment["payment_id"],
        "senderId":      payment["sender_id"],
        "senderName":    payment["sender_name"],
        "receiverId":    payment["receiver_id"],
        "receiverName":  payment["receiver_name"],
        "amount":        float(payment["amount"]),
        "currency":      payment["currency"],
        "status":        payment["status"],
        "failureReason": payment["failure_reason"],
        "refundStatus":  payment["refund_status"],
        "createdAt":     payment["created_at"],
        "updatedAt":     payment["updated_at"],
    })


@app.route("/api/payments/user/<user_id>", methods=["GET"])
def get_user_payments(user_id):
    """All payments sent or received by a user, newest first."""
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.*, s.name AS sender_name, r.name AS receiver_name
        FROM payments p
        JOIN users s ON p.sender_id   = s.id
        JOIN users r ON p.receiver_id = r.id
        WHERE p.sender_id = ? OR p.receiver_id = ?
        ORDER BY p.created_at DESC
    """, (user_id.upper(), user_id.upper()))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    payments = [{
        "paymentId":     p["payment_id"],
        "senderId":      p["sender_id"],
        "senderName":    p["sender_name"],
        "receiverId":    p["receiver_id"],
        "receiverName":  p["receiver_name"],
        "amount":        float(p["amount"]),
        "currency":      p["currency"],
        "status":        p["status"],
        "failureReason": p["failure_reason"],
        "refundStatus":  p["refund_status"],
        "createdAt":     p["created_at"],
        "type":          "SENT" if p["sender_id"] == user_id.upper() else "RECEIVED"
    } for p in rows]

    return jsonify({"success": True, "payments": payments})


# ================================================
# PART 4 - REFUND SYSTEM
# ================================================

@app.route("/api/refund/request", methods=["POST"])
def request_refund():
    """
    Sender of a successful payment requests a refund.
    State: payment.refund_status -> 'pending'
    Rules: only sender, only SUCCESS, within 10-min window, not already requested.
    """
    data         = request.get_json()
    payment_id   = data.get("paymentId",   "").strip().upper()
    requester_id = data.get("requesterId", "").strip().upper()
    pin          = data.get("pin",         "").strip()

    conn   = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE id=? AND pin=?", (requester_id, pin))
    if not cursor.fetchone():
        cursor.close()
        conn.close()
        return jsonify({"success": False, "message": "Authentication failed. Wrong PIN."}), 401

    cursor.execute("SELECT * FROM payments WHERE payment_id=?", (payment_id,))
    payment = cursor.fetchone()

    if not payment:
        cursor.close()
        conn.close()
        return jsonify({"success": False, "message": "Payment not found"}), 404
    if payment["sender_id"] != requester_id:
        cursor.close()
        conn.close()
        return jsonify({"success": False, "message": "Only the original sender can request a refund"}), 403
    if payment["status"] != "SUCCESS":
        cursor.close()
        conn.close()
        return jsonify({"success": False, "message": "Refund only available for successful payments"}), 400

    # Check refund_status before the time window; terminal states block forever.
    if payment["refund_status"] in ("accepted", "rejected"):
        cursor.close()
        conn.close()
        return jsonify({"success": False,
                        "message": "Refund already processed. You cannot request a refund again."}), 400
    if payment["refund_status"] == "pending":
        cursor.close()
        conn.close()
        return jsonify({"success": False,
                        "message": "A refund request is already pending. Please wait for the receiver to respond."}), 400

    # Enforce 10-minute refund window
    elapsed = (datetime.now() - datetime.fromisoformat(payment["updated_at"])).total_seconds()
    if elapsed > 600:
        cursor.close()
        conn.close()
        return jsonify({"success": False,
                        "message": "Refund window expired. Refunds must be requested within 10 minutes."}), 400

    refund_id = "REF" + uuid.uuid4().hex[:10].upper()
    now       = datetime.now().isoformat()

    conn.execute("""
        INSERT INTO refund_requests
          (refund_id, payment_id, requester_id, receiver_id, amount, currency, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)
    """, (refund_id, payment_id, requester_id, payment["receiver_id"],
          float(payment["amount"]), payment["currency"], now, now))

    conn.execute("UPDATE payments SET refund_status='pending' WHERE payment_id=?", (payment_id,))
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"success": True, "refundId": refund_id,
                    "message": f"Refund request sent. Awaiting approval from {payment['receiver_id']}."}), 201


@app.route("/api/refund/pending/<user_id>", methods=["GET"])
def get_pending_refunds(user_id):
    """Refund requests waiting for this user's approval."""
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.*, req.name AS requester_name, rec.name AS receiver_name
        FROM refund_requests r
        JOIN users req ON r.requester_id = req.id
        JOIN users rec ON r.receiver_id  = rec.id
        WHERE r.receiver_id=? AND r.status='PENDING'
        ORDER BY r.created_at DESC
    """, (user_id.upper(),))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    refunds = [{"refundId": r["refund_id"], "paymentId": r["payment_id"],
                "requesterId": r["requester_id"], "requesterName": r["requester_name"],
                "receiverId": r["receiver_id"],   "receiverName": r["receiver_name"],
                "amount": float(r["amount"]), "currency": r["currency"],
                "status": r["status"], "createdAt": r["created_at"]} for r in rows]

    return jsonify({"success": True, "refunds": refunds})


@app.route("/api/refund/all/<user_id>", methods=["GET"])
def get_all_refunds(user_id):
    """All refunds where user is requester OR receiver."""
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.*, req.name AS requester_name, rec.name AS receiver_name
        FROM refund_requests r
        JOIN users req ON r.requester_id = req.id
        JOIN users rec ON r.receiver_id  = rec.id
        WHERE r.requester_id=? OR r.receiver_id=?
        ORDER BY r.created_at DESC
    """, (user_id.upper(), user_id.upper()))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    refunds = [{"refundId": r["refund_id"], "paymentId": r["payment_id"],
                "requesterId": r["requester_id"], "requesterName": r["requester_name"],
                "receiverId": r["receiver_id"],   "receiverName": r["receiver_name"],
                "amount": float(r["amount"]), "currency": r["currency"],
                "status": r["status"], "createdAt": r["created_at"],
                "role": "REQUESTED" if r["requester_id"] == user_id.upper() else "TO_APPROVE"
               } for r in rows]

    return jsonify({"success": True, "refunds": refunds})


@app.route("/api/refund/action", methods=["POST"])
def action_refund():
    """
    Receiver approves or rejects a refund.
    ACCEPT -> transfers money back, sets payment.refund_status = 'accepted'
    REJECT -> sets payment.refund_status = 'rejected'
    """
    data      = request.get_json()
    refund_id = data.get("refundId", "").strip().upper()
    user_id   = data.get("userId",   "").strip().upper()
    pin       = data.get("pin",      "").strip()
    action    = data.get("action",   "").strip().upper()

    if action not in ("ACCEPT", "REJECT"):
        return jsonify({"success": False, "message": "Action must be ACCEPT or REJECT"}), 400

    conn   = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE id=? AND pin=?", (user_id, pin))
    if not cursor.fetchone():
        cursor.close()
        conn.close()
        return jsonify({"success": False, "message": "Authentication failed. Wrong PIN."}), 401

    cursor.execute("SELECT * FROM refund_requests WHERE refund_id=?", (refund_id,))
    refund = cursor.fetchone()

    if not refund:
        cursor.close()
        conn.close()
        return jsonify({"success": False, "message": "Refund not found"}), 404
    if refund["receiver_id"] != user_id:
        cursor.close()
        conn.close()
        return jsonify({"success": False, "message": "Only the receiver can act on this request"}), 403
    if refund["status"] != "PENDING":
        cursor.close()
        conn.close()
        return jsonify({"success": False, "message": f"Refund is already {refund['status']}"}), 400

    now = datetime.now().isoformat()

    if action == "ACCEPT":
        cursor.execute("SELECT balance FROM users WHERE id=?", (user_id,))
        rec = cursor.fetchone()
        if not rec or float(rec["balance"]) < float(refund["amount"]):
            cursor.close()
            conn.close()
            return jsonify({"success": False, "message": "Insufficient balance to process refund"}), 400

        conn.execute("UPDATE users SET balance = balance - ? WHERE id=?",
                     (float(refund["amount"]), refund["receiver_id"]))
        conn.execute("UPDATE users SET balance = balance + ? WHERE id=?",
                     (float(refund["amount"]), refund["requester_id"]))
        conn.execute("UPDATE refund_requests SET status='ACCEPTED', updated_at=? WHERE refund_id=?",
                     (now, refund_id))
        conn.execute("UPDATE payments SET refund_status='accepted' WHERE payment_id=?",
                     (refund["payment_id"],))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"success": True,
                        "message": f"Refund of Rs. {float(refund['amount']):.2f} accepted and transferred back."})
    else:
        conn.execute("UPDATE refund_requests SET status='REJECTED', updated_at=? WHERE refund_id=?",
                     (now, refund_id))
    conn.execute("UPDATE payments SET refund_status='rejected' WHERE payment_id=?",
                 (refund["payment_id"],))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"success": True, "message": "Refund request rejected."})


# ================================================
# PART 5 - ANALYTICS ROUTE
# ================================================

@app.route("/api/summary", methods=["GET"])
def transaction_summary():
    """Global transaction analytics dashboard."""
    conn   = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as total FROM payments")
    total = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as c FROM payments WHERE status='SUCCESS'")
    success = cursor.fetchone()["c"]

    cursor.execute("SELECT COUNT(*) as c FROM payments WHERE status='FAILED'")
    failed = cursor.fetchone()["c"]

    cursor.execute("SELECT COUNT(*) as c FROM payments WHERE status IN ('CREATED','PROCESSING')")
    pending = cursor.fetchone()["c"]

    cursor.execute("""
        SELECT failure_reason, COUNT(*) as count
        FROM payments
        WHERE status='FAILED' AND failure_reason IS NOT NULL
        GROUP BY failure_reason
        ORDER BY count DESC
    """)
    failure_breakdown = {row["failure_reason"]: row["count"] for row in cursor.fetchall()}

    cursor.execute("SELECT SUM(amount) as total FROM payments WHERE status='SUCCESS'")
    total_volume = cursor.fetchone()["total"] or 0

    cursor.close()
    conn.close()

    return jsonify({"success": True, "summary": {
        "total":            total,
        "success":          success,
        "failed":           failed,
        "pending":          pending,
        "totalVolume":      round(float(total_volume), 2),
        "failureBreakdown": failure_breakdown,
    }})


# ================================================
# ENTRY POINT
# ================================================

if __name__ == "__main__":
    init_db()
    print("\nPayFlow running at http://localhost:5000")
    print("Demo: USER001/1234  USER002/5678  USER003/9999  USER004/1111  USER005/0000")
    print("-" * 50)
    app.run(debug=True, port=5000)
