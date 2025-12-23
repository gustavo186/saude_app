# Saúde & Performance — v11.2

Agora inclui a **balança/bioimpedância** em tudo:
- Inserção manual (peso, %gordura, %músculo, %água, visceral, BMR)
- Dashboard
- Forecast (>=30 dias) para: peso, %gordura, %músculo, %água (se houver dados)
- Exportação CSV inclui body.csv

Forecast:
- Tenta Prophet; se falhar, usa regressão linear como fallback.