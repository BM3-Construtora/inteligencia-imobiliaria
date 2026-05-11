"""CLI helper to add/list/update company_projects via terminal (no dashboard required)."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Optional

from src.db import get_client

logger = logging.getLogger(__name__)

VALID_TYPES = {"mcmv_faixa1", "mcmv_faixa2", "mcmv_faixa3", "casa_padrao"}
VALID_STATUS = {"planning", "approved", "construction", "selling", "sold_out", "cancelled"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def cmd_add(args: argparse.Namespace) -> int:
    if args.project_type and args.project_type not in VALID_TYPES:
        print(f"Erro: project_type deve ser um de {sorted(VALID_TYPES)}")
        return 2
    if args.status and args.status not in VALID_STATUS:
        print(f"Erro: status deve ser um de {sorted(VALID_STATUS)}")
        return 2

    row: dict[str, Any] = {
        "name": args.name,
        "neighborhood": args.neighborhood,
        "project_type": args.project_type or "casa_padrao",
        "units": args.units,
        "status": args.status or "planning",
        "notes": args.notes,
    }
    if args.land_cost is not None:
        row["land_cost"] = args.land_cost
    if args.construction_cost_projected is not None:
        row["construction_cost_projected"] = args.construction_cost_projected

    # sale_price_per_unit * units → revenue_projected
    if args.sale_price_per_unit is not None:
        row["revenue_projected"] = float(args.sale_price_per_unit) * int(args.units)

    # construction_months armazenado em notes (não há coluna dedicada)
    if args.construction_months is not None:
        extra = f"[construction_months={args.construction_months}]"
        row["notes"] = f"{row.get('notes') or ''} {extra}".strip()

    # Compute margin_projected_pct if possível
    rev = row.get("revenue_projected")
    land = row.get("land_cost")
    constr = row.get("construction_cost_projected")
    if rev and (land is not None or constr is not None):
        total_cost = float(land or 0) + float(constr or 0)
        if total_cost > 0:
            row["margin_projected_pct"] = round(((float(rev) - total_cost) / float(rev)) * 100, 2)

    row = {k: v for k, v in row.items() if v is not None}

    db = get_client()
    res = db.table("company_projects").insert(row).execute()
    if res.data:
        new_id = res.data[0]["id"]
        print(f"OK: projeto criado id={new_id} name='{args.name}'")
        return 0
    print("Erro: insert sem retorno")
    return 1


def cmd_list(args: argparse.Namespace) -> int:
    db = get_client()
    q = db.table("company_projects").select(
        "id, name, neighborhood, project_type, units, status, "
        "land_cost, construction_cost_projected, revenue_projected, "
        "margin_projected_pct, margin_actual_pct"
    ).order("id", desc=True)
    if args.status:
        q = q.eq("status", args.status)
    res = q.execute()
    rows = res.data or []
    if not rows:
        print("(nenhum projeto)")
        return 0
    _print_table(rows)
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    update: dict[str, Any] = {}
    if args.status:
        if args.status not in VALID_STATUS:
            print(f"Erro: status inválido. Valores: {sorted(VALID_STATUS)}")
            return 2
        update["status"] = args.status
    if args.name is not None:
        update["name"] = args.name
    if args.neighborhood is not None:
        update["neighborhood"] = args.neighborhood
    if args.notes is not None:
        update["notes"] = args.notes
    if not update:
        print("Nada para atualizar")
        return 2
    update["updated_at"] = _now_iso()

    db = get_client()
    res = db.table("company_projects").update(update).eq("id", args.id).execute()
    if res.data:
        print(f"OK: projeto id={args.id} atualizado ({list(update.keys())})")
        return 0
    print(f"Erro: projeto id={args.id} não encontrado")
    return 1


def cmd_set_outcome(args: argparse.Namespace) -> int:
    update: dict[str, Any] = {"updated_at": _now_iso()}
    if args.revenue_actual is not None:
        update["revenue_actual"] = args.revenue_actual
    if args.construction_cost_actual is not None:
        update["construction_cost_actual"] = args.construction_cost_actual
    if args.margin_actual_pct is not None:
        update["margin_actual_pct"] = args.margin_actual_pct
    if args.completed_at is not None:
        update["completed_at"] = args.completed_at
    if len(update) == 1:
        print("Nada para atualizar (informe ao menos um campo de outcome)")
        return 2

    db = get_client()
    res = db.table("company_projects").update(update).eq("id", args.id).execute()
    if res.data:
        print(f"OK: outcome do projeto id={args.id} salvo")
        return 0
    print(f"Erro: projeto id={args.id} não encontrado")
    return 1


def _print_table(rows: list[dict[str, Any]]) -> None:
    cols = ["id", "name", "neighborhood", "project_type", "units", "status",
            "land_cost", "construction_cost_projected", "revenue_projected",
            "margin_projected_pct", "margin_actual_pct"]
    headers = {c: c for c in cols}
    widths = {c: max(len(str(headers[c])), *(len(_fmt(r.get(c))) for r in rows)) for c in cols}

    def line(values: dict[str, Any]) -> str:
        return " | ".join(_fmt(values.get(c)).ljust(widths[c]) for c in cols)

    print(line(headers))
    print("-+-".join("-" * widths[c] for c in cols))
    for r in rows:
        print(line(r))


def _fmt(v: Any) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="projects_cli", description="Manage company_projects")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("add", help="Add a new project")
    a.add_argument("--name", required=True)
    a.add_argument("--neighborhood")
    a.add_argument("--project-type", "--project_type", dest="project_type",
                   choices=sorted(VALID_TYPES))
    a.add_argument("--units", type=int, default=1)
    a.add_argument("--land-cost", "--land_cost", dest="land_cost", type=float)
    a.add_argument("--construction-cost-projected", "--construction_cost_projected",
                   dest="construction_cost_projected", type=float)
    a.add_argument("--sale-price-per-unit", "--sale_price_per_unit",
                   dest="sale_price_per_unit", type=float)
    a.add_argument("--construction-months", "--construction_months",
                   dest="construction_months", type=int)
    a.add_argument("--status", choices=sorted(VALID_STATUS), default="planning")
    a.add_argument("--notes")
    a.set_defaults(func=cmd_add)

    l = sub.add_parser("list", help="List projects")
    l.add_argument("--status", choices=sorted(VALID_STATUS))
    l.set_defaults(func=cmd_list)

    u = sub.add_parser("update", help="Update project metadata")
    u.add_argument("--id", type=int, required=True)
    u.add_argument("--status", choices=sorted(VALID_STATUS))
    u.add_argument("--name")
    u.add_argument("--neighborhood")
    u.add_argument("--notes")
    u.set_defaults(func=cmd_update)

    o = sub.add_parser("set-outcome", help="Save actual outcome numbers")
    o.add_argument("--id", type=int, required=True)
    o.add_argument("--revenue-actual", "--revenue_actual",
                   dest="revenue_actual", type=float)
    o.add_argument("--construction-cost-actual", "--construction_cost_actual",
                   dest="construction_cost_actual", type=float)
    o.add_argument("--margin-actual-pct", "--margin_actual_pct",
                   dest="margin_actual_pct", type=float)
    o.add_argument("--completed-at", "--completed_at",
                   dest="completed_at", help="YYYY-MM-DD")
    o.set_defaults(func=cmd_set_outcome)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
