from backend.context.doc_urls import attach_public_doc_urls, public_doc_url
from backend.formatting.intent_formatters import format_doc_search
from backend.models.config import AlfredConfig, GitConfig, GitRepoProfile


def _docs_config() -> AlfredConfig:
    return AlfredConfig(
        git=GitConfig(
            enabled=True,
            default_org="Acme",
            repo_profiles=[
                GitRepoProfile(
                    repo="Acme/docs",
                    role="docs",
                    docs_public_base_url="https://docs.example.com",
                )
            ],
        )
    )


def test_public_doc_url_maps_configured_docs_paths():
    config = _docs_config()
    assert (
        public_doc_url("getting-started/introduction.mdx", repo="Acme/docs", config=config)
        == "https://docs.example.com/getting-started/introduction"
    )
    assert (
        public_doc_url("platforms/hydrogen.mdx", repo="Acme/docs", config=config)
        == "https://docs.example.com/platforms/hydrogen"
    )
    assert public_doc_url("README.md", repo="Acme/app", config=config) == ""


def test_public_doc_url_uses_profile_override():
    config = AlfredConfig(
        git=GitConfig(
            enabled=True,
            default_org="Acme",
            repo_profiles=[
                GitRepoProfile(
                    repo="Acme/docs",
                    role="docs",
                    docs_public_base_url="https://docs.example.test",
                )
            ],
        )
    )
    assert (
        public_doc_url("misc/faq.mdx", repo="Acme/docs", config=config)
        == "https://docs.example.test/misc/faq"
    )


def test_attach_public_doc_urls_adds_url_field():
    hits = attach_public_doc_urls(
        [{"path": "platforms/hydrogen.mdx", "title": "Hydrogen", "repo": "Acme/docs"}],
        config=_docs_config(),
    )
    assert hits[0]["url"] == "https://docs.example.com/platforms/hydrogen"


def test_public_doc_url_without_configured_base_is_empty():
    assert public_doc_url("platforms/hydrogen.mdx", repo="Acme/docs") == ""


def test_format_doc_search_includes_public_url():
    text = format_doc_search(
        {
            "query": "headless checkout",
            "results": [
                {
                    "path": "platforms/hydrogen.mdx",
                    "title": "Hydrogen",
                    "excerpt": "Checkout SDK",
                    "url": "https://docs.example.com/platforms/hydrogen",
                }
            ],
        }
    )
    assert "https://docs.example.com/platforms/hydrogen" in text
    assert "Hydrogen" in text
