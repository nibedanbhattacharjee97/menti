import streamlit as st
import pandas as pd
import sqlite3
import qrcode
from io import BytesIO
import matplotlib.pyplot as plt

# ---------------- Database setup ----------------
conn = sqlite3.connect("votes.db", check_same_thread=False)
c = conn.cursor()
c.execute("CREATE TABLE IF NOT EXISTS votes (question TEXT, option TEXT)")
conn.commit()

# ---------------- QR Code Generator ----------------
def generate_qr_code(url):
    qr = qrcode.make(url)
    buf = BytesIO()
    qr.save(buf, format="PNG")
    buf.seek(0)
    return buf

# ---------------- Streamlit Page Config ----------------
st.set_page_config("📊 Mentimeter Clone", layout="wide")
st.title("📊 Live Voting App (Mentimeter Clone)")

# ---------------- Sidebar Navigation ----------------
menu = st.sidebar.radio("Select View", ["Upload Questions", "Voting Page", "Live Results"])

# ---------------- Upload Questions ----------------
if menu == "Upload Questions":
    st.header("📤 Upload Questions Excel")
    uploaded_file = st.file_uploader("Upload Excel", type=["xlsx"])

    if uploaded_file:
        df = pd.read_excel(uploaded_file)
        st.session_state["questions_df"] = df
        st.success("✅ File uploaded and questions loaded!")
        st.write(df)

        # QR Code to Vote
        st.subheader("📱 Scan QR to Vote")
        qr_url = "http://localhost:8501"  # Change to actual deployed URL if needed
        qr_img = generate_qr_code(qr_url)
        st.image(qr_img, caption="Scan this QR Code to Vote", width=250)

# ---------------- Voting Page ----------------
elif menu == "Voting Page":
    st.header("🗳️ Vote Now")

    if "questions_df" in st.session_state:
        df = st.session_state["questions_df"]
        question_list = df["Question"].tolist()
        selected_question = st.selectbox("Select Question", question_list)

        question_row = df[df["Question"] == selected_question].iloc[0]
        options = [opt for opt in question_row[1:].dropna().tolist()]

        selected_option = st.radio("Choose your answer:", options)

        if st.button("Submit Vote"):
            c.execute("INSERT INTO votes (question, option) VALUES (?, ?)", (selected_question, selected_option))
            conn.commit()
            st.success("✅ Your vote has been recorded!")
    else:
        st.warning("⚠️ Please upload a question Excel first.")

# ---------------- Live Results ----------------
elif menu == "Live Results":
    st.header("📈 Live Voting Results")

    # Delete All Results Button
    if st.button("🗑️ Delete All Voting Results"):
        c.execute("DELETE FROM votes")
        conn.commit()
        st.success("✅ All voting results have been deleted!")

    # Display Results
    c.execute("SELECT DISTINCT question FROM votes")
    questions = [row[0] for row in c.fetchall()]

    if questions:
        selected_q = st.selectbox("Choose a question to view results", questions)
        c.execute("SELECT option, COUNT(*) FROM votes WHERE question=? GROUP BY option", (selected_q,))
        results = c.fetchall()

        if results:
            options, counts = zip(*results)
            total_votes = sum(counts)
            percentages = [(count / total_votes) * 100 for count in counts]

            fig, ax = plt.subplots(figsize=(8, 4))
            bars = ax.bar(options, percentages, color=['#1f77b4', '#ff7f0e', '#2ca02c'], width=0.6)

            ax.set_ylabel("Percentage")
            ax.set_ylim(0, 100)
            ax.set_title(f"Live Results for: {selected_q}")
            ax.bar_label(bars, labels=[f"{pct:.1f}%" for pct in percentages], padding=3)
            st.pyplot(fig)
        else:
            st.info("No votes yet for this question.")
    else:
        st.warning("⚠️ No voting data available.")
    