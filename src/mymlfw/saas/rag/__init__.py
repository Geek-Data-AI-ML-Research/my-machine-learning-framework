"""Project Brain RAG package (Phase E)."""

from mymlfw.saas.rag.citation_firewall import enforce_citation_firewall
from mymlfw.saas.rag.cold_start import blend_tier2_into_corpus, dataset_fingerprint
from mymlfw.saas.rag.contrastive import build_episode_card
from mymlfw.saas.rag.consolidate import consolidate_project_brain
from mymlfw.saas.rag.contradiction import mark_needs_reverification
from mymlfw.saas.rag.query_expand import expand_query
from mymlfw.saas.rag.retrieve import gather_corpus, retrieve_three_buckets
from mymlfw.saas.rag.rrf import rrf_fuse
from mymlfw.saas.rag.utility import bump_times_cited, update_cited_memory_utility

__all__ = [
    "blend_tier2_into_corpus",
    "build_episode_card",
    "bump_times_cited",
    "consolidate_project_brain",
    "dataset_fingerprint",
    "enforce_citation_firewall",
    "expand_query",
    "gather_corpus",
    "mark_needs_reverification",
    "retrieve_three_buckets",
    "rrf_fuse",
    "update_cited_memory_utility",
]
