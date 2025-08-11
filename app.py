import streamlit as st
import pandas as pd
import sqlite3
import qrcode
from io import BytesIO
import matplotlib.pyplot as plt
from datetime import datetime
import json
import os

# -----------------------
# Config & DB connection
# -----------------------
st.set_page_config(page_title="📊 Mentimeter Clone", layout="wide")
DB_PATH = "votes.db"
BASE_URL = "https://YOUR_DEPLOYED_STREAMLIT_APP_URL"  # Replace with your app link

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
c = conn.cursor()

# Drop old tables if schema mismatch (optional safety)
def ensure_schema():
    # Check if 'id' exists in votes table
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='votes'")
    if c.fetchone():
        c.execute("PRAGMA table_info(votes)")
        cols = [r[1] for r in c.fetchall()]
        if "id" not in cols:
            c.execute("DROP TABLE votes")
    # Create tables
    c.execute("""
    CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question_text TEXT NOT NULL,
        created_at TEXT NOT NULL,
        meta TEXT
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS options (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question_id INTEGER NOT NULL,
        option_text TEXT NOT NULL,
        FOREIGN KEY(question_id) REFERENCES questions(id) ON DELETE CASCADE
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS votes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question_id INTEGER NOT NULL,
        option_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(question_id) REFERENCES questions(id) ON DELETE CASCADE,
        FOREIGN KEY(option_id) REFERENCES options(id) ON DELETE CASCADE
    )
    """)
    conn.commit()

ensure_schema()

# -----------------------
# Utility functions
# -----------------------
def generate_qr_code_bytes(url: str):
    qr = qrcode.make(url)
    buf = BytesIO()
    qr.save(buf, format="PNG")
    buf.seek(0)
    return buf

def insert_question_with_options(question_text: str, options_list: list, meta: dict = None):
    created_at = datetime.utcnow().isoformat()
    meta_json = json.dumps(meta) if meta else None
    c.execute("INSERT INTO questions (question_text, created_at, meta) VALUES (?, ?, ?)",
              (question_text, created_at, meta_json))
    qid = c.lastrowid
    for opt in options_list:
        c.execute("INSERT INTO options (question_id, option_text) VALUES (?, ?)", (qid, opt))
    conn.commit()
    return qid

def get_question(qid: int):
    c.execute("SELECT id, question_text, created_at, meta FROM questions WHERE id=?", (qid,))
    row = c.fetchone()
    if not row:
        return None
    q = {
        "id": row[0],
        "question_text": row[1],
        "created_at": row[2],
        "meta": json.loads(row[3]) if row[3] else None
    }
    c.execute("SELECT id, option_text FROM options WHERE question_id=? ORDER BY id", (qid,))
    q["options"] = [{"id": r[0], "text": r[1]} for r in c.fetchall()]
    return q

def get_all_questions():
    c.execute("SELECT id, question_text, created_at FROM questions ORDER BY created_at DESC")
    return c.fetchall()

def record_vote(question_id: int, option_id: int):
    created_at = datetime.utcnow().isoformat()
    c.execute("INSERT INTO votes (question_id, option_id, created_at) VALUES (?, ?, ?)",
              (question_id, option_id, created_at))
    conn.commit()

def get_results(question_id: int):
    c.execute("""
        SELECT o.option_text, COUNT(v.id) AS cnt, o.id
        FROM options o
        LEFT JOIN votes v ON v.option_id = o.id AND v.question_id=?
        WHERE o.question_id=?
        GROUP BY o.id, o.option_text
        ORDER BY o.id
    """, (question_id, question_id))
    rows = c.fetchall()
    return [{"option_text": r[0], "count": r[1], "option_id": r[2]} for r in rows]

def delete_question(question_id: int):
    c.execute("DELETE FROM votes WHERE question_id=?", (question_id,))
    c.execute("DELETE FROM options WHERE question_id=?", (question_id,))
    c.execute("DELETE FROM questions WHERE id=?", (question_id,))
    conn.commit()

# -----------------------
# Public QR voting mode
# -----------------------
query_params = st.query_params

if "q" in query_params:
    try:
        question_id = int(query_params["q"])
    except:
        st.error("Invalid question id.")
        st.stop()

    q = get_question(question_id)
    if q is None:
        st.error("Question not found.")
        st.stop()

    st.title("🗳️ Vote — " + q["question_text"])
    st.write("Select one option and submit your vote.")

    option_ids = [opt["id"] for opt in q["options"]]
    option_texts = [opt["text"] for opt in q["options"]]
    selected = st.radio("Choose an option:", option_texts)
    selected_option_id = option_ids[option_texts.index(selected)]

    if st.button("Submit Vote"):
        record_vote(question_id, selected_option_id)
        st.success("✅ Your vote has been recorded!")

        results = get_results(question_id)
        total = sum(r["count"] for r in results)
        if total > 0:
            st.subheader("Live Results")
            options = [r["option_text"] for r in results]
            counts = [r["count"] for r in results]
            percentages = [(c / total) * 100 for c in counts]
            fig, ax = plt.subplots(figsize=(8, 4))
            bars = ax.bar(options, percentages, width=0.6)
            ax.set_ylim(0, 100)
            ax.set_ylabel("Percentage")
            ax.bar_label(bars, labels=[f"{p:.1f}%" for p in percentages], padding=3)
            st.pyplot(fig)
    st.stop()

