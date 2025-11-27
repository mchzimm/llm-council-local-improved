"""Model quality metrics tracking and evaluation."""

import json
import os
import time
import random
from typing import Dict, Any, List, Optional
from pathlib import Path

# Store metrics in the data directory alongside conversations
DATA_DIR = Path(__file__).parent.parent / "data"
METRICS_FILE = DATA_DIR / "llm_metrics.json"
METRICS_MD_FILE = DATA_DIR / "llm_metrics.md"

# Ensure data directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Default metric structure for a model
DEFAULT_MODEL_METRICS = {
    "total_queries": 0,
    "successful_queries": 0,
    "failed_queries": 0,
    "retries": 0,
    "total_tokens_generated": 0,
    "total_generation_time_ms": 0,
    "evaluations": {
        "verbosity": [],       # 1-5 scale
        "expertise": [],       # 1-5 scale
        "adherence": [],       # 1-5 scale
        "clarity": [],         # 1-5 scale
        "overall": []          # 1-5 scale
    },
    "average_scores": {
        "verbosity": 0,
        "expertise": 0,
        "adherence": 0,
        "clarity": 0,
        "overall": 0
    },
    "composite_rating": 0,
    "rank": 0
}


def load_metrics() -> Dict[str, Any]:
    """Load metrics from file."""
    if os.path.exists(METRICS_FILE):
        try:
            with open(METRICS_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {"models": {}, "last_updated": None}
    return {"models": {}, "last_updated": None}


def save_metrics(metrics: Dict[str, Any]):
    """Save metrics to JSON file and update markdown version."""
    metrics["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(METRICS_FILE, 'w') as f:
        json.dump(metrics, f, indent=2)
    
    # Also save markdown version
    _save_metrics_markdown(metrics)


def get_model_metrics(model_id: str) -> Dict[str, Any]:
    """Get metrics for a specific model."""
    metrics = load_metrics()
    if model_id not in metrics["models"]:
        metrics["models"][model_id] = DEFAULT_MODEL_METRICS.copy()
        metrics["models"][model_id]["evaluations"] = {k: [] for k in DEFAULT_MODEL_METRICS["evaluations"]}
        metrics["models"][model_id]["average_scores"] = {k: 0 for k in DEFAULT_MODEL_METRICS["average_scores"]}
        save_metrics(metrics)
    return metrics["models"][model_id]


def record_query_result(
    model_id: str,
    success: bool,
    tokens_generated: int = 0,
    generation_time_ms: float = 0,
    retried: bool = False
):
    """Record the result of a query to a model."""
    metrics = load_metrics()
    
    if model_id not in metrics["models"]:
        metrics["models"][model_id] = DEFAULT_MODEL_METRICS.copy()
        metrics["models"][model_id]["evaluations"] = {k: [] for k in DEFAULT_MODEL_METRICS["evaluations"]}
        metrics["models"][model_id]["average_scores"] = {k: 0 for k in DEFAULT_MODEL_METRICS["average_scores"]}
    
    model = metrics["models"][model_id]
    model["total_queries"] += 1
    
    if success:
        model["successful_queries"] += 1
        model["total_tokens_generated"] += tokens_generated
        model["total_generation_time_ms"] += generation_time_ms
    else:
        model["failed_queries"] += 1
    
    if retried:
        model["retries"] += 1
    
    save_metrics(metrics)


def record_evaluation(
    model_id: str,
    verbosity: int,
    expertise: int,
    adherence: int,
    clarity: int,
    overall: int
):
    """Record an evaluation for a model's response."""
    metrics = load_metrics()
    
    if model_id not in metrics["models"]:
        metrics["models"][model_id] = DEFAULT_MODEL_METRICS.copy()
        metrics["models"][model_id]["evaluations"] = {k: [] for k in DEFAULT_MODEL_METRICS["evaluations"]}
        metrics["models"][model_id]["average_scores"] = {k: 0 for k in DEFAULT_MODEL_METRICS["average_scores"]}
    
    model = metrics["models"][model_id]
    
    # Keep last 100 evaluations per category
    max_history = 100
    
    model["evaluations"]["verbosity"].append(verbosity)
    model["evaluations"]["expertise"].append(expertise)
    model["evaluations"]["adherence"].append(adherence)
    model["evaluations"]["clarity"].append(clarity)
    model["evaluations"]["overall"].append(overall)
    
    # Trim to max history
    for key in model["evaluations"]:
        if len(model["evaluations"][key]) > max_history:
            model["evaluations"][key] = model["evaluations"][key][-max_history:]
    
    # Recalculate averages
    for key in model["evaluations"]:
        scores = model["evaluations"][key]
        model["average_scores"][key] = sum(scores) / len(scores) if scores else 0
    
    # Calculate composite rating (weighted average)
    weights = {
        "verbosity": 0.1,
        "expertise": 0.3,
        "adherence": 0.3,
        "clarity": 0.15,
        "overall": 0.15
    }
    model["composite_rating"] = sum(
        model["average_scores"][k] * weights[k] 
        for k in weights
    )
    
    # Update rankings
    _update_rankings(metrics)
    save_metrics(metrics)


def _update_rankings(metrics: Dict[str, Any]):
    """Update model rankings based on composite rating."""
    models = [(mid, m["composite_rating"]) for mid, m in metrics["models"].items()]
    models.sort(key=lambda x: x[1], reverse=True)
    
    for rank, (model_id, _) in enumerate(models, 1):
        metrics["models"][model_id]["rank"] = rank


def get_valid_models() -> List[str]:
    """Get list of valid models (council members + chairman)."""
    from .config import COUNCIL_MODELS, CHAIRMAN_MODEL
    valid = set(COUNCIL_MODELS)
    if CHAIRMAN_MODEL:
        valid.add(CHAIRMAN_MODEL)
    return list(valid)


def cleanup_invalid_models():
    """Remove entries for models that are not valid council members or chairman."""
    valid_models = set(get_valid_models())
    metrics = load_metrics()
    
    invalid = [mid for mid in metrics["models"].keys() if mid not in valid_models]
    
    if invalid:
        for model_id in invalid:
            del metrics["models"][model_id]
            print(f"[Metrics] Removed invalid model: {model_id}")
        
        _update_rankings(metrics)
        save_metrics(metrics)
        print(f"[Metrics] Cleaned up {len(invalid)} invalid model(s)")
    
    return invalid


def get_highest_rated_model(exclude_models: Optional[List[str]] = None, valid_only: bool = True) -> Optional[str]:
    """Get the model with highest rating, excluding specified models."""
    metrics = load_metrics()
    exclude = set(exclude_models or [])
    
    # Only consider valid models if requested
    valid_models = set(get_valid_models()) if valid_only else None
    
    candidates = [
        (mid, m["composite_rating"]) 
        for mid, m in metrics["models"].items()
        if mid not in exclude 
        and m["composite_rating"] > 0
        and (valid_models is None or mid in valid_models)
    ]
    
    if not candidates:
        return None
    
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0][0]


def get_evaluator_for_model(target_model: str) -> Optional[str]:
    """
    Get the best evaluator model for a target model.
    Never returns the target model itself.
    If target is highest rated, returns second highest.
    """
    valid_models = get_valid_models()
    
    # Get highest rated that isn't the target
    evaluator = get_highest_rated_model(exclude_models=[target_model], valid_only=True)
    
    if evaluator:
        return evaluator
    
    # Fallback: random valid model that isn't the target
    candidates = [m for m in valid_models if m != target_model]
    return random.choice(candidates) if candidates else None


def get_random_model(model_list: List[str], exclude_model: Optional[str] = None) -> Optional[str]:
    """Get a random model from the list, excluding specified model."""
    candidates = [m for m in model_list if m != exclude_model]
    return random.choice(candidates) if candidates else None


def get_all_metrics() -> Dict[str, Any]:
    """Get all metrics data."""
    return load_metrics()


def get_model_ranking() -> List[Dict[str, Any]]:
    """Get models sorted by ranking with key metrics."""
    metrics = load_metrics()
    
    ranking = []
    for model_id, data in metrics["models"].items():
        ranking.append({
            "model": model_id,
            "rank": data["rank"],
            "composite_rating": round(data["composite_rating"], 2),
            "total_queries": data["total_queries"],
            "success_rate": round(
                data["successful_queries"] / data["total_queries"] * 100
                if data["total_queries"] > 0 else 0, 1
            ),
            "avg_tokens_per_sec": round(
                data["total_tokens_generated"] / (data["total_generation_time_ms"] / 1000)
                if data["total_generation_time_ms"] > 0 else 0, 1
            ),
            "average_scores": data["average_scores"]
        })
    
    ranking.sort(key=lambda x: x["rank"])
    return ranking


def _save_metrics_markdown(metrics: Dict[str, Any]):
    """Generate and save a markdown version of the metrics."""
    if not metrics.get("models"):
        return
    
    # Sort models by rank
    sorted_models = sorted(
        metrics["models"].items(),
        key=lambda x: x[1].get("rank", 999)
    )
    
    md_lines = [
        "# LLM Council Model Metrics",
        "",
        f"**Last Updated:** {metrics.get('last_updated', 'N/A')}",
        "",
        "## Model Rankings",
        "",
        "| Rank | Model | Rating | Success Rate | Evaluations |",
        "|------|-------|--------|--------------|-------------|",
    ]
    
    for model_id, data in sorted_models:
        rank = data.get("rank", "-")
        rating = round(data.get("composite_rating", 0), 2)
        total = data.get("total_queries", 0)
        success = data.get("successful_queries", 0)
        success_rate = f"{round(success / total * 100, 1)}%" if total > 0 else "N/A"
        eval_count = len(data.get("evaluations", {}).get("overall", []))
        
        # Truncate long model names
        display_name = model_id[:40] + "..." if len(model_id) > 40 else model_id
        
        md_lines.append(f"| {rank} | {display_name} | {rating}/5.0 | {success_rate} | {eval_count} |")
    
    md_lines.extend([
        "",
        "## Detailed Scores",
        "",
    ])
    
    for model_id, data in sorted_models:
        avg_scores = data.get("average_scores", {})
        md_lines.extend([
            f"### {model_id}",
            "",
            f"- **Composite Rating:** {round(data.get('composite_rating', 0), 2)}/5.0",
            f"- **Rank:** #{data.get('rank', '-')}",
            "",
            "| Category | Score |",
            "|----------|-------|",
            f"| Verbosity | {round(avg_scores.get('verbosity', 0), 1)}/5.0 |",
            f"| Expertise | {round(avg_scores.get('expertise', 0), 1)}/5.0 |",
            f"| Adherence | {round(avg_scores.get('adherence', 0), 1)}/5.0 |",
            f"| Clarity | {round(avg_scores.get('clarity', 0), 1)}/5.0 |",
            f"| Overall | {round(avg_scores.get('overall', 0), 1)}/5.0 |",
            "",
            f"**Stats:** {data.get('successful_queries', 0)}/{data.get('total_queries', 0)} successful queries, {data.get('retries', 0)} retries",
            "",
        ])
    
    # Write markdown file
    with open(METRICS_MD_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md_lines))
    
    print(f"[Metrics] Updated markdown: {METRICS_MD_FILE}")
