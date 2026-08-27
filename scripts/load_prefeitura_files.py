"""Carga dos extratos oficiais da Prefeitura de Marília no Supabase.

Alimenta as tabelas criadas na migration 059:
  itbi_loteamento  <- TOTAL_DE_ITIBI_*.xlsx  (agregado por loteamento)
  alvaras          <- Projetos_Obras_Alvara_e_Habite_se_*.xls

Também preenche itbi_loteamento.bairro_canonico via matching fuzzy (Jaccard de
tokens) contra os bairros reais de `listings`, no mesmo formato de
norm_bairro() (initcap + trim). Matches com jaccard < 0.6 ficam NULL para
revisão manual.

Idempotente: apaga as linhas do mesmo source_file antes de inserir.

Uso:
    python scripts/load_prefeitura_files.py <itbi.xlsx> <alvaras.xls>

Requer: pandas, openpyxl, xlrd. Credenciais via .env (SUPABASE_URL/SUPABASE_KEY,
precisa ser service_role para escrever).
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

import pandas as pd

BATCH = 500
ITBI_PERIODO = ("2015-01-01", "2026-08-17")  # do cabeçalho do extrato
ANO_MIN, ANO_MAX = 1900, 2026

# tokens genéricos ignorados no matching loteamento <-> bairro
STOPWORDS = {
    "JD", "JARDIM", "PQ", "PARQUE", "RES", "RESID", "RESIDENCIAL", "RESIDENCIAIS",
    "LOT", "LOTEAMENTO", "NUC", "NUCLEO", "HAB", "HABITACIONAL", "CJ", "CONJ",
    "CONJUNTO", "VL", "VILA", "ANEXO", "PROLONGAMENTO", "PROLONG", "DE", "DA",
    "DO", "DAS", "DOS", "E", "I", "II", "III", "IV",
}


def load_env() -> tuple[str, str]:
    env: dict[str, str] = {}
    for line in Path(".env").read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    url = env.get("SUPABASE_URL")
    key = env.get("SUPABASE_KEY") or env.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        sys.exit("SUPABASE_URL/SUPABASE_KEY não encontrados no .env")
    return url, key


def rest(url: str, key: str, method: str, path: str, body: object = None,
         prefer: str | None = None) -> tuple[int, dict]:
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    if prefer:
        headers["Prefer"] = prefer
    req = urllib.request.Request(url + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req) as r:
        return r.status, dict(r.headers)


def insert_batches(url: str, key: str, table: str, rows: list[dict]) -> None:
    for i in range(0, len(rows), BATCH):
        rest(url, key, "POST", f"/rest/v1/{table}", rows[i : i + BATCH],
             prefer="return=minimal")
    print(f"  {table}: {len(rows)} linhas inseridas")


def delete_source(url: str, key: str, table: str, source_file: str) -> None:
    q = urllib.parse.quote(source_file)
    rest(url, key, "DELETE", f"/rest/v1/{table}?source_file=eq.{q}")


def token_set(name: str) -> frozenset[str]:
    s = unicodedata.normalize("NFKD", name.upper()).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return frozenset(t for t in s.split() if t not in STOPWORDS and len(t) > 1)


def fetch_bairros_listings(url: str, key: str) -> list[str]:
    """Bairros distintos de listings, no formato de norm_bairro (initcap+trim)."""
    seen: dict[str, int] = {}
    offset = 0
    while True:
        req = urllib.request.Request(
            f"{url}/rest/v1/listings?select=neighborhood&limit=1000&offset={offset}",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
        )
        with urllib.request.urlopen(req) as r:
            batch = json.loads(r.read())
        for row in batch:
            n = (row["neighborhood"] or "").strip()
            if n:
                canon = n.title()
                seen[canon] = seen.get(canon, 0) + 1
        if len(batch) < 1000:
            break
        offset += 1000
    # exige >=3 anúncios: evita casar com typo raro de bairro
    return [b for b, c in seen.items() if c >= 3]


def parse_itbi(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, header=2, usecols=[3, 4, 5])
    df.columns = ["loteamento", "qtde", "valor"]
    df = df.dropna(subset=["loteamento"])
    df["qtde"] = pd.to_numeric(df["qtde"], errors="coerce")
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    df = df.dropna(subset=["qtde", "valor"])
    df["loteamento"] = df["loteamento"].astype(str).str.strip()
    # linha de total geral do relatório não é loteamento
    df = df[~df["loteamento"].str.upper().str.startswith("TOTAL")]
    return df


def match_bairros(loteamentos: list[str], bairros: list[str]) -> dict[str, tuple[str, float]]:
    keys = {b: token_set(b) for b in bairros}
    result: dict[str, tuple[str, float]] = {}
    for lot in loteamentos:
        lk = token_set(lot)
        if not lk:
            continue
        best, best_j = None, 0.0
        for b, bk in keys.items():
            if not bk:
                continue
            j = len(lk & bk) / len(lk | bk)
            if j > best_j:
                best_j, best = j, b
        if best and best_j >= 0.6:
            result[lot] = (best, round(best_j, 2))
    return result


def num_br(series: pd.Series) -> pd.Series:
    """'2.443,2' -> 2443.2"""
    return pd.to_numeric(
        series.astype(str)
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False),
        errors="coerce",
    )


def parse_date_safe(value: object) -> tuple[str | None, str | None, bool]:
    """(iso_date, raw_se_invalida, suspeita)."""
    if pd.isna(value):
        return None, None, False
    raw = str(value).strip()
    try:
        dt = datetime.strptime(raw, "%d/%m/%Y %H:%M:%S")
    except ValueError:
        try:
            dt = pd.to_datetime(raw, dayfirst=True).to_pydatetime()
        except Exception:
            return None, raw, True
    if not (ANO_MIN <= dt.year <= ANO_MAX):
        return None, raw, True
    return dt.date().isoformat(), None, False


def parse_alvaras(path: Path) -> list[dict]:
    df = pd.read_excel(path, header=2)
    df["area_construida"] = num_br(df["TotalAreaConstruida"])
    df["area_terreno"] = num_br(df["AreaTerreno"])
    rows: list[dict] = []
    for r in df.itertuples(index=False):
        alvara_dt, alvara_raw, s1 = parse_date_safe(r.Alvara_dtEmissao)
        habitese_dt, _, s2 = parse_date_safe(r.Habitese_dtEmissao)

        def txt(v: object) -> str | None:
            return None if pd.isna(v) else str(v).strip() or None

        rows.append({
            "inscricao": str(r.Inscricao).strip(),
            "alvara_dt": alvara_dt,
            "alvara_dt_raw": alvara_raw,
            "processo_adm": txt(r.ProcessoAdm),
            "cep": txt(r.ObraCep),
            "bairro_raw": txt(r.ObraBairro),
            "logradouro": txt(r.ObraLogradouro),
            "numero": txt(r.ObraNumero),
            "complemento": txt(r.ObraComplemento),
            "tipo_edificacao": txt(r.TipodeEdificacao),
            "area_construida": None if pd.isna(r.area_construida) else round(float(r.area_construida), 2),
            "area_terreno": None if pd.isna(r.area_terreno) else round(float(r.area_terreno), 2),
            "habitese_dt": habitese_dt,
            "habitese_numero": txt(r.Habitese_Numero),
            "data_suspeita": s1 or s2,
            "source_file": path.name,
        })
    return rows


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    itbi_path, alvaras_path = Path(sys.argv[1]), Path(sys.argv[2])
    url, key = load_env()

    print("ITBI: parseando", itbi_path.name)
    itbi = parse_itbi(itbi_path)
    print(f"  {len(itbi)} loteamentos, {int(itbi.qtde.sum())} transações")

    print("De-para: buscando bairros de listings...")
    bairros = fetch_bairros_listings(url, key)
    matches = match_bairros(itbi["loteamento"].tolist(), bairros)
    print(f"  {len(matches)}/{len(itbi)} loteamentos casados (jaccard >= 0.6)")

    itbi_rows = []
    for r in itbi.itertuples(index=False):
        m = matches.get(r.loteamento)
        itbi_rows.append({
            "loteamento": r.loteamento,
            "qtde_itbi": int(r.qtde),
            "valor_arrecadado": round(float(r.valor), 2),
            "periodo_inicio": ITBI_PERIODO[0],
            "periodo_fim": ITBI_PERIODO[1],
            "bairro_canonico": m[0] if m else None,
            "match_confidence": m[1] if m else None,
            "source_file": itbi_path.name,
        })
    delete_source(url, key, "itbi_loteamento", itbi_path.name)
    insert_batches(url, key, "itbi_loteamento", itbi_rows)

    print("Alvarás: parseando", alvaras_path.name, "(demora um pouco)")
    alvara_rows = parse_alvaras(alvaras_path)
    suspeitas = sum(1 for r in alvara_rows if r["data_suspeita"])
    print(f"  {len(alvara_rows)} linhas ({suspeitas} com data suspeita)")
    delete_source(url, key, "alvaras", alvaras_path.name)
    insert_batches(url, key, "alvaras", alvara_rows)

    print("Carga concluída.")


if __name__ == "__main__":
    main()
