
import os
import io
import zipfile
import bcrypt
import streamlit as st
import pandas as pd
from datetime import datetime, date, time
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL")  # Postgres when set
APP_USER = os.getenv("APP_USER")
APP_PASSWORD = os.getenv("APP_PASSWORD")
DB_PATH = os.getenv("DB_PATH", "health.db")

if not APP_USER or not APP_PASSWORD:
    st.error("Configure APP_USER e APP_PASSWORD nas variáveis de ambiente/Secrets.")
    st.stop()

def make_engine():
    if DATABASE_URL:
        return create_engine(DATABASE_URL, pool_pre_ping=True)
    return create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})

engine = make_engine()
backend = engine.url.get_backend_name()

def init_db():
    with engine.begin() as c:
        c.execute(text("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL
        );
        """))

        if backend == "sqlite":
            c.execute(text("""
            CREATE TABLE IF NOT EXISTS bp (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                period TEXT NOT NULL,
                systolic INTEGER NOT NULL,
                diastolic INTEGER NOT NULL,
                bpm INTEGER NOT NULL
            );
            """))
            c.execute(text("""
            CREATE TABLE IF NOT EXISTS body (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                weight REAL NOT NULL,
                fat REAL,
                muscle REAL,
                water REAL,
                visceral REAL,
                bmr REAL,
                note TEXT
            );
            """))
            c.execute(text("""
            CREATE TABLE IF NOT EXISTS sleep (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sleep_date TEXT NOT NULL,
                duration INTEGER,
                score INTEGER,
                note TEXT
            );
            """))
            c.execute(text("""
            CREATE TABLE IF NOT EXISTS workouts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                activity TEXT,
                duration INTEGER,
                intensity TEXT,
                avg_hr INTEGER,
                note TEXT
            );
            """))
        else:
            c.execute(text("""
            CREATE TABLE IF NOT EXISTS bp (
                id SERIAL PRIMARY KEY,
                ts TIMESTAMP NOT NULL,
                period TEXT NOT NULL,
                systolic INT NOT NULL,
                diastolic INT NOT NULL,
                bpm INT NOT NULL
            );
            """))
            c.execute(text("""
            CREATE TABLE IF NOT EXISTS body (
                id SERIAL PRIMARY KEY,
                ts TIMESTAMP NOT NULL,
                weight DOUBLE PRECISION NOT NULL,
                fat DOUBLE PRECISION,
                muscle DOUBLE PRECISION,
                water DOUBLE PRECISION,
                visceral DOUBLE PRECISION,
                bmr DOUBLE PRECISION,
                note TEXT
            );
            """))
            c.execute(text("""
            CREATE TABLE IF NOT EXISTS sleep (
                id SERIAL PRIMARY KEY,
                sleep_date DATE NOT NULL,
                duration INT,
                score INT,
                note TEXT
            );
            """))
            c.execute(text("""
            CREATE TABLE IF NOT EXISTS workouts (
                id SERIAL PRIMARY KEY,
                ts TIMESTAMP NOT NULL,
                activity TEXT,
                duration INT,
                intensity TEXT,
                avg_hr INT,
                note TEXT
            );
            """))

def ensure_user():
    with engine.begin() as c:
        r = c.execute(text("SELECT 1 FROM users WHERE username=:u"), {"u": APP_USER}).fetchone()
        if not r:
            pw = bcrypt.hashpw(APP_PASSWORD.encode(), bcrypt.gensalt()).decode()
            c.execute(text("INSERT INTO users (username,password_hash) VALUES (:u,:p)"), {"u": APP_USER, "p": pw})

def login_ui():
    st.markdown("## 🔐 Login")
    u = st.text_input("Usuário")
    p = st.text_input("Senha", type="password")
    if st.button("Entrar"):
        with engine.begin() as c:
            r = c.execute(text("SELECT password_hash FROM users WHERE username=:u"), {"u": u}).fetchone()
            if r and bcrypt.checkpw(p.encode(), r[0].encode()):
                st.session_state["auth"] = True
                st.rerun()
            else:
                st.error("Usuário ou senha inválidos")

def classify(sys: int, dia: int) -> str:
    if sys >= 180 or dia >= 120: return "🔴 Muito alta"
    if sys >= 140 or dia >= 90: return "🟠 Alta"
    if sys >= 130 or dia >= 80: return "🟡 Elevada"
    return "🟢 Normal"

def dt_for_db(d: date, t_: time):
    dt = datetime.combine(d, t_).replace(second=0, microsecond=0)
    return dt.isoformat() if backend == "sqlite" else dt

def read_df(sql: str, params=None):
    return pd.read_sql(text(sql), engine, params=params or {})

def export_backup_zip() -> bytes:
    tables = ["bp", "body", "sleep", "workouts"]
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
        for t in tables:
            df = read_df(f"SELECT * FROM {t} ORDER BY 1 DESC")
            z.writestr(f"{t}.csv", df.to_csv(index=False))
    mem.seek(0)
    return mem.read()

def restore_backup_zip(file_bytes: bytes) -> str:
    tables = ["bp", "body", "sleep", "workouts"]
    with zipfile.ZipFile(io.BytesIO(file_bytes), "r") as z:
        for t in tables:
            if f"{t}.csv" not in z.namelist():
                return f"Backup inválido: faltando {t}.csv"

        with engine.begin() as c:
            for t in tables:
                c.execute(text(f"DELETE FROM {t};"))

        for t in tables:
            df = pd.read_csv(z.open(f"{t}.csv"))
            if df.empty:
                continue
            df.to_sql(t, engine, if_exists="append", index=False)
    return "Restore concluído!"

st.set_page_config("Saúde & Performance", "❤️", layout="centered")

init_db()
ensure_user()

with st.sidebar:
    mode = "Cloud (Postgres)" if DATABASE_URL else "Local (SQLite)"
    st.caption(f"Modo: **{mode}**")
    if not DATABASE_URL:
        st.warning("No Streamlit Cloud, SQLite pode perder dados em reinícios. Use Backup ou Postgres.")
    page = st.radio("Menu", ["Registrar", "Dashboard", "Backup/Restore"], index=0)

if "auth" not in st.session_state:
    login_ui()
    st.stop()

st.title("❤️ Saúde & Performance")

if page == "Registrar":
    tab_bp, tab_body, tab_sleep, tab_wo = st.tabs(["🩺 Pressão", "⚖️ Balança", "😴 Sono (opcional)", "🏋️ Treino (opcional)"])

    with tab_bp:
        with st.form("bp_form", clear_on_submit=True):
            d = st.date_input("Data", value=date.today())
            tt = st.time_input("Hora", value=datetime.now().time().replace(second=0, microsecond=0))
            period = st.selectbox("Período", ["matinal", "vespertina", "noturna"])
            c1, c2 = st.columns(2)
            sys = c1.number_input("Sistólica (mmHg)", 60, 260, 120, 1)
            dia = c2.number_input("Diastólica (mmHg)", 40, 160, 80, 1)
            bpm = st.number_input("BPM (pulso)", 30, 220, 60, 1)
            ok = st.form_submit_button("Salvar pressão ✅")
            if ok:
                with engine.begin() as c:
                    c.execute(text("""
                        INSERT INTO bp (ts, period, systolic, diastolic, bpm)
                        VALUES (:ts, :p, :s, :d, :b)
                    """), {"ts": dt_for_db(d, tt), "p": period, "s": int(sys), "d": int(dia), "b": int(bpm)})
                st.success("Pressão salva!")

    with tab_body:
        with st.form("body_form", clear_on_submit=True):
            d = st.date_input("Data", value=date.today(), key="bd")
            tt = st.time_input("Hora", value=time(7,0), key="bt")
            weight = st.number_input("Peso (kg)", 20.0, 300.0, 80.0, 0.1)
            fat = st.number_input("% Gordura", 0.0, 80.0, 0.0, 0.1)
            muscle = st.number_input("% Músculo", 0.0, 80.0, 0.0, 0.1)
            water = st.number_input("% Água", 0.0, 80.0, 0.0, 0.1)
            visceral = st.number_input("Gordura visceral (índice)", 0.0, 60.0, 0.0, 0.5)
            bmr = st.number_input("BMR (kcal)", 0.0, 6000.0, 0.0, 10.0)
            note = st.text_input("Obs (opcional)")
            ok = st.form_submit_button("Salvar balança ✅")
            if ok:
                with engine.begin() as c:
                    c.execute(text("""
                        INSERT INTO body (ts, weight, fat, muscle, water, visceral, bmr, note)
                        VALUES (:ts,:w,:f,:m,:wa,:v,:b,:n)
                    """), {
                        "ts": dt_for_db(d, tt),
                        "w": float(weight),
                        "f": float(fat) if fat>0 else None,
                        "m": float(muscle) if muscle>0 else None,
                        "wa": float(water) if water>0 else None,
                        "v": float(visceral) if visceral>0 else None,
                        "b": float(bmr) if bmr>0 else None,
                        "n": note.strip() if note else None
                    })
                st.success("Balança salva!")

    with tab_sleep:
        with st.form("sleep_form", clear_on_submit=True):
            sd = st.date_input("Data do sono", value=date.today(), key="sd")
            duration = st.number_input("Duração (min)", 0, 1000, 0, 5)
            score = st.number_input("Score (0-100)", 0, 100, 0, 1)
            note = st.text_input("Obs (opcional)", key="sn")
            ok = st.form_submit_button("Salvar sono ✅")
            if ok:
                with engine.begin() as c:
                    c.execute(text("""
                        INSERT INTO sleep (sleep_date, duration, score, note)
                        VALUES (:d,:du,:s,:n)
                    """), {
                        "d": sd.isoformat() if backend=="sqlite" else sd,
                        "du": int(duration) if duration>0 else None,
                        "s": int(score) if score>0 else None,
                        "n": note.strip() if note else None
                    })
                st.success("Sono salvo!")

    with tab_wo:
        with st.form("wo_form", clear_on_submit=True):
            d = st.date_input("Data", value=date.today(), key="wd")
            tt = st.time_input("Hora", value=datetime.now().time().replace(second=0, microsecond=0), key="wt")
            activity = st.selectbox("Atividade", ["Musculação","Esteira","Beach tênis","Pickleball","Tênis","Outro"])
            duration = st.number_input("Duração (min)", 0, 600, 60, 5)
            intensity = st.selectbox("Intensidade", ["baixa","média","alta"], index=1)
            avg_hr = st.number_input("FC média (opcional)", 0, 220, 0, 1)
            note = st.text_input("Obs (opcional)", key="wn")
            ok = st.form_submit_button("Salvar treino ✅")
            if ok:
                with engine.begin() as c:
                    c.execute(text("""
                        INSERT INTO workouts (ts, activity, duration, intensity, avg_hr, note)
                        VALUES (:ts,:a,:d,:i,:h,:n)
                    """), {
                        "ts": dt_for_db(d, tt),
                        "a": activity,
                        "d": int(duration) if duration>0 else None,
                        "i": intensity,
                        "h": int(avg_hr) if avg_hr>0 else None,
                        "n": note.strip() if note else None
                    })
                st.success("Treino salvo!")

elif page == "Dashboard":
    st.subheader("📊 Pressão + BPM (comparação)")
    df = read_df("SELECT * FROM bp ORDER BY id DESC LIMIT 180")
    if df.empty:
        st.info("Sem dados ainda.")
    else:
        df["ts"] = pd.to_datetime(df["ts"])
        df["class"] = df.apply(lambda r: classify(int(r["systolic"]), int(r["diastolic"])), axis=1)
        for per in ["matinal", "vespertina", "noturna"]:
            sub = df[df["period"] == per].copy()
            st.markdown(f"**{per.capitalize()}**")
            if sub.empty:
                st.info("Sem dados")
                continue
            sub = sub.sort_values("ts")
            st.line_chart(sub.set_index("ts")[["systolic","diastolic","bpm"]], height=240)
            last = sub.iloc[-1]
            st.caption(f"Última: {int(last['systolic'])}/{int(last['diastolic'])} • {last['class']} | BPM médio: {int(round(sub['bpm'].mean()))}")

else:
    st.subheader("🧰 Backup / Restore")
    st.markdown("### Backup")
    b = export_backup_zip()
    st.download_button("⬇️ Baixar backup (ZIP de CSVs)", data=b, file_name="health_backup.zip", mime="application/zip", use_container_width=True)

    st.divider()
    st.markdown("### Restore")
    up = st.file_uploader("Envie um backup health_backup.zip", type=["zip"])
    if up is not None:
        if st.button("Restaurar (substitui os dados atuais)", type="primary"):
            msg = restore_backup_zip(up.read())
            if msg.startswith("Restore"):
                st.success(msg)
            else:
                st.error(msg)
