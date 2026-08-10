#!/usr/bin/env bash
# Reorganiza sql/*.sql -> supabase/migrations/ no layout do Supabase CLI.
#
# Converte cada arquivo para uma versão única de 14 dígitos, crescente, na ordem
# atual (preserva a sequência e resolve as colisões de prefixo 017/030/031/032/052,
# que o CLI rejeitaria por exigir versão única).
#
# Uso:
#   scripts/migrate_to_supabase_layout.sh          # dry-run: só mostra o plano
#   scripts/migrate_to_supabase_layout.sh --apply  # executa os git mv
#
# Rode num commit dedicado, quando a branch parar de receber migrations de
# outras sessões. Depois: atualize as referências textuais a sql/NNN_*.sql em
# comentários/docstrings, e faça o baseline (supabase migration repair) antes de
# ativar o CD. Ver docs/adr/0001-cd-migrations-supabase-cli.md.
set -euo pipefail

APPLY=false
[ "${1:-}" = "--apply" ] && APPLY=true

DEST="supabase/migrations"
mkdir -p "$DEST"

i=1
count=$(ls sql/*.sql 2>/dev/null | wc -l | tr -d ' ')
if [ "$count" -gt 57 ]; then
  echo "AVISO: $count migrations — o esquema de versão (segundos 01-59) satura acima de 59."
  echo "Ajuste a base de timestamp no script antes de aplicar."
  exit 1
fi

for f in $(ls sql/*.sql | sort); do
  desc=$(basename "$f" | sed -E 's/^[0-9]+_//')
  ver=$(printf "202501010000%02d" "$i")
  dest="${DEST}/${ver}_${desc}"
  if $APPLY; then
    git mv "$f" "$dest"
    echo "moved  $f -> $dest"
  else
    echo "would move  $f -> $dest"
  fi
  i=$((i + 1))
done

if ! $APPLY; then
  echo ""
  echo "Dry-run. Rode com --apply para executar os git mv."
fi
