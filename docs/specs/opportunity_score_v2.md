# Spec — Opportunity Score v2 (plugar o cérebro V2 no funil)

## Problema

O `hunter.py` decide qual terreno vira oportunidade usando só sinais base
(preço, preço/m², área, MCMV, localização, fonte). Todo o "cérebro V2"
(AVM, spatial/acessibilidade, regulatório, distress, vision) é computado, custa
Gemini, e não move `opportunities.score`. É um silo, confirmado por código
(`vision.py:8-19` tem a integração escrita como comentário nunca colado).

## Objetivo

Fazer os sinais V2 reordenarem o ranking, sem quebrar o funil atual nem os
thresholds existentes (`>=30` corte, `>=50` regulatory, `>=60` vision, `>=70`
notify/hit-rate).

## Decisão de design

Os sinais V2 entram como **multiplicador** sobre o score base, não como pontos
aditivos:

```
final = raw_base * source_confidence * v2_multiplier
v2_multiplier = clamp(1 + upside + antecipado - friccao, 0.90, 1.30)
```

Por que multiplicador e não pontos:
- **Degradação graciosa nativa:** sem dado V2, cada termo é 0 → multiplicador
  1.0 → score idêntico ao de hoje. As tabelas V2 estão vazias em produção até os
  coletores rodarem, então a mudança é inócua até haver dado.
- **Não mexe em thresholds:** a escala do score base não muda.
- **É o desenho já validado no artifact de arquitetura** (base × conf × (1+upside)
  × (1+antecip) × (1−fricção)).

## Escopo (fatiado)

**Fatia 1 (esta):** os dois eixos com dado de acesso trivial.
- `upside` (AVM): usa `avm_predictions.mispricing_pct` e `is_undervalued`.
  Subprecificado (p50 > pedido) empurra o score para cima, ponderado pela
  `confidence` do modelo. Cap +0.20.
- `antecipado` (spatial): usa `listings.mcmv_accessibility_score` (0-100).
  Boa acessibilidade MCMV dá bônus suave. Faixa [-0.05, +0.10].

**Fatia 2 (depois, precisa de aprovação):**
- `friccao` (regulatório): `regulatory_signals` (APP, litígio, zoneamento hostil)
  como penalidade. Exige mapear o schema e a política "nunca bloqueia".
- Renormalização da escala para 0-100 e revisão dos thresholds (corrige o bug
  de score > 100). Reverbera em notifier/regulatory/vision/feedback: fatia
  própria, revisada em conjunto.

## Critérios de aceite (fatia 1)

1. `_score_listing(listing, ctx)` sem terceiro argumento → score idêntico ao
   atual (testes existentes passam sem alteração).
2. Um listing subprecificado no AVM (`is_undervalued`, confidence alta) recebe
   score estritamente maior que o mesmo listing sem sinal AVM.
3. Acessibilidade alta aumenta o score; baixa reduz levemente; ausente é neutra.
4. `v2_multiplier` fica registrado em `score_breakdown` para o card explicável.
5. Nenhum threshold do funil é alterado nesta fatia.

## Não-objetivos

- Não fechar a RLS pública (decisão de auth pendente).
- Não renormalizar a escala nesta fatia.
- Não tocar distress/vision-satélite (rodam fora do cron de produção).
