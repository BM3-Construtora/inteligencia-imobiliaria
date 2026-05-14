"""Lista canônica de bairros de Marília-SP e validação de nomes extraídos.

Fonte: tabela `neighborhoods` do Supabase (curada manualmente, 2026-05).
Uso principal: validar nomes extraídos por regex de obras, parcelamentos,
habite-se antes de persistir — rejeitar falsos-positivos (nomes de escola,
logradouros, nomes de pessoa, etc.).
"""

from __future__ import annotations

import unicodedata

# ---------------------------------------------------------------------------
# Lista canônica (nome exibição → mantido com acentos para saída limpa)
# ---------------------------------------------------------------------------

_CANONICAL: list[str] = [
    "Aeroporto",
    "Altaneira",
    "Alto Cafezal",
    "Alto dos Palmital",
    "Altos da Colina",
    "Altos do Palmital",
    "Ana Carla",
    "Antenor Barion",
    "Armando Mascaro",
    "Avencas",
    "Banzato",
    "Barbosa",
    "Bassan",
    "Betel",
    "Boa Vista",
    "Bosque",
    "Califórnia",
    "Canaã",
    "Cascata",
    "Cavalieri",
    "Cavalieri II",
    "Cavallari",
    "Cavallieri",
    "Centro",
    "Cerqueira César",
    "Coimbra",
    "Colibri",
    "Continental",
    "Cora",
    "Estância dos Ipês",
    "Figueirinha",
    "Firenze",
    "Fragata",
    "Higienópolis",
    "Hípica Paulista",
    "Jardim J.K.",
    "Jânio Quadros",
    "Jequitibá",
    "Jóquei Clube",
    "Laranjal",
    "Lácio",
    "Lorenzetti",
    "Maracá",
    "Maracá II",
    "Marajó",
    "Maria Paula",
    "Mariana",
    "Mirante",
    "Montana",
    "Montolar",
    "Nova Marília",
    "Novo Mundo",
    "Osvaldo Fanceli",
    "Padre Nóbrega",
    "Palmital",
    "Paulista",
    "Pedro Matheus",
    "Pólon",
    "Quarto Centenário",
    "Rezende",
    "Rosália",
    "Salgado Filho",
    "Saliola",
    "San Francisco",
    "Santa Antonieta",
    "Santa Olivia",
    "Santa Paula",
    "Santa Tereza",
    "São João",
    "São José",
    "São Miguel",
    "Savi",
    "Somenzari",
    "Tancredo Neves",
    "Terra Verde",
    "Teruel",
    "Thomaz Mascaro",
    "Vera Cruz",
    # Jardins
    "Jardim Acapulco",
    "Jardim Adolpho Bim",
    "Jardim Aeroporto",
    "Jardim Alvorada",
    "Jardim América",
    "Jardim América IV",
    "Jardim Aquárius",
    "Jardim Araxá",
    "Jardim Bancários",
    "Jardim Bandeirantes",
    "Jardim Betânia",
    "Jardim Botânico",
    "Jardim Califórnia",
    "Jardim Cavalari",
    "Jardim Cavallari",
    "Jardim Colibri",
    "Jardim Continental",
    "Jardim Cristo Rei",
    "Jardim Damasco I",
    "Jardim Damasco II",
    "Jardim Damasco III",
    "Jardim Dirceu",
    "Jardim dos Lírios",
    "Jardim Eldorado",
    "Jardim Esmeralda",
    "Jardim Espanha",
    "Jardim Esplanada",
    "Jardim Estoril",
    "Jardim Flamingo",
    "Jardim Florença",
    "Jardim Fontanelli",
    "Jardim Guarujá",
    "Jardim Ipanema",
    "Jardim Itaipu",
    "Jardim Itamarati",
    "Jardim Jequitibá",
    "Jardim Lavínia",
    "Jardim Luciana",
    "Jardim Lucimar",
    "Jardim Maracá",
    "Jardim Marajá",
    "Jardim Marambaia",
    "Jardim Marília",
    "Jardim Marina",
    "Jardim Mirante",
    "Jardim Morumbi",
    "Jardim Nacional",
    "Jardim Natal",
    "Jardim Nazareth",
    "Jardim Ohara",
    "Jardim Paraíso",
    "Jardim Parati",
    "Jardim Paulista",
    "Jardim Pérola",
    "Jardim Planalto",
    "Jardim Polyana",
    "Jardim Progresso",
    "Jardim Renata",
    "Jardim Riviera",
    "Jardim Santa Antonieta",
    "Jardim Santa Clara",
    "Jardim Santa Paula",
    "Jardim Sasazaki",
    "Jardim São Domingos",
    "Jardim São Francisco",
    "Jardim Tangará",
    "Jardim Tropical",
    "Jardim Universitário",
    "Jardim Veneza",
    "Jardim Verona",
    "Jardim Virgínia",
    "Jardim Vitória",
    # Parques
    "Parque Alvorada",
    "Parque das Acácias",
    "Parque das Azaléias",
    "Parque das Esmeraldas",
    "Parque das Flores",
    "Parque das Indústrias",
    "Parque das Nações",
    "Parque das Primaveras",
    "Parque das Vivendas",
    "Parque das Árvores",
    "Parque dos Ipês",
    "Parque dos Sabiás II",
    "Parque Serra Dourada",
    "Parque São Jorge",
    # Vilas
    "Vila Amaral",
    "Vila Bela",
    "Vila Coimbra",
    "Vila Maria",
    "Vila Real",
    "Vila Romana",
    "Villa D'Itália",
    "Villa Flora",
    # Residenciais (seleção)
    "Residencial Araucária",
    "Residencial Lavínia",
    "Residencial Mangueiras",
    "Residencial Vida Nova Maracá",
    "Residencial Vida Nova Maracá II",
]

