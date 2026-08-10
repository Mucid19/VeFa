import requests
import logging
from typing import Any

logger = logging.getLogger(__name__)


class _OllamaPart:
    """Mimics Gemini response Part object."""
    def __init__(self, text: str):
        self.text = text
        # No function_call attribute - just text


class _OllamaContent:
    """Mimics Gemini response Content object."""
    def __init__(self, text: str):
        self.parts = [_OllamaPart(text)]


class _OllamaCandidate:
    """Mimics Gemini response Candidate object."""
    def __init__(self, text: str):
        self.content = _OllamaContent(text)
        self.finish_reason = "STOP"


class OllamaResponse:
    """
    Mimics the Gemini GenerateContentResponse interface so that
    agent_runner.py can use Ollama without any changes.
    """
    def __init__(self, text: str):
        self.text = text
        self.candidates = [_OllamaCandidate(text)]


class OllamaModelWrapper:
    """
    Compatibility wrapper for Ollama local API.
    Mimics the Gemini GenerativeModel interface used throughout the engine.
    """
    def __init__(
        self,
        model_name: str = "llama3",
        temperature: float = 0.7,
        host: str = "http://localhost:11434"
    ):
        self.model_name = model_name
        self.default_temperature = temperature
        self.host = host

    def generate_content(
        self,
        prompt: Any,
        generation_config: Any = None,
        safety_settings: Any = None,
    ) -> OllamaResponse:
        
        temp = self.default_temperature
        is_json = False
        
        if generation_config:
            if hasattr(generation_config, "temperature") and generation_config.temperature is not None:
                temp = generation_config.temperature
            elif isinstance(generation_config, dict) and "temperature" in generation_config:
                temp = generation_config["temperature"]
                
            if hasattr(generation_config, "response_mime_type") and generation_config.response_mime_type == "application/json":
                is_json = True
            elif isinstance(generation_config, dict) and generation_config.get("response_mime_type") == "application/json":
                is_json = True

        # Flatten prompt to string
        if isinstance(prompt, list):
            prompt_str = "\n".join(str(p) for p in prompt)
        else:
            prompt_str = str(prompt)

        # Separate system prompt (agent instructions) from user prompt (user request)
        system_prompt = None
        user_prompt = prompt_str

        delimiter = "\n\n---\n\nUser Request:\n"
        alt_delimiter = "\n\n---\n\n"

        if delimiter in prompt_str:
            parts = prompt_str.split(delimiter, 1)
            system_prompt = parts[0].strip()
            user_prompt = parts[1].strip()
        elif alt_delimiter in prompt_str:
            parts = prompt_str.split(alt_delimiter, 1)
            system_prompt = parts[0].strip()
            user_prompt = parts[1].strip()

        payload = {
            "model": self.model_name,
            "prompt": user_prompt,
            "stream": False,
            "options": {
                "temperature": temp
            }
        }
        
        if system_prompt:
            payload["system"] = system_prompt
        
        if is_json:
            payload["format"] = "json"

        try:
            response = requests.post(
                f"{self.host}/api/generate",
                json=payload,
                timeout=3000  # Long timeout for local LLM
            )
            response.raise_for_status()
            data = response.json()
            text = data.get("response", "")
            return OllamaResponse(text=text)
        except Exception as e:
            logger.error(f"Ollama API request failed: {e}")
            raise e
