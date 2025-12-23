import os, bcrypt, streamlit as st, pandas as pd
from datetime import datetime, date, time, timedelta
from sqlalchemy import create_engine, text

APP_USER=os.getenv("APP_USER")
APP_PASSWORD=os.getenv("APP_PASSWORD")
DB_PATH=os.getenv("DB_PATH","health.db")

if not APP_USER or not APP_PASSWORD:
    st.error("Defina APP_USER e APP_PASSWORD")
    st.stop()

engine=create_engine(f"sqlite:///{DB_PATH}",connect_args={"check_same_thread":False})

# ---------------- DB ----------------
with engine.begin() as c:
    c.execute(text("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password_hash TEXT);"))
    c.execute(text("CREATE TABLE IF NOT EXISTS bp (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, systolic INT, diastolic INT, bpm INT);"))
    c.execute(text("CREATE TABLE IF NOT EXISTS sleep (id INTEGER PRIMARY KEY AUTOINCREMENT, sleep_date TEXT, duration INT, score INT);"))
    c.execute(text("CREATE TABLE IF NOT EXISTS workouts (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, activity TEXT, duration INT);"))
    c.execute(text("""CREATE TABLE IF NOT EXISTS body (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT,
        weight REAL,
        fat REAL,
        muscle REAL,
        water REAL,
        visceral REAL,
        bmr REAL
    );"""))
    r=c.execute(text("SELECT 1 FROM users WHERE username=:u"),{"u":APP_USER}).fetchone()
    if not r:
        pw=bcrypt.hashpw(APP_PASSWORD.encode(),bcrypt.gensalt()).decode()
        c.execute(text("INSERT INTO users VALUES (:u,:p)"),{"u":APP_USER,"p":pw})

# ---------------- Auth ----------------
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

st.title("❤️ Saúde & Performance — v11.2")

menu=st.sidebar.radio("Menu",[
    "Inserir dados","Dashboard","Forecast","Exportar CSV"
])

# ---------------- Load ----------------
bp=pd.read_sql("SELECT * FROM bp",engine,parse_dates=["ts"])
sleep=pd.read_sql("SELECT * FROM sleep",engine,parse_dates=["sleep_date"])
wo=pd.read_sql("SELECT * FROM workouts",engine,parse_dates=["ts"])
body=pd.read_sql("SELECT * FROM body",engine,parse_dates=["ts"])

# ---------------- Forecast helpers ----------------
def forecast_series(df, date_col, value_col, days=14):
    d=df[[date_col,value_col]].dropna()
    if len(d)<30:
        return None

    # Try Prophet
    try:
        from prophet import Prophet
        mdf=d.rename(columns={date_col:"ds",value_col:"y"})
        m=Prophet(daily_seasonality=False, weekly_seasonality=True)
        m.fit(mdf)
        future=m.make_future_dataframe(periods=days)
        fc=m.predict(future)[["ds","yhat"]]
        return fc.rename(columns={"yhat":"y"})
    except Exception:
        pass

    # Fallback: linear regression
    try:
        from sklearn.linear_model import LinearRegression
        mdf=d.copy()
        mdf["t"]=(mdf[date_col]-mdf[date_col].min()).dt.days
        X=mdf[["t"]]
        y=mdf[value_col]
        lr=LinearRegression().fit(X,y)
        future=pd.DataFrame({"t":range(mdf.t.max()+1,mdf.t.max()+1+days)})
        future["y"]=lr.predict(future[["t"]])
        future["ds"]=[mdf[date_col].max()+timedelta(days=i+1) for i in range(days)]
        hist=mdf[[date_col,value_col]].rename(columns={date_col:"ds",value_col:"y"})
        return pd.concat([hist,future[["ds","y"]]])
    except Exception:
        return None

