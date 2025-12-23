# Saúde & Performance — v4 (Hybrid)

## O que é "Hybrid"
- **Streamlit Cloud** roda o app na internet.
- **Banco local (arquivo)** no Streamlit Cloud **não é confiável** (pode reiniciar e apagar).
- Então este app tem 2 modos:
  1) **Cloud mode (persistente)**: usa Postgres via `DATABASE_URL`.
  2) **Local mode**: se não houver `DATABASE_URL`, usa SQLite (`health.db`) no seu computador.

Além disso, tem **Backup/Restore** por ZIP de CSVs:
- Baixe um backup ZIP com todos os dados
- Restaure depois enviando o ZIP

## Variáveis de ambiente (Secrets)
APP_USER=seu_usuario
APP_PASSWORD=sua_senha

Opcional (para persistência real na Cloud):
DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DBNAME

Local (quando rodar no seu PC):
DB_PATH=health.db