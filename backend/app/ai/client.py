import json
import logging
from typing import Any, Optional
import httpx
from app.config import settings

logger = logging.getLogger("ai_client")


class AIClient:
    """
    Unified Multi-Provider AI Client for SmartDev IoT.
    Supports:
    1. Ollama (Llama 3.2, Llama 3, Mistral) - 100% Free, Local & Private
    2. Groq (Llama-3.3-70b-versatile, Llama-3.1-8b-instant) - Ultra-fast Free Cloud API
    3. SmartDev Built-in Cognitive Engine - Offline Fallback (No Key / No Internet required)
    """

    def __init__(self):
        self._cached_ollama_available: Optional[bool] = None

    async def check_ollama(self) -> bool:
        """Check if local Ollama daemon is active."""
        try:
            async with httpx.AsyncClient(timeout=1.5) as client:
                res = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
                if res.status_code == 200:
                    self._cached_ollama_available = True
                    return True
        except Exception:
            pass
        self._cached_ollama_available = False
        return False

    async def get_available_providers(self) -> dict[str, Any]:
        ollama_active = await self.check_ollama()
        groq_active = bool(settings.GROQ_API_KEY)
        return {
            "preferred_provider": settings.AI_PROVIDER,
            "ollama": {
                "available": ollama_active,
                "url": settings.OLLAMA_BASE_URL,
                "model": settings.OLLAMA_MODEL,
                "free": True,
                "local": True,
            },
            "groq": {
                "available": groq_active,
                "model": settings.GROQ_MODEL,
                "free_tier": True,
                "cloud": True,
            },
            "builtin_engine": {
                "available": True,
                "name": "SmartDev Cognitive Heuristics AI",
                "free": True,
                "offline": True,
            },
        }

    async def generate_response(
        self,
        messages: list[dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        force_provider: Optional[str] = None,
    ) -> tuple[str, str]:
        """
        Generates a completion using the best available AI provider.
        Returns: (response_text, provider_model_name)
        """
        provider = force_provider or settings.AI_PROVIDER.lower()

        # 1. Try Groq if explicitly requested or auto with valid key
        if (provider in ("groq", "auto")) and settings.GROQ_API_KEY:
            try:
                res, model = await self._call_groq(messages, system_prompt, temperature)
                if res:
                    return res, f"Groq/{model}"
            except Exception as e:
                logger.warning("Groq API call failed, falling back: %s", e)

        # 2. Try Ollama (Local Llama) if explicitly requested or auto
        if provider in ("ollama", "auto"):
            ollama_ok = await self.check_ollama()
            if ollama_ok:
                try:
                    res, model = await self._call_ollama(messages, system_prompt, temperature)
                    if res:
                        return res, f"Ollama/{model}"
                except Exception as e:
                    logger.warning("Ollama call failed, falling back: %s", e)

        # 3. Built-in Cognitive Fallback Engine
        return "", "builtin"

    async def _call_ollama(
        self,
        messages: list[dict[str, str]],
        system_prompt: Optional[str],
        temperature: float,
    ) -> tuple[str, str]:
        formatted_messages = []
        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})
        formatted_messages.extend(messages)

        payload = {
            "model": settings.OLLAMA_MODEL,
            "messages": formatted_messages,
            "stream": False,
            "options": {"temperature": temperature},
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(f"{settings.OLLAMA_BASE_URL}/api/chat", json=payload)
            if res.status_code == 200:
                data = res.json()
                content = data.get("message", {}).get("content", "")
                return content.strip(), settings.OLLAMA_MODEL
            raise RuntimeError(f"Ollama returned HTTP {res.status_code}: {res.text}")

    async def _call_groq(
        self,
        messages: list[dict[str, str]],
        system_prompt: Optional[str],
        temperature: float,
    ) -> tuple[str, str]:
        formatted_messages = []
        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})
        formatted_messages.extend(messages)

        headers = {
            "Authorization": f"Bearer {settings.GROQ_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": settings.GROQ_MODEL,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": 1024,
        }

        async with httpx.AsyncClient(timeout=12.0) as client:
            res = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            if res.status_code == 200:
                data = res.json()
                content = data["choices"][0]["message"]["content"]
                return content.strip(), settings.GROQ_MODEL
            raise RuntimeError(f"Groq returned HTTP {res.status_code}: {res.text}")


ai_client = AIClient()
