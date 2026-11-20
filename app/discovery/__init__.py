"""CINEMY Homepage Discovery Services (Trending Now, Evergreen Picks, Recommended for You)."""
from .trending import get_trending_titles, invalidate_trending_cache
from .popular import (
    get_evergreen,
    get_evergreen_titles,
    get_popular_titles,
    invalidate_evergreen_cache,
    invalidate_popular_cache,
)
from .recommendations import get_recommended_titles, invalidate_recommendations_cache


def invalidate_discovery_cache() -> None:
    invalidate_trending_cache()
    invalidate_evergreen_cache()
    invalidate_recommendations_cache()


__all__ = [
    "get_trending_titles",
    "get_evergreen_titles",
    "get_evergreen",
    "get_popular_titles",
    "get_recommended_titles",
    "invalidate_trending_cache",
    "invalidate_evergreen_cache",
    "invalidate_popular_cache",
    "invalidate_recommendations_cache",
    "invalidate_discovery_cache",
]
