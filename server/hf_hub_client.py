"""
Re-export do cliente Hugging Face Hub a partir de server.workers.hf_hub_client.
Permite import direto via `from server.hf_hub_client import ...` ou `from hf_hub_client import ...`.
"""

from workers.hf_hub_client import HFHubClient, search_hf_models

__all__ = ["HFHubClient", "search_hf_models"]