# ---------------------------------------------------------------------------
# Índices de lookup
# ---------------------------------------------------------------------------

_PREFIXES = (
    "jardim ", "jd ", "jd. ", "parque ", "vila ", "residencial ",
    "conjunto habitacional ", "conjunto residencial ",
    "sitios de recreio ", "sítios de recreio ",
    "bairro ",
)


def _normalize(s: str) -> str:
    """Remove acentos e passa para lowercase."""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.lower().strip()


def _core(normalized: str) -> str:
    """Remove prefixo de tipo de bairro para matching fuzzy."""
    for pfx in _PREFIXES:
        if normalized.startswith(pfx):
            return normalized[len(pfx):]
    return normalized


# Aliases explícitos: formas abreviadas ou com typo → nome canônico
_ALIASES: dict[str, str] = {
    "j.k.": "Jardim J.K.",
    "jk": "Jardim J.K.",
    "jardim jk": "Jardim J.K.",
    "america iv": "Jardim América IV",
    "jardim america iv": "Jardim América IV",
    "cavalari": "Jardim Cavallari",
    "jardim cavalari": "Jardim Cavallari",
    "santa antonieta 3": "Jardim Santa Antonieta",
    "santa antonieta iii": "Jardim Santa Antonieta",
    "jardim santa antonieta 3": "Jardim Santa Antonieta",
    "jardim santa antonieta iii": "Jardim Santa Antonieta",
}

# norm → canonical display name
_NORM_TO_CANONICAL: dict[str, str] = {}
# core → canonical display name (para "Cavallari" → "Jardim Cavallari")
_CORE_TO_CANONICAL: dict[str, str] = {}

for _name in _CANONICAL:
    _n = _normalize(_name)
    _NORM_TO_CANONICAL[_n] = _name
    _c = _core(_n)
    if _c not in _CORE_TO_CANONICAL:
        _CORE_TO_CANONICAL[_c] = _name

# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def validate_neighborhood(name: str | None) -> str | None:
    """Valida e normaliza um nome de bairro extraído.

    Retorna o nome canônico (com acentos) se válido, ou None se não reconhecido.

    Exemplos:
        "Jardim Cavallari" → "Jardim Cavallari"
        "Cavallari"        → "Jardim Cavallari"  (match por core)
        "Colibri"          → "Jardim Colibri"
        "Clara Luz"        → None  (nome de escola)
        "Geralda César"    → None  (nome de pessoa)
        "Palmital"         → "Palmital"
    """
    if not name:
        return None
    n = _normalize(name)
    # 0. alias explícito
    if n in _ALIASES:
        return _ALIASES[n]
    # 1. match exato
    if n in _NORM_TO_CANONICAL:
        return _NORM_TO_CANONICAL[n]
    # 2. match por core (remove prefixo)
    c = _core(n)
    if c and c in _CORE_TO_CANONICAL:
        return _CORE_TO_CANONICAL[c]
    return None


def is_known_neighborhood(name: str | None) -> bool:
    return validate_neighborhood(name) is not None
