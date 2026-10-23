#!/usr/bin/env python3
"""
Seed script for Fraud Alert Assistant.
Populates MongoDB with 150 synthetic fraud alerts according to specifications:
- Database: bankdemo
- Collection: fraud_alerts
- Status distribution: ~60% False Positive (90), ~15% Confirmed Fraud (23), ~25% Open (37)
- Realistic notes with names, phone numbers, and emails
- Relevant indexes created on key query fields
"""

import os
import random
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv, find_dotenv
from pymongo import MongoClient, ASCENDING

# 1. Load environment variables
load_dotenv(find_dotenv(usecwd=True))

MONGO_URI = (
    os.getenv("MONGODB_URI")
    or os.getenv("mongodb_uri")
    or "mongodb://127.0.0.1:27017"
)
DB_NAME = (
    os.getenv("MONGODB_DATABASE")
    or os.getenv("MONGODB_DB")
    or os.getenv("mongodb")
    or "bankdemo"
)
# Sanitize if DB_NAME has a space like 'bank demo'
if DB_NAME == "bank demo":
    DB_NAME = "bankdemo"

COLLECTION_NAME = (
    os.getenv("MONGODB_COLLECTION")
    or os.getenv("mongodn_collection")
    or os.getenv("mongodb_collection")
    or "fraud_alerts"
)

# Reference data pools
ALERT_TYPES = [
    "UNUSUAL_TRANSACTION_SPIKE",
    "RAPID_SUCCESSION_TRANSFERS",
    "GEO_VELOCITY_MISMATCH",
    "HIGH_RISK_MERCHANT_CATEGORY",
    "NEW_UNRECOGNIZED_DEVICE_LOGIN",
    "SUSPICIOUS_ACCOUNT_TAKEOVER_ATTEMPT",
    "LARGE_INTERNATIONAL_WIRE",
    "CARD_NOT_PRESENT_VELOCITY",
    "ATM_SUSPICIOUS_PIN_RETRIES",
    "CRYPTO_OFFRAMP_SURGE"
]

RULES_POOL = [
    "RULE_GEO_IP_DISTANCE_GT_500KM",
    "RULE_TRANSACTION_VELOCITY_5X_AVG",
    "RULE_NEW_BENEFICIARY_LARGE_TRANSFER",
    "RULE_DEVICE_FINGERPRINT_MISMATCH",
    "RULE_OFF_HOURS_HIGH_VALUE_TX",
    "RULE_MERCHANT_MCC_HIGH_RISK_GAMBLING",
    "RULE_FAILED_PASSWORD_THEN_TRANSFER",
    "RULE_ROUND_DOLLAR_AMOUNT_PATTERN",
    "RULE_FOREIGN_CARD_NOT_PRESENT"
]

MERCHANTS = [
    ("Amazon US", "E-Commerce"),
    ("Binance Global", "Crypto Exchange"),
    ("Best Buy Electronics", "Retail"),
    ("Air France Booking", "Travel"),
    ("Apple Store Soho", "Electronics"),
    ("Grand Casino Macau", "Gambling"),
    ("Shell Gas Station", "Automotive"),
    ("Wire to PrivatBank Zurich", "Banking"),
    ("Walmart Supercenter", "Retail"),
    ("Western Union Transfer", "Remittance"),
    ("Coinbase Inc", "Crypto Exchange"),
    ("Target Online", "E-Commerce")
]

ANALYSTS = [
    "analyst.patel@bankdemo.com",
    "analyst.chen@bankdemo.com",
    "analyst.rodriguez@bankdemo.com",
    "analyst.miller@bankdemo.com",
    "analyst.kowalski@bankdemo.com"
]

SAMPLE_NOTES = [
    "Customer Robert Jenkins (+1-555-019-4821, rjenkins@example.com) verified transaction via SMS two-factor auth. Legitimate business purchase while traveling.",
    "Analyst note: Contacted cardholder Maria Gomez (phone: +1-555-234-5678, email: mgomez_91@samplemail.com). Customer confirmed card was compromised during recent trip.",
    "Cardholder David Kim (+1-555-876-5432, david.kim@fintechcorp.io) initiated dispute for unauthorized digital wallet binding from IP 185.220.101.5.",
    "Sarah Connor (Compliance Lead, ext: 4022, sarah.connor@bankdemo.com) reviewed KYC documents; cleared alert as recurring payroll disbursement.",
    "Suspicious inbound caller claiming to be Michael Brown (+1-555-349-8812, brown.m@fakeprovider.net) failed security verification questions.",
    "Senior Analyst Liam Vance (lvance@bankdemo.com) reported cardholder Alex Rivera (+1-555-912-3847, a.rivera@globalnet.org) was victim of SIM swap attack.",
    "Inbound verification: Emily Zhang (+1-555-671-8920, emily.zhang@techfirm.co) confirmed she authorized the large overseas hotel reservation.",
    "Case transferred to Financial Intelligence Unit. Contact point: Inspector Carlos Silva (+1-555-782-9011, csilva@lawenforce.gov)."
]

