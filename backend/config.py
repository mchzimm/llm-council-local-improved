"""Configuration for the LLM Council."""

import os
from dotenv import load_dotenv
from .config_loader import get_council_models, get_chairman_model, get_formatter_model, load_config

load_dotenv()

# Load configuration
config = load_config()

# LM Studio API configuration (will be set dynamically after validation)
LM_STUDIO_BASE_URL = None  # Will be set by model validator
LM_STUDIO_API_ENDPOINT = None  # Will be set by model validator

# Dynamic model loading from config.json
COUNCIL_MODELS = get_council_models()
CHAIRMAN_MODEL = get_chairman_model()
FORMATTER_MODEL = get_formatter_model()

# Data directory for conversation storage
DATA_DIR = "data/conversations"

def set_api_endpoints(base_url: str):
    """Set API endpoints after validation"""
    global LM_STUDIO_BASE_URL, LM_STUDIO_API_ENDPOINT
    LM_STUDIO_BASE_URL = base_url
    LM_STUDIO_API_ENDPOINT = f"{base_url}/chat/completions"
