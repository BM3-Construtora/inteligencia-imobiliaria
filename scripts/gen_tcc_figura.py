# -*- coding: utf-8 -*-
"""Gera a Figura 1 do TCC: diagrama do pipeline metodológico do MaríliaBot."""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

os.makedirs("docs/img", exist_ok=True)
OUT = "docs/img/pipeline.png"

STAGES = [
    ("1. Coleta de dados públicos",
     "portais (on-market) · off-market (alvará, EIV, IPTU,\n"
     "inventário, leilão) · ITBI · IBGE · SINAPI · OpenStreetMap"),
    ("2. Normalização, deduplicação e geocodificação",
     "padronização · fingerprint cross-portal · 5 centroides econômicos"),
    ("3. Avaliação automatizada (AVM)",
     "LightGBM por quantis (P10–P90) · ITBI como ground truth\n"
     "+ explicabilidade SHAP"),
    ("4. Simulação de viabilidade",
     "VGV · TIR (método de Newton) · payback · faixas MCMV"),
    ("5. Scoring de oportunidades",
     "ranking multicritério de terrenos"),
    ("6. Entrega da decisão",
     "dashboard interativo · bot de Telegram (GO / NO-GO explicável)"),
]

fig, ax = plt.subplots(figsize=(6.5, 9.2))
ax.set_xlim(0, 10)
ax.set_ylim(0, len(STAGES) * 2)
ax.axis("off")

box_w, box_h = 8.6, 1.35
x = 5.0
colors = ["#E8F0FE", "#E6F4EA", "#FEF7E0", "#FCE8E6", "#F3E8FD", "#E0F7FA"]

centers = []
for i, (titulo, sub) in enumerate(STAGES):
    y = len(STAGES) * 2 - 1.4 - i * 2
    centers.append(y)
    box = FancyBboxPatch(
        (x - box_w / 2, y - box_h / 2), box_w, box_h,
        boxstyle="round,pad=0.02,rounding_size=0.12",
        linewidth=1.1, edgecolor="#444", facecolor=colors[i % len(colors)],
    )
    ax.add_patch(box)
    ax.text(x, y + 0.28, titulo, ha="center", va="center",
            fontsize=10.5, fontweight="bold", color="#1a1a1a")
    ax.text(x, y - 0.30, sub, ha="center", va="center",
            fontsize=7.6, color="#333")

for i in range(len(centers) - 1):
    arr = FancyArrowPatch(
        (x, centers[i] - box_h / 2), (x, centers[i + 1] + box_h / 2),
        arrowstyle="-|>", mutation_scale=16, linewidth=1.4, color="#555",
    )
    ax.add_patch(arr)

plt.tight_layout()
plt.savefig(OUT, dpi=160, bbox_inches="tight")
print("OK ->", OUT)
