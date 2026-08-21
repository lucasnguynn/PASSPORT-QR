def test_social_scaffold_exists() -> None:
    from app.modules.social.router import router

    assert router.prefix == "/api/social"