def generate_alert(index: int, status: str) -> dict:
    alert_id = f"ALT-{1000 + index:04d}"
    alert_type = random.choice(ALERT_TYPES)
    
    # Correlate risk score and risk level to status
    if status == "False Positive":
        risk_score = round(random.uniform(15.0, 58.0), 1)
        risk_level = "LOW" if risk_score < 35 else "MEDIUM"
        sar_review_flag = False
        analyst = random.choice(ANALYSTS)
    elif status == "Confirmed Fraud":
        risk_score = round(random.uniform(75.0, 99.5), 1)
        risk_level = "HIGH" if risk_score < 88 else "CRITICAL"
        sar_review_flag = random.random() < 0.85  # 85% need SAR review
        analyst = random.choice(ANALYSTS)
    else:  # Open / In Review
        risk_score = round(random.uniform(40.0, 85.0), 1)
        risk_level = "MEDIUM" if risk_score < 65 else "HIGH"
        sar_review_flag = risk_score > 75
        analyst = random.choice(ANALYSTS + [None])

    # Dates
    days_ago = random.randint(1, 30)
    created_at = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=random.randint(0, 23), minutes=random.randint(0, 59))
    sla_due = created_at + timedelta(hours=random.choice([4, 12, 24, 48]))

    # Transaction
    merchant_name, category = random.choice(MERCHANTS)
    amount = round(random.uniform(45.0, 18500.0), 2)
    currency = random.choice(["USD", "USD", "USD", "EUR", "GBP", "CAD"])

    tx_details = {
        "transaction_id": f"TXN-{random.randint(10000000, 99999999)}",
        "amount": amount,
        "currency": currency,
        "merchant": merchant_name,
        "category": category,
        "channel": random.choice(["ONLINE", "POS_CHIP", "ATM", "WIRE", "MOBILE_APP"]),
        "location": random.choice(["New York, USA", "London, UK", "Paris, France", "Tokyo, Japan", "Toronto, Canada", "Berlin, Germany"]),
        "ip_address": f"{random.randint(24, 210)}.{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}"
    }

    # Triggered rules
    num_rules = random.randint(1, 3)
    triggered_rules = random.sample(RULES_POOL, num_rules)

    # Customer ref
    cust_id = f"CUST-{random.randint(10000, 99999)}"

    # Notes with fake PII (names, phones, emails) in some notes
    notes = []
    if index % 4 == 0:
        notes.append(random.choice(SAMPLE_NOTES))
    elif status == "False Positive":
        notes.append("Automated rule triggered; customer transaction profile historically consistent.")
    elif status == "Confirmed Fraud":
        notes.append("Account frozen. Card re-issuance triggered. Awaiting dispute settlement.")
    else:
        notes.append("Queued for secondary fraud triage. Verification in progress.")

    # Decision history
    decision_history = [
        {
            "timestamp": created_at.isoformat(),
            "action": "ALERT_TRIGGERED",
            "actor": "SYSTEM_RULE_ENGINE",
            "comment": f"Alert auto-generated with risk score {risk_score}"
        }
    ]

    if status != "Open":
        decision_time = created_at + timedelta(hours=random.randint(1, 6))
        decision_history.append({
            "timestamp": decision_time.isoformat(),
            "action": "CLOSED_FALSE_POSITIVE" if status == "False Positive" else "CONFIRMED_FRAUD_ESCALATED",
            "actor": analyst or "lead.analyst@bankdemo.com",
            "comment": "Verified as false positive by customer contact." if status == "False Positive" else "Confirmed fraudulent activity, card blocked."
        })

    return {
        "alert_id": alert_id,
        "alert_type": alert_type,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "status": status,
        "triggered_rules": triggered_rules,
        "transaction_details": tx_details,
        "customer_ref": cust_id,
        "assigned_analyst": analyst,
        "created_at": created_at,
        "sla_due": sla_due,
        "notes": notes,
        "decision_history": decision_history,
        "sar_review_flag": sar_review_flag
    }

def main():
    print(f"Connecting to MongoDB at {MONGO_URI}...")
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]

    # Target 150 items: 60% (90) False Positive, 15% (23) Confirmed Fraud, 25% (37) Open
    num_fp = 90
    num_fraud = 23
    num_open = 37
    total_target = num_fp + num_fraud + num_open  # 150

    status_list = (
        ["False Positive"] * num_fp +
        ["Confirmed Fraud"] * num_fraud +
        ["Open"] * num_open
    )
    random.shuffle(status_list)

    alerts = [generate_alert(i + 1, status) for i, status in enumerate(status_list)]

    # Clean existing data in collection to avoid duplicates if re-running
    collection.delete_many({})

    # Insert documents
    result = collection.insert_many(alerts)
    inserted_count = len(result.inserted_ids)

    # Create Indexes
    collection.create_index([("alert_id", ASCENDING)], unique=True)
    collection.create_index([("status", ASCENDING)])
    collection.create_index([("risk_score", ASCENDING)])
    collection.create_index([("customer_ref", ASCENDING)])
    collection.create_index([("created_at", ASCENDING)])

    # Verification counts
    count_fp = collection.count_documents({"status": "False Positive"})
    count_fraud = collection.count_documents({"status": "Confirmed Fraud"})
    count_open = collection.count_documents({"status": "Open"})
    indexes = collection.index_information()

    print("\n" + "=" * 50)
    print("MongoDB Seeding Summary")
    print("=" * 50)
    print(f"Database:          {DB_NAME}")
    print(f"Collection:        {COLLECTION_NAME}")
    print(f"Inserted:          {inserted_count}")
    print(f" - False Positive: {count_fp} ({count_fp / inserted_count * 100:.1f}%)")
    print(f" - Confirmed Fraud:{count_fraud} ({count_fraud / inserted_count * 100:.1f}%)")
    print(f" - Open:           {count_open} ({count_open / inserted_count * 100:.1f}%)")
    print("\nCreated Indexes:")
    for idx_name in indexes:
        print(f" - {idx_name}")
    print("=" * 50)

if __name__ == "__main__":
    main()
