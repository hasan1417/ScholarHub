#!/usr/bin/env python3
"""Apply ScholarHub defaults for OnlyOffice AI plugin settings."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List

CONFIG_PATH = Path("/etc/onlyoffice/documentserver/local.json")

DEFAULT_ALLOWED_ORIGINS = [
    "https://onlyoffice.github.io",
    "https://onlyoffice-plugins.github.io",
]

CAPABILITIES = {
    "chat": 0x01,
    "image": 0x02,
    "embeddings": 0x04,
    "audio": 0x08,
    "moderations": 0x10,
    "realtime": 0x20,
    "code": 0x40,
    "vision": 0x80,
}

ENDPOINTS = {
    "chat": 0x01,  # v1.Chat_Completions
    "completions": 0x02,
    "images": 0x11,  # v1.Images_Generations
}


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_config() -> Dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"OnlyOffice config not found at {CONFIG_PATH}")
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def dump_config(config: Dict) -> None:
    tmp_path = CONFIG_PATH.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    tmp_path.replace(CONFIG_PATH)


def ensure_ai_settings(config: Dict) -> Dict:
    ai_settings = config.get("aiSettings", {})

    # Keep existing non-AI defaults if present
    timeout = ai_settings.get("timeout", "30s")
    allowed = list(ai_settings.get("allowedCorsOrigins") or DEFAULT_ALLOWED_ORIGINS)
    plugin_dir = ai_settings.get("pluginDir", "../branding/info/ai")

    provider_name = os.getenv("ONLYOFFICE_AI_PROVIDER_NAME", "OpenAI")
    provider_url = os.getenv("ONLYOFFICE_AI_PROVIDER_URL", "https://api.openai.com")
    provider_addon = os.getenv("ONLYOFFICE_AI_PROVIDER_VERSION", "v1")
    api_key = os.getenv("OPENAI_API_KEY", "")

    chat_model = os.getenv("ONLYOFFICE_AI_CHAT_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o"))
    summary_model = os.getenv("ONLYOFFICE_AI_SUMMARY_MODEL", "gpt-4o-mini")
    translate_model = os.getenv("ONLYOFFICE_AI_TRANSLATE_MODEL", summary_model)
    analysis_model = os.getenv("ONLYOFFICE_AI_ANALYSIS_MODEL", chat_model)
    image_model = os.getenv("ONLYOFFICE_AI_IMAGE_MODEL", "dall-e-3")

    enable_vision_for_chat = _bool_env("ONLYOFFICE_AI_CHAT_ENABLE_VISION", True)

    # Build capabilities map
    model_capabilities: Dict[str, int] = {
        chat_model: CAPABILITIES["chat"] | (CAPABILITIES["vision"] if enable_vision_for_chat else 0),
        summary_model: CAPABILITIES["chat"],
        translate_model: CAPABILITIES["chat"],
        analysis_model: CAPABILITIES["chat"],
        image_model: CAPABILITIES["image"],
    }

    # Drop duplicates while preserving max capabilities
    condensed_capabilities: Dict[str, int] = {}
    for model_id, caps in model_capabilities.items():
        if not model_id:
            continue
        existing = condensed_capabilities.get(model_id, 0)
        condensed_capabilities[model_id] = existing | caps

    def model_display_name(model_id: str) -> str:
        return f"{provider_name} [{model_id}]"

    provider_models: List[Dict] = []
    models_payload: List[Dict] = []

    for model_id, caps in condensed_capabilities.items():
        if not model_id:
            continue
        endpoints: List[int] = []
        if caps & CAPABILITIES["chat"]:
            endpoints.append(ENDPOINTS["chat"])
        if caps & CAPABILITIES["image"]:
            endpoints.append(ENDPOINTS["images"])

        provider_models.append({
            "id": model_id,
            "object": "model",
            "owned_by": provider_name.lower().replace(" ", ""),
            "name": model_id,
            "endpoints": endpoints,
            "options": {},
        })

        models_payload.append({
            "id": model_id,
            "name": model_display_name(model_id),
            "provider": provider_name,
            "capabilities": caps,
        })

    providers_payload = {
        provider_name: {
            "name": provider_name,
            "url": provider_url,
            "addon": provider_addon,
            "key": api_key,
            "models": provider_models,
        }
    }

    actions_payload = {
        "Chat": {"model": chat_model},
        "Summarization": {"model": summary_model},
        "Translation": {"model": translate_model},
        "TextAnalyze": {"model": analysis_model},
        "ImageGeneration": {"model": image_model},
    }

    config["aiSettings"] = {
        "version": 3,
        "timeout": timeout,
        "allowedCorsOrigins": allowed,
        "pluginDir": plugin_dir,
        "providers": providers_payload,
        "models": models_payload,
        "actions": actions_payload,
    }
    return config


def main() -> None:
    try:
        config = load_config()
    except FileNotFoundError as exc:
        print(f"[update_ai_settings] {exc}")
        return

    updated = ensure_ai_settings(config)
    dump_config(updated)

    if not os.getenv("OPENAI_API_KEY"):
        print("[update_ai_settings] WARNING: OPENAI_API_KEY is not set; AI plugin requests will fail until it is provided.")
    else:
        print("[update_ai_settings] Applied OnlyOffice AI defaults for provider", os.getenv("ONLYOFFICE_AI_PROVIDER_NAME", "OpenAI"))


if __name__ == "__main__":
    main()
