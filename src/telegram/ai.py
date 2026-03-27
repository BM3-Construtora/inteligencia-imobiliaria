"""AI-powered conversational responses using Gemini + Supabase context."""

from __future__ import annotations

import logging

from src.llm import _generate, GEMINI_API_KEY
from src.telegram.queries import get_market_context_for_ai

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Voce e o MariliaBot, um assistente de inteligencia imobiliaria especializado em Marilia-SP.
Voce ajuda uma construtora familiar (BM3) a decidir ONDE, O QUE e QUANDO construir.
Foco principal: MCMV (Minha Casa Minha Vida).

Regras:
- Responda em portugues informal e direto, como um consultor pragmatico
- Use os dados fornecidos para embasar suas respostas
- Quando nao souber, diga que nao tem dados suficientes
- Seja conciso (max 300 palavras)
- Nao use markdown pesado (o Telegram nao renderiza bem)
- Use emojis com moderacao
- Sempre que possivel, de uma recomendacao clara (comprar/nao comprar, construir/esperar)
"""


def answer_question(user_message: str) -> str:
    """Answer a free-text question using Gemini + market data context."""
    if not GEMINI_API_KEY:
        return "LLM nao configurado. Defina GEMINI_API_KEY no .env."

    try:
        context = get_market_context_for_ai()
    except Exception:
        logger.exception("[ai] Failed to fetch context")
        context = "Dados indisponiveis no momento."

    prompt = f"""{SYSTEM_PROMPT}

DADOS ATUAIS DO MERCADO:
{context}

PERGUNTA DO USUARIO:
{user_message}

Responda de forma direta e util:"""

    response = _generate(prompt, max_tokens=2000)

    if not response:
        return "Desculpe, nao consegui gerar uma resposta. Tente novamente."

    return response
