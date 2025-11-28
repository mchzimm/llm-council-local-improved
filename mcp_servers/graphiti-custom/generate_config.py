#!/usr/bin/env python3
"""
Generate config.yaml and environment variables from graphiti_config.json.
This allows easy configuration of LLM, embedder, and database settings.
"""

import json
import yaml
import os
import sys

def load_json_config(path: str) -> dict:
    """Load the JSON configuration file."""
    with open(path, 'r') as f:
        return json.load(f)

def generate_yaml_config(config: dict) -> dict:
    """Generate the YAML configuration structure from JSON config."""
    yaml_config = {
        'server': {
            'transport': config.get('server', {}).get('transport', 'http'),
            'host': config.get('server', {}).get('host', '0.0.0.0'),
            'port': config.get('server', {}).get('port', 8000),
        },
        'llm': {
            'provider': config['llm']['provider'],
            'model': config['llm']['model'],
            'temperature': config['llm'].get('temperature', 0.0),
            'max_tokens': config['llm'].get('max_tokens', 16384),
            'providers': {
                'openai_generic': {
                    'api_key': config['llm'].get('api_key', 'lms'),
                    'api_url': config['llm'].get('base_url', 'http://localhost:1234/v1'),
                }
            }
        },
        'embedder': {
            'provider': config['embedder']['provider'],
            'model': config['embedder']['model'],
        },
        'database': {
            'provider': config['database']['provider'],
            'providers': {
                'falkordb': {
                    'uri': config['database'].get('uri', 'redis://localhost:6379'),
                    'password': config['database'].get('password', ''),
                    'database': config['database'].get('database', 'graphiti'),
                }
            }
        },
        'graphiti': {
            'group_id': config.get('graphiti', {}).get('group_id', 'main'),
        }
    }
    return yaml_config

def generate_env_vars(config: dict) -> dict:
    """Generate environment variables from JSON config."""
    return {
        'OPENAI_API_KEY': config['llm'].get('api_key', 'lms'),
        'OPENAI_BASE_URL': config['llm'].get('base_url', 'http://localhost:1234/v1'),
        'EMBEDDER_API_KEY': config['embedder'].get('api_key', 'lms'),
        'EMBEDDER_BASE_URL': config['embedder'].get('base_url', 'http://localhost:1234/v1'),
        'EMBEDDER_DIM': str(config['embedder'].get('embedding_dim', 768)),
    }

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(script_dir, 'graphiti_config.json')
    yaml_path = os.path.join(script_dir, 'config.yaml')
    
    if not os.path.exists(json_path):
        print(f"❌ Configuration file not found: {json_path}")
        sys.exit(1)
    
    # Load JSON config
    config = load_json_config(json_path)
    print(f"✅ Loaded configuration from {json_path}")
    
    # Generate and write YAML config
    yaml_config = generate_yaml_config(config)
    
    # Add header comment
    yaml_header = "# Graphiti Custom MCP Server\n# Auto-generated from graphiti_config.json\n# Do not edit directly - modify graphiti_config.json instead\n\n"
    
    with open(yaml_path, 'w') as f:
        f.write(yaml_header)
        yaml.dump(yaml_config, f, default_flow_style=False, sort_keys=False)
    
    print(f"✅ Generated {yaml_path}")
    
    # Generate environment variables for shell script
    env_vars = generate_env_vars(config)
    
    print("\n📋 Environment variables for docker run:")
    for key, value in env_vars.items():
        print(f"   -e {key}=\"{value}\"")
    
    # Output for shell script sourcing
    env_file = os.path.join(script_dir, '.env')
    with open(env_file, 'w') as f:
        for key, value in env_vars.items():
            f.write(f'{key}="{value}"\n')
    print(f"\n✅ Generated {env_file}")
    
    # Print summary
    print("\n📊 Configuration Summary:")
    print(f"   LLM Provider: {config['llm']['provider']}")
    print(f"   LLM Model: {config['llm']['model']}")
    print(f"   LLM Endpoint: {config['llm'].get('base_url')}")
    print(f"   Embedder Provider: {config['embedder']['provider']}")
    print(f"   Embedder Model: {config['embedder']['model']}")
    print(f"   Embedder Endpoint: {config['embedder'].get('base_url')}")
    print(f"   Database: {config['database']['provider']} @ {config['database'].get('uri')}")

if __name__ == '__main__':
    main()
