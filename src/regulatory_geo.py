"""Hardcoded GeoJSON simplificado dos principais cursos d'água de Marília-SP.

Coordenadas aproximadas (centro de Marília ~ -22.21, -49.95). Usado para detectar
proximidade com APP (Área de Preservação Permanente — Lei 12.651/2012 art. 4).
A faixa marginal mínima para cursos < 10m de largura é 30m de cada lado.

TODO: substituir por shapefile real da Secretaria de Meio Ambiente quando disponível.
"""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from typing import Optional

# Lista de cursos d'água principais. polyline_coords é lista de (lat, lng).
WATER_COURSES: list[dict] = [
    {
        "nome": "Córrego do Cascata",
        "tipo": "corrego",
        "largura_estimada_m": 5,
        "app_buffer_m": 30,
        "polyline_coords": [
            (-22.1995, -49.9612),
            (-22.2042, -49.9587),
            (-22.2095, -49.9551),
            (-22.2148, -49.9510),
            (-22.2201, -49.9468),
            (-22.2254, -49.9421),
        ],
    },
    {
        "nome": "Ribeirão Lajeado",
        "tipo": "ribeirao",
        "largura_estimada_m": 12,
        "app_buffer_m": 50,
        "polyline_coords": [
            (-22.1850, -49.9320),
            (-22.1902, -49.9395),
            (-22.1968, -49.9462),
            (-22.2035, -49.9521),
            (-22.2110, -49.9580),
            (-22.2188, -49.9635),
        ],
    },
    {
        "nome": "Córrego do Barbosa",
        "tipo": "corrego",
        "largura_estimada_m": 4,
        "app_buffer_m": 30,
        "polyline_coords": [
            (-22.2305, -49.9710),
            (-22.2268, -49.9655),
            (-22.2231, -49.9602),
            (-22.2195, -49.9548),
            (-22.2158, -49.9495),
        ],
    },
]


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distância em metros entre dois pontos lat/lng."""
    r = 6371000.0
    p1, p2 = radians(lat1), radians(lat2)
    dp = radians(lat2 - lat1)
    dl = radians(lng2 - lng1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * r * asin(sqrt(a))


def _point_to_segment_m(
    lat: float, lng: float,
    a_lat: float, a_lng: float,
    b_lat: float, b_lng: float,
) -> float:
    """Distância em metros do ponto até o segmento [A,B] (aproximação plana)."""
    # Projeção equiretangular local — bom o suficiente para distâncias < 5km.
    # Converte tudo para metros relativos a um ponto de referência (A).
    cos_lat = cos(radians((a_lat + b_lat) / 2))
    ax, ay = 0.0, 0.0
    bx = (b_lng - a_lng) * 111320.0 * cos_lat
    by = (b_lat - a_lat) * 110540.0
    px = (lng - a_lng) * 111320.0 * cos_lat
    py = (lat - a_lat) * 110540.0

    dx, dy = bx - ax, by - ay
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq == 0:
        return sqrt(px * px + py * py)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_len_sq))
    proj_x = ax + t * dx
    proj_y = ay + t * dy
    return sqrt((px - proj_x) ** 2 + (py - proj_y) ** 2)


def nearest_water_course(
    lat: float, lng: float
) -> Optional[dict]:
    """Retorna o curso d'água mais próximo + distância em metros.

    Returns:
        {"nome": str, "tipo": str, "distance_m": float, "app_buffer_m": int,
         "within_app": bool} | None se sem dados.
    """
    if lat is None or lng is None:
        return None

    best: Optional[dict] = None
    for course in WATER_COURSES:
        coords = course["polyline_coords"]
        if len(coords) < 2:
            continue
        min_d = float("inf")
        for i in range(len(coords) - 1):
            a_lat, a_lng = coords[i]
            b_lat, b_lng = coords[i + 1]
            d = _point_to_segment_m(lat, lng, a_lat, a_lng, b_lat, b_lng)
            if d < min_d:
                min_d = d
        if best is None or min_d < best["distance_m"]:
            best = {
                "nome": course["nome"],
                "tipo": course["tipo"],
                "distance_m": round(min_d, 1),
                "app_buffer_m": course["app_buffer_m"],
                "within_app": min_d < course["app_buffer_m"],
            }
    return best
