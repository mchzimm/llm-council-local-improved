"""Dynamic configuration loader for LLM Council."""

import json
import os
from typing import List, Dict, Any, Tuple
from pathlib import Path

# Default fallback configuration
DEFAULT_COUNCIL_MODELS = [
    "microsoft/phi-4-mini-reasoning",
    "apollo-v0.1-4b-thinking-qx86x-hi-mlx",
    "ai21-jamba-reasoning-3b-hi-mlx",
]
DEFAULT_CHAIRMAN_MODEL = "qwen/qwen3-4b-thinking-2507"
DEFAULT_DELIBERATION_ROUNDS = 1

def get_project_root() -> Path:
    """Get the project root directory."""
    current_file = Path(__file__)
    # Go up from backend/config_loader.py to project root
    return current_file.parent.parent

def load_config() -> Dict[str, Any]:
    """
    Load configuration from config.json, with fallback to models.json.
    
    Returns:
        Dict containing full configuration, or defaults if loading fails
    """
    project_root = get_project_root()
    config_path = project_root / "config.json"
    models_path = project_root / "models.json"  # Backward compatibility
    
    # Try config.json first
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # Validate and normalize configuration
            normalized = normalize_config(config)
            if normalized:
                print(f"Loaded configuration from {config_path}")
                return normalized
            else:
                print(f"Warning: Invalid configuration in {config_path}, using defaults")
                return get_default_config()
        
        except json.JSONDecodeError as e:
            print(f"Warning: Invalid JSON in {config_path}: {e}")
        except Exception as e:
            print(f"Warning: Error loading {config_path}: {e}")
    
    # Fallback to models.json for backward compatibility
    elif models_path.exists():
        try:
            with open(models_path, 'r', encoding='utf-8') as f:
                old_config = json.load(f)
            
            # Convert old models.json format to new config.json format
            if validate_old_config(old_config):
                converted = convert_old_config(old_config)
                print(f"Loaded legacy configuration from {models_path}")
                print("Consider migrating to config.json format")
                return converted
            else:
                print(f"Warning: Invalid legacy configuration in {models_path}")
        
        except json.JSONDecodeError as e:
            print(f"Warning: Invalid JSON in {models_path}: {e}")
        except Exception as e:
            print(f"Warning: Error loading {models_path}: {e}")
    
    # Final fallback to defaults
    print(f"Warning: No configuration file found, using defaults")
    return get_default_config()

def normalize_config(config: Dict[str, Any]) -> Dict[str, Any] | None:
    """
    Normalize and validate configuration structure.
    
    Args:
        config: Raw configuration dictionary
    
    Returns:
        Normalized configuration or None if invalid
    """
    if not isinstance(config, dict):
        return None
    
    # Handle both new format (models: {...}) and mixed format
    if "models" in config:
        # New format - validate structure
        if not validate_new_config(config):
            return None
        return config
    
    elif "council" in config and "chairman" in config:
        # Old format found in config.json - convert it
        if validate_old_config(config):
            return convert_old_config(config)
        return None
    
    return None

def validate_new_config(config: Dict[str, Any]) -> bool:
    """Validate new config.json format."""
    if "models" not in config:
        return False
    
    models = config["models"]
    if not isinstance(models, dict):
        return False
    
    # Validate models section using old validation logic
    return validate_old_config(models)

def validate_old_config(config: Dict[str, Any]) -> bool:
    """Validate models.json format (backward compatibility)."""
    if not isinstance(config, dict):
        return False
    
    if "council" not in config or "chairman" not in config:
        return False
    
    # Validate council models
    council = config["council"]
    if not isinstance(council, list) or len(council) == 0:
        return False
    
    for model in council:
        if not isinstance(model, dict) or "id" not in model or "name" not in model:
            return False
        if not isinstance(model["id"], str) or not isinstance(model["name"], str):
            return False
    
    # Validate chairman model
    chairman = config["chairman"]
    if not isinstance(chairman, dict):
        return False
    if "id" not in chairman or "name" not in chairman:
        return False
    if not isinstance(chairman["id"], str) or not isinstance(chairman["name"], str):
        return False
    
    return True

def convert_old_config(old_config: Dict[str, Any]) -> Dict[str, Any]:
    """Convert models.json format to new config.json format."""
    return {
        "models": {
            "council": old_config["council"],
            "chairman": old_config["chairman"]
        },
        "deliberation": {
            "rounds": 1,  # Default to single round for backward compatibility
            "max_rounds": 5,
            "enable_cross_review": True,
            "refinement_prompt_template": "default"
        },
        "metadata": old_config.get("metadata", {
            "version": "1.0-converted",
            "source": "converted_from_models_json"
        })
    }

def get_default_config() -> Dict[str, Any]:
    """Get default fallback configuration."""
    return {
        "models": {
            "council": [
                {"id": model, "name": model.split("/")[-1]} 
                for model in DEFAULT_COUNCIL_MODELS
            ],
            "chairman": {
                "id": DEFAULT_CHAIRMAN_MODEL,
                "name": DEFAULT_CHAIRMAN_MODEL.split("/")[-1]
            }
        },
        "deliberation": {
            "rounds": DEFAULT_DELIBERATION_ROUNDS,
            "max_rounds": 5,
            "enable_cross_review": True,
            "refinement_prompt_template": "default"
        },
        "metadata": {
            "version": "fallback",
            "source": "hardcoded_defaults"
        }
    }

