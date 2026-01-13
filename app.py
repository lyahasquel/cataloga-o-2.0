import streamlit as st
import sqlite3
import datetime
import pandas as pd
import hashlib
import time

DB_NAME = "catalogo_caixas.db"
TEMPO_SESSAO = 60 * 60  # 1 hora

# ======================================================
# BANCO DE DADOS
# ======================================================

def conectar():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def criar_tabelas_seguranca():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('usuario','admin'))
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessoes_ativas (
            username TEXT PRIMARY KEY,
            login_time TEXT,
            ultima_atividade TEXT
        )
    """)

    conn.commit()
    conn.close()

# ======================================================
# SEGURANÇA
# ======================================================

def hash_senha(senha):
    return hashlib.sha256(senha.encode()).hexdigest()

def autenticar(username, senha):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT role FROM usuarios
        WHERE username = ? AND password_hash = ?
    """, (username, hash_senha(senha)))
    res = cursor.fetchone()
    conn.close()
    return res

# ======================================================
# CONTROLE DE SESSÃO
# ======================================================

def registrar_login(username):
    agora = datetime.datetime.now().isoformat()
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO sessoes_ativas (username, login_time, ultima_atividade)
        VALUES (?, ?, ?)
        ON CONFLICT(username) DO UPDATE SET
            ultima_atividade = excluded.ultima_atividade
    """, (username, agora, agora))
    conn.commit()
    conn.close()

def registrar_logout(username):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessoes_ativas WHERE username = ?", (username,))
    conn.commit()
    conn.close()

def verificar_expiracao():
    if st.session_state.logado:
        if time.time() - st.session_state.ultima_atividade > TEMPO_SESSAO:
            st.warning("Sessão expirada por inatividade.")
            registrar_logout(st.session_state.username)
            st.session_state.clear()
            st.rerun()

# ======================================================
# FUNÇÕES ORIGINAIS DO APP
# ======================================================

def gerar_codigo_tripla():
    conn = conectar()
    cursor = conn.cursor()

    ano = datetime.datetime.now().year
    cursor.execute("SELECT codigo_tripla FROM caixa_tripla ORDER BY id_tripla DESC LIMIT 1")
    ultimo = cursor.fetchone()

    numero = 1 if ultimo is None else int(ultimo[0].split("-")[2]) + 1
    conn.close()
    return f"T-{ano}-{numero:03d}", ano

def inserir_assunto(nome):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO assuntos (nome_assunto) VALUES (?)", (nome,))
    conn.commit()
    cursor.execute("SELECT id_assunto FROM assuntos WHERE nome_assunto=?", (nome,))
    assunto_id = cursor.fetchone()[0]
    conn.close()
    return assunto_id

def inserir_localizacao(local):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO localizacao (estante, prateleira, descricao)
        VALUES (?, ?, ?)
    """, (local, "", ""))
    conn.commit()
    cursor.execute("SELECT id_local FROM localizacao ORDER BY id_local DESC LIMIT 1")
    local_id = cursor.fetchone()[0]
    conn.close()
    return local_id

def cadastrar_caixa_tripla(assunto, data, local, obs):
    codigo, ano = gerar_codigo_tripla()
    assunto_id = inserir_assunto(assunto)
    local_id = inserir_localizacao(local)

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO caixa_tripla
        (codigo_tripla, ano, assunto_id, data_entrada, local_id, observacoes)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (codigo, ano, assunto_id, data, local_id, obs))

    cursor.execute("SELECT id_tripla FROM caixa_tripla WHERE codigo_tripla=?", (codigo,))
    tripla_id = cursor.fetchone()[0]

    for letra in ["A", "B", "C"]:
        cursor.execute("""
            INSERT INTO caixa_individual
            (codigo_box, letra, tripla_id, assunto_id, data_entrada)
            VALUES (?, ?, ?, ?, ?)
        """, (f"{codigo}-{letra}", letra, tripla_id, assunto_id, data))

    conn.commit()
    conn.close()
    return codigo

def listar_caixas():
    conn = conectar()
    df = pd.read_sql_query("""
        SELECT 
            c.codigo_box AS "Código Caixa",
            t.codigo_tripla AS "Caixa Tripla",
            a.nome_assunto AS "Assunto",
            c.data_entrada AS "Data Entrada",
            c.status AS "Status"
        FROM caixa_individual c
        JOIN caixa_tripla t ON c.tripla_id = t.id_tripla
        JOIN assuntos a ON c.assunto_id = a.id_assunto
        ORDER BY t.codigo_tripla, c.letra
    """, conn)
    conn.close()
    return df

# ======================================================
# ESTADO INICIAL
# ======================================================

if "logado" not in st.session_state:
    st.session_state.logado = False
    st.session_state.username = None
    st.session_state.role = None
    st.session_state.ultima_atividade = time.time()

criar_tabelas_seguranca()
verificar_expiracao()

# ======================================================
# LOGIN (BLOQUEIO TOTAL)
# ======================================================

if not st.session_state.logado:
    st.set_page_config(page_title="Login", layout="centered")
    st.title("🔐 Login")

    user = st.text_input("Usuário")
    senha = st.text_input("Senha", type="password")

    if st.button("Entrar"):
        auth = autenticar(user, senha)
        if auth:
            st.session_state.logado = True
            st.session_state.username = user
            st.session_state.role = auth[0]
            st.session_state.ultima_atividade = time.time()
            registrar_login(user)
            st.rerun()
        else:
            st.error("Usuário ou senha inválidos")

    st.stop()

# ======================================================
# APP PRINCIPAL
# ======================================================

st.session_state.ultima_atividade = time.time()

st.set_page_config(page_title="Catálogo de Caixas", layout="wide")
st.title("📦 Sistema de Catalogação de Caixas")

st.sidebar.write(f"👤 {st.session_state.username}")
st.sidebar.write(f"🔑 {st.session_state.role}")

if st.sidebar.button("Sair"):
    registrar_logout(st.session_state.username)
    st.session_state.clear()
    st.rerun()

menu = st.sidebar.selectbox(
    "Menu",
    ["Cadastrar Caixa Tripla", "Listar Caixas", "Exportar para Excel"]
)

# -----------------------------
# CADASTRO
# -----------------------------
if menu == "Cadastrar Caixa Tripla":
    st.header("➕ Nova Caixa Tripla")

    with st.form("form_tripla"):
        assunto = st.text_input("Assunto")
        data = st.date_input("Data de entrada", datetime.date.today())
        local = st.text_input("Localização física")
        obs = st.text_area("Observações")
        salvar = st.form_submit_button("Salvar")

    if salvar:
        if assunto.strip() == "" or local.strip() == "":
            st.error("Assunto e Localização são obrigatórios.")
        else:
            codigo = cadastrar_caixa_tripla(assunto, str(data), local, obs)
            st.success(f"Caixa tripla {codigo} criada com sucesso (A, B e C).")

# -----------------------------
# LISTAGEM
# -----------------------------
elif menu == "Listar Caixas":
    st.header("📋 Lista de Caixas")
    st.dataframe(listar_caixas(), use_container_width=True)

# -----------------------------
# EXPORTAÇÃO
# -----------------------------
elif menu == "Exportar para Excel":
    st.header("📥 Exportar dados")
    df = listar_caixas()
    csv = df.to_csv(index=False).encode("utf-8")

    st.download_button(
        "Baixar arquivo Excel (CSV)",
        csv,
        "catalogo_caixas.csv",
        "text/csv"
    )
