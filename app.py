
import streamlit as st
import pandas as pd
import joblib

model = joblib.load("meshach.pkl")

st.title("MOBILE MONEY FRAUD DETECTION SYSTEM")
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

    # Check unusual amount and balance changes
    unusual_amount = amount >= 100000
    unusual_balance = (
        abs(Actualbalanceorig - amount) > 1
        or abs(Actualbalancedest - amount) > 1
    )

    # Display risk level
    if prediction[0] == 1:
        st.error("HIGH RISK: Fraudulent Transaction Detected")

        st.markdown("""
        <audio autoplay>
        <source src="https://actions.google.com/sounds/v1/alarms/beep_short.ogg"
        type="audio/ogg">
        </audio>
        """, unsafe_allow_html=True)

    elif unusual_amount or unusual_balance:
        st.warning("MEDIUM RISK: Transaction Requires Review")

    else:
        st.success("LOW RISK: Transaction is Legitimate")

    # Display balance-change information
    st.write("Sender Balance Change:", Actualbalanceorig)
    st.write("Receiver Balance Change:", Actualbalancedest)