# ---------------- Inserir dados ----------------
if menu=="Inserir dados":
    t1,t2,t3,t4=st.tabs(["🩺 Pressão","😴 Sono","🏋️ Treino","⚖️ Balança (bioimpedância)"])

    with t1:
        with st.form("bp"):
            d=st.date_input("Data",date.today(), key="bpd")
            t=st.time_input("Hora",datetime.now().time().replace(second=0,microsecond=0), key="bpt")
            s=st.number_input("Sistólica",60,260,120, key="bps")
            d2=st.number_input("Diastólica",40,160,80, key="bpd2")
            b=st.number_input("BPM",30,220,60, key="bpb")
            if st.form_submit_button("Salvar pressão"):
                with engine.begin() as c:
                    c.execute(text("INSERT INTO bp (ts,systolic,diastolic,bpm) VALUES (:t,:s,:d,:b)"),
                              {"t":datetime.combine(d,t).isoformat(),"s":int(s),"d":int(d2),"b":int(b)})
                st.success("Pressão salva")
                st.rerun()

    with t2:
        with st.form("sleep"):
            sd=st.date_input("Data do sono",date.today(), key="sd")
            dur=st.number_input("Duração (min)",0,1000,0, key="dur")
            sc=st.number_input("Score (0-100)",0,100,0, key="sc")
            if st.form_submit_button("Salvar sono"):
                with engine.begin() as c:
                    c.execute(text("INSERT INTO sleep (sleep_date,duration,score) VALUES (:d,:du,:s)"),
                              {"d":sd.isoformat(),"du":(int(dur) if dur>0 else None),"s":(int(sc) if sc>0 else None)})
                st.success("Sono salvo")
                st.rerun()

    with t3:
        with st.form("wo"):
            d=st.date_input("Data",date.today(), key="wd")
            t=st.time_input("Hora",datetime.now().time().replace(second=0,microsecond=0), key="wt")
            act=st.selectbox("Atividade",["Musculação","Esteira","Beach tênis","Pickleball","Tênis","Outro"], key="wa")
            dur=st.number_input("Duração (min)",0,600,60, key="wdu")
            if st.form_submit_button("Salvar treino"):
                with engine.begin() as c:
                    c.execute(text("INSERT INTO workouts (ts,activity,duration) VALUES (:t,:a,:d)"),
                              {"t":datetime.combine(d,t).isoformat(),"a":act,"d":int(dur)})
                st.success("Treino salvo")
                st.rerun()

    with t4:
        with st.form("body"):
            d=st.date_input("Data",date.today(), key="bd")
            t=st.time_input("Hora",time(7,0), key="bt")
            weight=st.number_input("Peso (kg)",20.0,300.0,80.0,0.1, key="bw")
            fat=st.number_input("% Gordura",0.0,80.0,0.0,0.1, key="bf")
            muscle=st.number_input("% Músculo",0.0,80.0,0.0,0.1, key="bm")
            water=st.number_input("% Água",0.0,80.0,0.0,0.1, key="bwa")
            visceral=st.number_input("Visceral (índice)",0.0,60.0,0.0,0.5, key="bv")
            bmr=st.number_input("BMR (kcal)",0.0,6000.0,0.0,10.0, key="bbmr")
            if st.form_submit_button("Salvar balança"):
                with engine.begin() as c:
                    c.execute(text("""INSERT INTO body (ts,weight,fat,muscle,water,visceral,bmr)
                                    VALUES (:t,:w,:f,:m,:wa,:v,:b)"""),
                              {"t":datetime.combine(d,t).isoformat(),
                               "w":float(weight),
                               "f":(float(fat) if fat>0 else None),
                               "m":(float(muscle) if muscle>0 else None),
                               "wa":(float(water) if water>0 else None),
                               "v":(float(visceral) if visceral>0 else None),
                               "b":(float(bmr) if bmr>0 else None)})
                st.success("Balança salva")
                st.rerun()

# ---------------- Dashboard ----------------
elif menu=="Dashboard":
    t1,t2,t3,t4=st.tabs(["🩺 Pressão","😴 Sono","🏋️ Treino","⚖️ Balança"])

    with t1:
        if bp.empty:
            st.info("Sem dados")
        else:
            st.line_chart(bp.set_index("ts")[["systolic","diastolic","bpm"]])

    with t2:
        if sleep.empty:
            st.info("Sem dados")
        else:
            cols=[]
            if "duration" in sleep.columns and sleep["duration"].notna().any(): cols.append("duration")
            if "score" in sleep.columns and sleep["score"].notna().any(): cols.append("score")
            if cols:
                st.line_chart(sleep.set_index("sleep_date")[cols])

    with t3:
        if wo.empty:
            st.info("Sem dados")
        else:
            tmp=wo.copy()
            tmp["week"]=tmp.ts.dt.to_period("W").astype(str)
            st.bar_chart(tmp.groupby("week")["duration"].sum())

    with t4:
        if body.empty:
            st.info("Sem dados")
        else:
            st.line_chart(body.set_index("ts")[["weight"]])
            cols=[c for c in ["fat","muscle","water","visceral","bmr"] if c in body.columns and body[c].notna().any()]
            if cols:
                st.line_chart(body.set_index("ts")[cols])

# ---------------- Forecast ----------------
elif menu=="Forecast":
    st.subheader("📈 Forecast (>=30 dias)")
    st.caption("Mostra previsão de 14 dias à frente. Ativa só com pelo menos 30 pontos/dias na série.")

    # BP
    st.markdown("## Pressão & BPM")
    fc_sys=forecast_series(bp,"ts","systolic")
    if fc_sys is None:
        st.info("Pressão sistólica: necessário mínimo de 30 dias/pontos")
    else:
        st.markdown("### Sistólica")
        st.line_chart(fc_sys.set_index("ds")[["y"]])

    fc_bpm=forecast_series(bp,"ts","bpm")
    if fc_bpm is None:
        st.info("BPM: necessário mínimo de 30 dias/pontos")
    else:
        st.markdown("### BPM")
        st.line_chart(fc_bpm.set_index("ds")[["y"]])

    # Sleep
    st.markdown("## Sono")
    fc_sleep=forecast_series(sleep,"sleep_date","score")
    if fc_sleep is None:
        st.info("Score de sono: necessário mínimo de 30 dias/pontos")
    else:
        st.markdown("### Score de sono")
        st.line_chart(fc_sleep.set_index("ds")[["y"]])

    # Body / bioimpedance
    st.markdown("## ⚖️ Balança (bioimpedância)")
    fc_w=forecast_series(body,"ts","weight")
    if fc_w is None:
        st.info("Peso: necessário mínimo de 30 dias/pontos")
    else:
        st.markdown("### Peso (kg)")
        st.line_chart(fc_w.set_index("ds")[["y"]])

    for col, title in [("fat","% Gordura"),("muscle","% Músculo"),("water","% Água")]:
        if col in body.columns and body[col].notna().sum() >= 30:
            fc=forecast_series(body,"ts",col)
            if fc is not None:
                st.markdown(f"### {title}")
                st.line_chart(fc.set_index("ds")[["y"]])

# ---------------- Export ----------------
else:
    st.subheader("⬇️ Exportar CSV")
    st.download_button("bp.csv", bp.to_csv(index=False), "bp.csv")
    st.download_button("sleep.csv", sleep.to_csv(index=False), "sleep.csv")
    st.download_button("workouts.csv", wo.to_csv(index=False), "workouts.csv")
    st.download_button("body.csv", body.to_csv(index=False), "body.csv")
