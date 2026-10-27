
import streamlit as st
import pandas as pd
import joblib
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import text

# Neon connection string: paste it here, or set DATABASE_URL in Streamlit secrets
try:
    DATABASE_URL = st.secrets["DATABASE_URL"]
except Exception:
    DATABASE_URL = "postgresql+psycopg2://USER:PASSWORD@HOST/neondb?sslmode=require"

# Timezone used to display prediction times
APP_TIMEZONE = "Africa/Lagos"

model = joblib.load("meshach.pkl")


# ---------- Database ----------

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS predictions (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    transaction_type TEXT NOT NULL,
    amount DOUBLE PRECISION,
    old_balance_orig DOUBLE PRECISION,
    new_balance_orig DOUBLE PRECISION,
    old_balance_dest DOUBLE PRECISION,
    new_balance_dest DOUBLE PRECISION,
    sender_change DOUBLE PRECISION,
    receiver_change DOUBLE PRECISION,
    fraud_probability DOUBLE PRECISION,
    risk_level TEXT NOT NULL
)
"""


@st.cache_resource
def create_table(_conn):
    with _conn.session as s:
        s.execute(text(CREATE_TABLE_SQL))
        s.commit()


def get_connection():
    conn = st.connection("neon", type="sql", url=DATABASE_URL, pool_pre_ping=True)
    create_table(conn)
    return conn


def save_prediction(row):
    conn = get_connection()
    with conn.session as s:
        s.execute(
            text("""
                INSERT INTO predictions (
                    transaction_type, amount,
                    old_balance_orig, new_balance_orig,
                    old_balance_dest, new_balance_dest,
                    sender_change, receiver_change,
                    fraud_probability, risk_level
                ) VALUES (
                    :transaction_type, :amount,
                    :old_balance_orig, :new_balance_orig,
                    :old_balance_dest, :new_balance_dest,
                    :sender_change, :receiver_change,
                    :fraud_probability, :risk_level
                )
            """),
            row,
        )
        s.commit()


def load_history():
    conn = get_connection()
    return conn.query("SELECT * FROM predictions ORDER BY created_at DESC", ttl=0)


# ---------- Helpers ----------

def humanize_time(ts, now=None):
    """Show a time as 'Just now', '5 min ago', 'Today, 2:30 PM', 'Yesterday, 9:10 AM' or a date."""
    tz = ZoneInfo(APP_TIMEZONE)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    local = ts.astimezone(tz)
    now = (now or datetime.now(timezone.utc)).astimezone(tz)

    seconds = (now - local).total_seconds()
    clock = local.strftime("%I:%M %p").lstrip("0")

    if seconds < 60:
        return "Just now"
    if seconds < 3600:
        return f"{int(seconds // 60)} min ago"
    if local.date() == now.date():
        return f"Today, {clock}"
    if local.date() == now.date() - timedelta(days=1):
        return f"Yesterday, {clock}"
    return f"{local.strftime('%d %b %Y')}, {clock}"


RISK_LABELS = {"HIGH": "🔴 HIGH", "MEDIUM": "🟠 MEDIUM", "LOW": "🟢 LOW"}
RISK_COLORS = {
    "🔴 HIGH": "rgba(255, 75, 75, 0.15)",
    "🟠 MEDIUM": "rgba(255, 170, 0, 0.15)",
    "🟢 LOW": "rgba(33, 195, 84, 0.12)",
}


def color_row(row):
    color = RISK_COLORS.get(row["Risk"], "")
    return [f"background-color: {color}"] * len(row)


# ---------- App ----------

st.title("MOBILE MONEY FRAUD DETECTION SYSTEM")

predict_tab, history_tab = st.tabs(["🔍 Predict", "📜 Prediction History"])

with predict_tab:
    st.write("Input Transaction Details Below")

    transaction_type = st.selectbox(
        "Select transaction type",
        ["CASH_IN", "CASH_OUT", "PAYMENT", "TRANSFER"]
    )

    amount = st.number_input("Amount")
    oldbalanceOrg = st.number_input("Old Balance Original")
    oldbalanceDest = st.number_input("Old Balance Destination")
    newbalanceOrig = st.number_input("New Balance Original")
    newbalanceDest = st.number_input("New Balance Destination")

    # Encode transaction type
    type_CASH_IN = 1 if transaction_type == "CASH_IN" else 0
    type_CASH_OUT = 1 if transaction_type == "CASH_OUT" else 0
    type_PAYMENT = 1 if transaction_type == "PAYMENT" else 0
    type_TRANSFER = 1 if transaction_type == "TRANSFER" else 0

    # Calculate balance changes
    Actualbalanceorig = oldbalanceOrg - newbalanceOrig
    Actualbalancedest = newbalanceDest - oldbalanceDest

    if st.button("Predict Transaction"):

        input_data = [[
            amount,
            oldbalanceOrg,
            newbalanceOrig,
            oldbalanceDest,
            newbalanceDest,
            Actualbalanceorig,
            Actualbalancedest,
            type_CASH_IN,
            type_CASH_OUT,
            type_PAYMENT,
            type_TRANSFER
        ]]

        prediction = model.predict(input_data)
        fraud_probability = float(model.predict_proba(input_data)[0][1])

        # Check unusual amount and balance changes
        unusual_amount = amount >= 100000
        unusual_balance = (
            abs(Actualbalanceorig - amount) > 1
            or abs(Actualbalancedest - amount) > 1
        )

        # Display risk level
        if prediction[0] == 1:
            risk_level = "HIGH"
            st.error("HIGH RISK: Fraudulent Transaction Detected")

            st.markdown("""
            <audio autoplay>
            <source src="https://actions.google.com/sounds/v1/alarms/beep_short.ogg"
            type="audio/ogg">
            </audio>
            """, unsafe_allow_html=True)

        elif unusual_amount or unusual_balance:
            risk_level = "MEDIUM"
            st.warning("MEDIUM RISK: Transaction Requires Review")

        else:
            risk_level = "LOW"
            st.success("LOW RISK: Transaction is Legitimate")

        # Display balance-change information
        st.write("Fraud Probability:", f"{fraud_probability:.1%}")
        st.write("Sender Balance Change:", Actualbalanceorig)
        st.write("Receiver Balance Change:", Actualbalancedest)

        # Save prediction to the database
        try:
            save_prediction({
                "transaction_type": transaction_type,
                "amount": amount,
                "old_balance_orig": oldbalanceOrg,
                "new_balance_orig": newbalanceOrig,
                "old_balance_dest": oldbalanceDest,
                "new_balance_dest": newbalanceDest,
                "sender_change": Actualbalanceorig,
                "receiver_change": Actualbalancedest,
                "fraud_probability": fraud_probability,
                "risk_level": risk_level,
            })
            st.toast("Prediction saved to history")
        except Exception as e:
            st.warning(f"Could not save prediction to the database: {e}")

with history_tab:
    try:
        history = load_history()
    except Exception as e:
        history = None
        st.warning(f"Could not load prediction history: {e}")

    if history is not None and history.empty:
        st.info("No predictions yet. Make a prediction in the Predict tab and it will appear here.")

    elif history is not None:
        counts = history["risk_level"].value_counts()
        total_col, high_col, medium_col, low_col = st.columns(4)
        total_col.metric("Total", len(history))
        high_col.metric("🔴 High", int(counts.get("HIGH", 0)))
        medium_col.metric("🟠 Medium", int(counts.get("MEDIUM", 0)))
        low_col.metric("🟢 Low", int(counts.get("LOW", 0)))

        selected = st.multiselect(
            "Filter by risk level",
            ["HIGH", "MEDIUM", "LOW"],
            default=["HIGH", "MEDIUM", "LOW"]
        )
        filtered = history[history["risk_level"].isin(selected)]

        table = pd.DataFrame({
            "When": filtered["created_at"].map(humanize_time),
            "Type": filtered["transaction_type"],
            "Amount": filtered["amount"],
            "Old Balance Orig": filtered["old_balance_orig"],
            "New Balance Orig": filtered["new_balance_orig"],
            "Old Balance Dest": filtered["old_balance_dest"],
            "New Balance Dest": filtered["new_balance_dest"],
            "Sender Change": filtered["sender_change"],
            "Receiver Change": filtered["receiver_change"],
            "Fraud Probability": filtered["fraud_probability"],
            "Risk": filtered["risk_level"].map(RISK_LABELS),
        })

        money_columns = [c for c in table.columns if c not in ("When", "Type", "Fraud Probability", "Risk")]
        styled = (
            table.style
            .apply(color_row, axis=1)
            .format("{:,.2f}", subset=money_columns)
            .format("{:.1%}", subset=["Fraud Probability"])
        )
        st.dataframe(styled, hide_index=True, width="stretch")

        st.download_button(
            "Download history as CSV",
            filtered.to_csv(index=False),
            file_name="prediction_history.csv",
            mime="text/csv"
        )
