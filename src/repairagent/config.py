from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


class ConfigError(Exception):
    pass


PROVIDER_PRESETS: dict[str, dict[str, str | None]] = {
    "groq": {"base_url": "https://api.groq.com/openai/v1", "key_env": "GROQ_API_KEY"},
    "ollama": {"base_url": "http://localhost:11434/v1", "key_env": None},
    "openai": {"base_url": "https://api.openai.com/v1", "key_env": "OPENAI_API_KEY"},
}


def load_env_file(path: str | Path = ".env", environ: dict[str, str] | None = None) -> int:
    target = os.environ if environ is None else environ
    file = Path(path)
    if not file.is_file():
        return 0
    loaded = 0
    for raw in file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in target:
            target[key] = value
            loaded += 1
    return loaded


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    model: str
    base_url: str
    api_key: str | None
    temperature: float = 0.0
    max_tokens: int = 1024
    timeout_s: float = 60.0
    max_retries: int = 4

    @classmethod
    def from_env(
        cls,
        provider: str | None = None,
        model: str | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> LLMSettings:
        env = os.environ if environ is None else environ
        name = (provider or env.get("LLM_PROVIDER") or "groq").lower()
        if name not in PROVIDER_PRESETS:
            raise ConfigError(
                f"Unknown provider '{name}'. Choose one of: {', '.join(sorted(PROVIDER_PRESETS))}."
            )
        preset = PROVIDER_PRESETS[name]
        chosen_model = model or env.get("LLM_MODEL")
        if not chosen_model:
            raise ConfigError(
                "No model configured. Set LLM_MODEL or pass --model "
                "(for Groq check the current model ids at console.groq.com/docs/models)."
            )
        key_env = preset["key_env"]
        api_key = env.get("LLM_API_KEY") or (env.get(key_env) if key_env else None)
        if key_env and not api_key:
            raise ConfigError(f"No API key found. Set {key_env} (or LLM_API_KEY).")
        return cls(
            provider=name,
            model=chosen_model,
            base_url=env.get("LLM_BASE_URL") or str(preset["base_url"]),
            api_key=api_key,
            temperature=float(env.get("LLM_TEMPERATURE", "0")),
            max_tokens=int(env.get("LLM_MAX_TOKENS", "1024")),
            timeout_s=float(env.get("LLM_TIMEOUT_S", "60")),
            max_retries=int(env.get("LLM_MAX_RETRIES", "4")),
        )


@dataclass(frozen=True)
class Budget:
    max_steps: int = 20
    max_total_tokens: int = 150_000
    max_wall_s: float = 300.0
    max_test_runs: int = 8
    max_policy_violations: int = 3
    max_repeat_actions: int = 3
