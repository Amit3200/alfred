from backend.context.doc_urls import attach_public_doc_urls, public_doc_url
from backend.formatting.intent_formatters import format_doc_search
from backend.models.config import AlfredConfig, GitConfig, GitRepoProfile


def test_public_doc_url_maps_flexype_docs_paths():
    assert (
        public_doc_url("getting-started/introduction.mdx", repo="FlexyPe/docs")
        == "https://docs.flexype.io/getting-started/introduction"
    )
    assert (
        public_doc_url("platforms/hydrogen.mdx", repo="FlexyPe/docs")
        == "https://docs.flexype.io/platforms/hydrogen"
    )
    assert public_doc_url("README.md", repo="FlexyPe/cipher") == ""


def test_public_doc_url_uses_profile_override():
    config = AlfredConfig(
        git=GitConfig(
            enabled=True,
            default_org="FlexyPe",
            repo_profiles=[
                GitRepoProfile(
                    repo="FlexyPe/docs",
                    role="docs",
                    docs_public_base_url="https://docs.example.test",
                )
            ],
        )
    )
    assert (
        public_doc_url("misc/faq.mdx", repo="FlexyPe/docs", config=config)
        == "https://docs.example.test/misc/faq"
    )


def test_attach_public_doc_urls_adds_url_field():
    hits = attach_public_doc_urls(
        [{"path": "platforms/hydrogen.mdx", "title": "Hydrogen", "repo": "FlexyPe/docs"}]
    )
    assert hits[0]["url"] == "https://docs.flexype.io/platforms/hydrogen"


def test_format_doc_search_includes_public_url():
    text = format_doc_search(
        {
            "query": "headless checkout",
            "results": [
                {
                    "path": "platforms/hydrogen.mdx",
                    "title": "Hydrogen",
                    "excerpt": "Checkout SDK",
                    "url": "https://docs.flexype.io/platforms/hydrogen",
                }
            ],
        }
    )
    assert "https://docs.flexype.io/platforms/hydrogen" in text
    assert "Hydrogen" in text