# -----------------------
# Admin UI
# -----------------------
st.title("📊 Live Voting App (Mentimeter Clone)")
menu = st.sidebar.radio("Select View", [
    "Upload Questions", "Questions Manager", "Voting Page (local)", "Live Results", "Admin: Cleanup"
])

# Upload Questions
if menu == "Upload Questions":
    st.header("📤 Upload Questions Excel")
    uploaded_file = st.file_uploader("Upload Excel (.xlsx)", type=["xlsx"])
    if uploaded_file:
        df = pd.read_excel(uploaded_file)
        if "Question" not in df.columns:
            st.error("Excel must have a 'Question' column.")
            st.stop()
        st.write(df)
        set_name = st.text_input("Optional: Set name for this upload")
        if st.button("Save Questions"):
            count = 0
            for _, row in df.iterrows():
                qtext = str(row["Question"]).strip()
                options = [str(v).strip() for v in row[1:].tolist()
                           if pd.notna(v) and str(v).strip()]
                if qtext and len(options) >= 2:
                    insert_question_with_options(qtext, options, {"upload_name": set_name or None})
                    count += 1
            st.success(f"✅ Saved {count} question(s).")
            st.rerun()

# Questions Manager
elif menu == "Questions Manager":
    st.header("🗂️ Questions Manager")
    rows = get_all_questions()
    if not rows:
        st.info("No questions found.")
    else:
        for qid, qtext, created_at in rows:
            with st.expander(f"{qtext} (ID: {qid})"):
                q = get_question(qid)
                st.write("Options:", [o["text"] for o in q["options"]])
                if BASE_URL.startswith("http"):
                    vote_url = f"{BASE_URL}?q={qid}"
                    st.code(vote_url)
                    st.image(generate_qr_code_bytes(vote_url), width=200)
                results = get_results(qid)
                st.write("Votes:", {r["option_text"]: r["count"] for r in results})
                if st.button("Delete Question", key=f"del{qid}"):
                    delete_question(qid)
                    st.success("Deleted.")
                    st.rerun()

# Voting Page (local)
elif menu == "Voting Page (local)":
    st.header("🗳️ Vote Locally")
    rows = get_all_questions()
    if not rows:
        st.info("No questions available.")
    else:
        q_map = {f"{qid} - {qtext}": qid for qid, qtext, _ in rows}
        choice = st.selectbox("Choose Question", list(q_map.keys()))
        qid = q_map[choice]
        q = get_question(qid)
        selected = st.radio("Choose an option:", [o["text"] for o in q["options"]])
        if st.button("Submit Local Vote"):
            opt_id = q["options"][[o["text"] for o in q["options"]].index(selected)]["id"]
            record_vote(qid, opt_id)
            st.success("Vote recorded.")
            st.rerun()

# Live Results
elif menu == "Live Results":
    st.header("📈 Live Results")
    rows = get_all_questions()
    if not rows:
        st.info("No questions.")
    else:
        q_map = {f"{qid} - {qtext}": qid for qid, qtext, _ in rows}
        choice = st.selectbox("Select Question", list(q_map.keys()))
        qid = q_map[choice]
        results = get_results(qid)
        total = sum(r["count"] for r in results)
        if total == 0:
            st.info("No votes yet.")
        else:
            options = [r["option_text"] for r in results]
            counts = [r["count"] for r in results]
            percentages = [(c / total) * 100 for c in counts]
            fig, ax = plt.subplots(figsize=(8, 4))
            bars = ax.bar(options, percentages, width=0.6)
            ax.set_ylim(0, 100)
            ax.set_ylabel("Percentage")
            ax.bar_label(bars, labels=[f"{p:.1f}%" for p in percentages], padding=3)
            st.pyplot(fig)

# Admin Cleanup
elif menu == "Admin: Cleanup":
    st.header("⚠️ Admin Cleanup")
    if st.button("Delete All Questions & Votes"):
        c.execute("DELETE FROM votes")
        c.execute("DELETE FROM options")
        c.execute("DELETE FROM questions")
        conn.commit()
        st.success("All data deleted.")