def get_council_models() -> List[str]:
    """Get list of council model IDs."""
    config = load_config()
    return [model["id"] for model in config["models"]["council"]]

def get_chairman_model() -> str:
    """Get chairman model ID."""
    config = load_config()
    return config["models"]["chairman"]["id"]

def get_formatter_model() -> str:
    """Get formatter model ID. Returns chairman model if formatter is not configured."""
    config = load_config()
    formatter = config["models"].get("formatter", {})
    formatter_id = formatter.get("id", "").strip()
    if formatter_id:
        return formatter_id
    # Fall back to chairman model
    return config["models"]["chairman"]["id"]

def get_deliberation_config() -> Dict[str, Any]:
    """Get deliberation configuration."""
    config = load_config()
    return config.get("deliberation", {
        "rounds": DEFAULT_DELIBERATION_ROUNDS,
        "max_rounds": 5,
        "enable_cross_review": True,
        "refinement_prompt_template": "default"
    })

def get_deliberation_rounds() -> int:
    """Get number of deliberation rounds."""
    deliberation = get_deliberation_config()
    return deliberation.get("rounds", DEFAULT_DELIBERATION_ROUNDS)

def get_title_generation_config() -> Dict[str, Any]:
    """Get title generation configuration."""
    config = load_config()
    return config.get("title_generation", {
        "enabled": True,
        "max_concurrent": 2,
        "timeout_seconds": 60,
        "retry_attempts": 3,
        "thinking_models": ["thinking", "reasoning", "o1"],
        "auto_expand_thinking": True
    })

def resolve_model_connection_params(model: Dict[str, Any], server_config: Dict[str, Any]) -> Dict[str, str]:
    """
    Resolve connection parameters for a specific model.
    
    Args:
        model: Model configuration dict
        server_config: Server configuration dict with defaults
    
    Returns:
        Dict with resolved connection parameters
    """
    # Parameter resolution order: model-specific -> server default -> system default
    
    # Get model-specific parameters (empty strings are considered "not set")
    model_ip = model.get("ip", "").strip()
    model_port = model.get("port", "").strip()
    model_base_url = model.get("base_url_template", "").strip()
    model_api_key = model.get("api_key", "").strip()
    
    # Get server defaults
    server_ip = server_config.get("ip", "").strip()
    server_port = server_config.get("port", "11434").strip()
    server_base_url = server_config.get("base_url_template", "http://{ip}:{port}/v1").strip()
    server_api_key = server_config.get("api_key", "").strip()
    
    # Resolve each parameter
    resolved_ip = model_ip or server_ip or "127.0.0.1"
    resolved_port = model_port or server_port or "11434"
    resolved_api_key = model_api_key or server_api_key
    
    # Handle base URL template
    if model_base_url:
        resolved_base_url = model_base_url
    elif server_base_url:
        resolved_base_url = server_base_url
    else:
        resolved_base_url = "http://{ip}:{port}/v1"
    
    # Format the base URL with resolved IP and port
    formatted_base_url = resolved_base_url.format(ip=resolved_ip, port=resolved_port)
    
    return {
        "ip": resolved_ip,
        "port": resolved_port,
        "base_url": formatted_base_url,
        "api_key": resolved_api_key,
        "api_endpoint": f"{formatted_base_url}/chat/completions"
    }

def get_model_connection_info(model_id: str) -> Dict[str, str]:
    """Get connection information for a specific model."""
    config = load_config()
    server_config = config.get("server", {})
    
    # Find model in configuration
    models = config["models"]
    
    # Check council models
    for model in models["council"]:
        if model["id"] == model_id:
            return resolve_model_connection_params(model, server_config)
    
    # Check chairman model
    if models["chairman"]["id"] == model_id:
        return resolve_model_connection_params(models["chairman"], server_config)
    
    # Check formatter model
    formatter = models.get("formatter", {})
    if formatter.get("id") == model_id:
        return resolve_model_connection_params(formatter, server_config)
    
    # Fallback to server defaults if model not found
    return resolve_model_connection_params({}, server_config)


def get_response_config() -> Dict[str, Any]:
    """Get response configuration for brevity and max_tokens settings."""
    config = load_config()
    return config.get("response_config", {
        "response_style": "standard",
        "max_tokens": {
            "stage1": None,
            "stage2": None,
            "stage3": None
        }
    })


def get_model_info(model_id: str) -> Dict[str, Any]:
    """Get detailed information about a specific model."""
    config = load_config()
    models = config["models"]
    
    # Check council models
    for model in models["council"]:
        if model["id"] == model_id:
            return model
    
    # Check chairman model
    if models["chairman"]["id"] == model_id:
        return models["chairman"]
    
    return {}

def list_all_models() -> Dict[str, List[Dict[str, str]]]:
    """Get all configured models organized by role."""
    config = load_config()
    models = config["models"]
    return {
        "council": models["council"],
        "chairman": [models["chairman"]]  # Wrap in list for consistency
    }