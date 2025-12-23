
import os, bcrypt, streamlit as st, pandas as pd
from datetime import datetime, date
from sqlalchemy import create_engine, text

APP_USER=os.getenv("APP_USER")
APP_PASSWORD=os.getenv("APP_PASSWORD")
DB_PATH="health.db"

if not APP_USER or not APP_PASSWORD:
    st.error("Defina APP_USER e APP_PASSWORD")
    st.stop()

engine=create_engine(f"sqlite:///{DB_PATH}",connect_args={"check_same_thread":False})

# DB setup
with engine.begin() as c:
    c.execute(text("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password_hash TEXT);"))
    c.execute(text("CREATE TABLE IF NOT EXISTS bp (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, systolic INT, diastolic INT, bpm INT);"))
    c.execute(text("CREATE TABLE IF NOT EXISTS sleep (id INTEGER PRIMARY KEY AUTOINCREMENT, sleep_date TEXT, duration INT, score INT);"))
    c.execute(text("CREATE TABLE IF NOT EXISTS workouts (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, activity TEXT, duration INT);"))
    r=c.execute(text("SELECT 1 FROM users WHERE username=:u"),{"u":APP_USER}).fetchone()
    if not r:
        pw=bcrypt.hashpw(APP_PASSWORD.encode(),bcrypt.gensalt()).decode()
        c.execute(text("INSERT INTO users VALUES (:u,:p)"),{"u":APP_USER,"p":pw})

# Login
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

st.title("❤️ Saúde & Performance — v7.1")

menu=st.sidebar.radio("Menu",["Inserir dados","Dashboard","Score do dia","Exportar CSV"])

# Load data
bp=pd.read_sql("SELECT * FROM bp",engine,parse_dates=["ts"])
sleep=pd.read_sql("SELECT * FROM sleep",engine,parse_dates=["sleep_date"])
wo=pd.read_sql("SELECT * FROM workouts",engine,parse_dates=["ts"])

# Inserir dados
if menu=="Inserir dados":
    tab1,tab2,tab3=st.tabs(["🩺 Pressão","😴 Sono","🏋️ Treino"])

    with tab1:
        with st.form("bp"):
            d=st.date_input("Data",date.today())
            t=st.time_input("Hora",datetime.now().time())
            s=st.number_input("Sistólica",60,260,120)
            d2=st.number_input("Diastólica",40,160,80)
            b=st.number_input("BPM",30,220,60)
            if st.form_submit_button("Salvar"):
                with engine.begin() as c:
                    c.execute(text("INSERT INTO bp (ts,systolic,diastolic,bpm) VALUES (:t,:s,:d,:b)"),
                              {"t":datetime.combine(d,t).isoformat(),"s":s,"d":d2,"b":b})
                st.success("Salvo")
                st.experimental_rerun()

    with tab2:
        with st.form("sleep"):
            sd=st.date_input("Data do sono",date.today())
            dur=st.number_input("Duração (min)",0,1000,0)
            sc=st.number_input("Score (0-100)",0,100,0)
            if st.form_submit_button("Salvar"):
                with engine.begin() as c:
                    c.execute(text("INSERT INTO sleep (sleep_date,duration,score) VALUES (:d,:du,:s)"),
                              {"d":sd.isoformat(),"du":dur or None,"s":sc or None})
                st.success("Salvo")
                st.experimental_rerun()

    with tab3:
        with st.form("wo"):
            d=st.date_input("Data",date.today())
            t=st.time_input("Hora",datetime.now().time())
            act=st.selectbox("Atividade",["Musculação","Esteira","Beach tênis","Pickleball","Tênis","Outro"])
            dur=st.number_input("Duração (min)",0,600,60)
            if st.form_submit_button("Salvar"):
                with engine.begin() as c:
                    c.execute(text("INSERT INTO workouts (ts,activity,duration) VALUES (:t,:a,:d)"),
                              {"t":datetime.combine(d,t).isoformat(),"a":act,"d":dur})
                st.success("Salvo")
                st.experimental_rerun()

# Dashboard
elif menu=="Dashboard":
    tab1,tab2,tab3=st.tabs(["🩺 Pressão","😴 Sono","🏋️ Treino"])
    with tab1:
        if not bp.empty:
            st.line_chart(bp.set_index("ts")[["systolic","diastolic","bpm"]])
        else: st.info("Sem dados")
    with tab2:
        if not sleep.empty:
            if sleep.duration.notna().any():
                st.bar_chart(sleep.set_index("sleep_date")[["duration"]])
            if sleep.score.notna().any():
                st.line_chart(sleep.set_index("sleep_date")[["score"]])
        else: st.info("Sem dados")
    with tab3:
        if not wo.empty:
            wo["week"]=wo.ts.dt.to_period("W").astype(str)
            st.bar_chart(wo.groupby("week")["duration"].sum())
        else: st.info("Sem dados")

# Score
elif menu=="Score do dia":
    def score_day(d):
        pts=0
        db=bp[bp.ts.dt.date==d]
        if not db.empty:
            last=db.iloc[-1]
            pts+=40 if last.systolic<130 else 25 if last.systolic<140 else 10
            pts+=max(0,25-abs(last.bpm-60))
        else: pts+=20
        sl=sleep[sleep.sleep_date.dt.date==d]
        if not sl.empty:
            if sl.iloc[-1].score:
                pts+=sl.iloc[-1].score*0.25
            elif sl.iloc[-1].duration:
                pts+=min(25,(sl.iloc[-1].duration/60)/8*25)
        else: pts+=10
        mins=wo[wo.ts.dt.date==d].duration.sum() if not wo.empty else 0
        pts+=10 if mins==0 else 15 if mins<60 else 10 if mins<120 else 5
        pts=int(min(100,pts))
        if pts>=80: sug="Treino forte liberado"
        elif pts>=65: sug="Treino moderado"
        elif pts>=50: sug="Treino leve"
        else: sug="Descanso recomendado"
        return pts,sug

    sc,sug=score_day(date.today())
    st.subheader(f"🚦 Hoje: {sc}/100")
    st.info(sug)

# Export
else:
    st.subheader("⬇️ Exportar CSV")
    st.download_button("Baixar bp.csv",bp.to_csv(index=False),"bp.csv")
    st.download_button("Baixar sleep.csv",sleep.to_csv(index=False),"sleep.csv")
    st.download_button("Baixar workouts.csv",wo.to_csv(index=False),"workouts.csv")
