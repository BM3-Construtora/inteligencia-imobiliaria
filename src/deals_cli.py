"""CLI para gerenciar bm3_deals (Track D — feedback loop).

Uso:
    python -m src.deals_cli add <listing_id> <stage>
    python -m src.deals_cli update <deal_id> --offer 200000 --notes "..."
    python -m src.deals_cli outcome <deal_id> --margin 22.5 --payback 18
    python -m src.deals_cli list [--stage closed_won]
    python -m src.deals_cli import-stalled [--addr1 "..."] [--addr2 "..."]
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any, Optional

from src.db import get_client
from src.feedback_loop import (
    VALID_STAGES,
    record_deal,
    record_outcome,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_add(args: argparse.Namespace) -> int:
    stage = args.stage
    if stage not in VALID_STAGES:
        print(f"Erro: stage inválido. Valores: {sorted(VALID_STAGES)}")
        return 2
    try:
        deal_id = record_deal(
            listing_id=args.listing_id,
            stage=stage,
            notes=args.notes,
            created_by=args.created_by or "matheus",
        )
    except Exception as exc:
        print(f"Erro: {exc}")
        return 1
    print(f"OK: deal id={deal_id} listing_id={args.listing_id} stage={stage}")
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    db = get_client()
    res = db.table("bm3_deals").select("listing_id, stage").eq("id", args.id).limit(1).execute()
    if not res.data:
        print(f"Erro: deal id={args.id} não encontrado")
        return 1
    current = res.data[0]
    new_stage = args.stage or current["stage"]

    fields: dict[str, Any] = {}
    if args.offer is not None:
        fields["offered_price"] = args.offer
    if args.accepted is not None:
        fields["accepted_price"] = args.accepted
    if args.asking is not None:
        fields["asking_price"] = args.asking
    if args.notes is not None:
        fields["notes"] = args.notes
    if args.rejection_reason is not None:
        fields["rejection_reason"] = args.rejection_reason

    try:
        record_deal(
            listing_id=current.get("listing_id"),
            stage=new_stage,
            deal_id=args.id,
            **fields,
        )
    except Exception as exc:
        print(f"Erro: {exc}")
        return 1
    print(f"OK: deal id={args.id} atualizado (stage={new_stage}, fields={list(fields.keys())})")
    return 0


def cmd_outcome(args: argparse.Namespace) -> int:
    try:
        record_outcome(args.id, args.margin, args.payback)
    except Exception as exc:
        print(f"Erro: {exc}")
        return 1
    print(f"OK: outcome id={args.id} margem={args.margin}% payback={args.payback}m")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    db = get_client()
    q = (
        db.table("bm3_deals")
        .select("id, listing_id, stage, asking_price, offered_price, accepted_price, "
                "hunter_score_at_visit, avm_p50_at_visit, viability_margin_at_visit, "
                "actual_outcome_margin_pct, created_at")
        .order("id", desc=True)
        .limit(args.limit)
    )
    if args.stage:
        q = q.eq("stage", args.stage)
    res = q.execute()
    rows = res.data or []
    if not rows:
        print("(nenhum deal)")
        return 0
    _print_table(rows)
    return 0


def cmd_import_stalled(args: argparse.Namespace) -> int:
    """Importa as 2 casas paradas da BM3 como casos retrospectivos.

    Não inventa dados — cria placeholders stage='closed_lost' com NULLs
    e nota explícita para preenchimento manual.
    """
    db = get_client()
    placeholders = [
        {
            "stage": "closed_lost",
            "notes": (
                "CASO RETROSPECTIVO — preencher dados reais via `update`. "
                f"Endereço aprox: {args.addr1 or 'TODO: preencher endereço da casa parada #1'}. "
                "TODO: asking_price, offered_price, viability_margin_at_visit, "
                "actual_outcome_margin_pct, rejection_reason."
            ),
            "rejection_reason": "TODO: preencher motivo (obra parou / mercado / financiamento)",
            "created_by": "matheus",
        },
        {
            "stage": "closed_lost",
            "notes": (
                "CASO RETROSPECTIVO — preencher dados reais via `update`. "
                f"Endereço aprox: {args.addr2 or 'TODO: preencher endereço da casa parada #2'}. "
                "TODO: asking_price, offered_price, viability_margin_at_visit, "
                "actual_outcome_margin_pct, rejection_reason."
            ),
            "rejection_reason": "TODO: preencher motivo (obra parou / mercado / financiamento)",
            "created_by": "matheus",
        },
    ]

    created_ids: list[int] = []
    for p in placeholders:
        # Idempotência: não duplica se já existe placeholder com notas iniciando assim
        existing = (
            db.table("bm3_deals")
            .select("id, notes")
            .eq("stage", "closed_lost")
            .like("notes", "CASO RETROSPECTIVO%")
            .execute()
        )
        already = [r for r in (existing.data or [])
                   if (args.addr1 and args.addr1 in (r.get("notes") or ""))
                   or (args.addr2 and args.addr2 in (r.get("notes") or ""))]
        if already and (args.addr1 or args.addr2):
            print(f"Skip: já existe placeholder com endereço informado (id={already[0]['id']})")
            continue
        res = db.table("bm3_deals").insert(p).execute()
        if res.data:
            created_ids.append(int(res.data[0]["id"]))

    if not created_ids:
        print("Nada importado (já existe ou falhou).")
        return 0

    print(f"OK: importados {len(created_ids)} casos retrospectivos. IDs: {created_ids}")
    print("Use `update <deal_id> --notes ... --asking ... --offer ...` para preencher.")
    return 0


# ---------------------------------------------------------------------------
# Pretty table
# ---------------------------------------------------------------------------

def _fmt(v: Any) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.2f}"
    s = str(v)
    return s if len(s) <= 24 else s[:23] + "…"


def _print_table(rows: list[dict[str, Any]]) -> None:
    cols = ["id", "listing_id", "stage", "asking_price", "offered_price",
            "accepted_price", "hunter_score_at_visit", "avm_p50_at_visit",
            "viability_margin_at_visit", "actual_outcome_margin_pct", "created_at"]
    headers = {c: c for c in cols}
    widths = {c: max(len(headers[c]), *(len(_fmt(r.get(c))) for r in rows)) for c in cols}

    def line(values: dict[str, Any]) -> str:
        return " | ".join(_fmt(values.get(c)).ljust(widths[c]) for c in cols)

    print(line(headers))
    print("-+-".join("-" * widths[c] for c in cols))
    for r in rows:
        print(line(r))


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="deals_cli", description="Manage bm3_deals (Track D)")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("add", help="Registra um novo deal (visita/oferta/etc)")
    a.add_argument("listing_id", type=int, nargs="?", default=None,
                   help="ID da listing (use 0 ou omita para off-market)")
    a.add_argument("stage", choices=sorted(VALID_STAGES))
    a.add_argument("--notes")
    a.add_argument("--created-by", "--created_by", dest="created_by")
    a.set_defaults(func=cmd_add)

    u = sub.add_parser("update", help="Atualiza um deal existente")
    u.add_argument("id", type=int)
    u.add_argument("--stage", choices=sorted(VALID_STAGES))
    u.add_argument("--offer", type=float, help="offered_price")
    u.add_argument("--accepted", type=float, help="accepted_price")
    u.add_argument("--asking", type=float, help="asking_price")
    u.add_argument("--notes")
    u.add_argument("--rejection-reason", "--rejection_reason", dest="rejection_reason")
    u.set_defaults(func=cmd_update)

    o = sub.add_parser("outcome", help="Registra resultado real (margem/payback)")
    o.add_argument("id", type=int)
    o.add_argument("--margin", type=float, required=True, help="margem real (%)")
    o.add_argument("--payback", type=int, required=True, help="payback real (meses)")
    o.set_defaults(func=cmd_outcome)

    l = sub.add_parser("list", help="Lista deals")
    l.add_argument("--stage", choices=sorted(VALID_STAGES))
    l.add_argument("--limit", type=int, default=50)
    l.set_defaults(func=cmd_list)

    i = sub.add_parser("import-stalled", help="Importa as 2 casas paradas BM3 como retrospectiva")
    i.add_argument("--addr1", help="Endereço aproximado casa parada #1")
    i.add_argument("--addr2", help="Endereço aproximado casa parada #2")
    i.set_defaults(func=cmd_import_stalled)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    # listing_id=0 ou None vira None (off-market)
    if getattr(args, "listing_id", None) == 0:
        args.listing_id = None
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
