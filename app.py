
import os, bcrypt, streamlit as st, pandas as pd
from datetime import datetime, date
from sqlalchemy import create_engine, text

# ---------- Config ----------
APP_USER=os.getenv("APP_USER")
APP_PASSWORD=os.getenv("APP_PASSWORD")
DB_PATH="health.db"

if not APP_USER or not APP_PASSWORD:
    st.error("Defina APP_USER e APP_PASSWORD")
    st.stop()

engine=create_engine(f"sqlite:///{DB_PATH}",connect_args={"check_same_thread":False})

# ---------- DB ----------
with engine.begin() as c:
    c.execute(text("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password_hash TEXT);"))
    c.execute(text("CREATE TABLE IF NOT EXISTS bp (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, systolic INT, diastolic INT, bpm INT);"))
    c.execute(text("CREATE TABLE IF NOT EXISTS sleep (id INTEGER PRIMARY KEY AUTOINCREMENT, sleep_date TEXT, duration INT, score INT);"))
    c.execute(text("CREATE TABLE IF NOT EXISTS workouts (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, duration INT);"))
    r=c.execute(text("SELECT 1 FROM users WHERE username=:u"),{"u":APP_USER}).fetchone()
    if not r:
        pw=bcrypt.hashpw(APP_PASSWORD.encode(),bcrypt.gensalt()).decode()
        c.execute(text("INSERT INTO users VALUES (:u,:p)"),{"u":APP_USER,"p":pw})

# ---------- Login ----------
def login():
    u=st.text_input("Usuário")
    p=st.text_input("Senha",type="password")
    if st.button("Entrar"):
        with engine.begin() as c:
            r=c.execute(text("SELECT password_hash FROM users WHERE username=:u"),{"u":u}).fetchone()
            if r and bcrypt.checkpw(p.encode(),r[0].encode()):
                st.session_state["auth"]=True
                st.rerun()
            else:
                st.error("Login inválido")

if "auth" not in st.session_state:
    login()
    st.stop()

st.title("❤️ Saúde & Performance — v7")

# ---------- Load data ----------
bp=pd.read_sql("SELECT * FROM bp",engine,parse_dates=["ts"])
sleep=pd.read_sql("SELECT * FROM sleep",engine,parse_dates=["sleep_date"])
wo=pd.read_sql("SELECT * FROM workouts",engine,parse_dates=["ts"])

# ---------- Score ----------
def daily_score(d):
    pts=0
    day_bp=bp[bp.ts.dt.date==d]
    if not day_bp.empty:
        last=day_bp.iloc[-1]
        pts+=40 if last.systolic<130 else 25 if last.systolic<140 else 10
        pts+=max(0,25-abs(last.bpm-60))
    else:
        pts+=20

    s=sleep[sleep.sleep_date.dt.date==d]
    if not s.empty:
        if s.iloc[-1].score:
            pts+=s.iloc[-1].score*0.25
        elif s.iloc[-1].duration:
            pts+=min(25,(s.iloc[-1].duration/60)/8*25)
    else:
        pts+=10

    mins=wo[wo.ts.dt.date==d].duration.sum() if not wo.empty else 0
    pts+=10 if mins==0 else 15 if mins<60 else 10 if mins<120 else 5

    pts=int(min(100,pts))
    if pts>=80: sug="Treino forte liberado"
    elif pts>=65: sug="Treino moderado"
    elif pts>=50: sug="Treino leve"
    else: sug="Descanso recomendado"
    return pts,sug

today=date.today()
score,sug=daily_score(today)

st.subheader(f"🚦 Hoje: {score}/100")
st.info(sug)

# ---------- Alerts ----------
if not bp.empty:
    last=bp.iloc[-1]
    if last.systolic>=140 or last.bpm>=100:
        st.error(f"⚠️ Alerta: {last.systolic}/{last.diastolic} • BPM {last.bpm}")
    else:
        st.success(f"Última: {last.systolic}/{last.diastolic} • BPM {last.bpm}")

# ---------- Dashboards ----------
tab1,tab2,tab3=st.tabs(["🩺 Pressão","😴 Sono","🏋️ Treino"])

with tab1:
    if not bp.empty:
        st.line_chart(bp.set_index("ts")[["systolic","diastolic","bpm"]])
    else:
        st.info("Sem dados")

with tab2:
    if not sleep.empty:
        if sleep.duration.notna().any():
            st.bar_chart(sleep.set_index("sleep_date")[["duration"]])
        if sleep.score.notna().any():
            st.line_chart(sleep.set_index("sleep_date")[["score"]])
    else:
        st.info("Sem dados")

with tab3:
    if not wo.empty:
        wo["week"]=wo.ts.dt.to_period("W").astype(str)
        st.bar_chart(wo.groupby("week")["duration"].sum())
    else:
        st.info("Sem dados")
