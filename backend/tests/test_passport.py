def test_passport_scaffold_exists() -> None:
    from app.modules.passport.router import router

    assert router.prefix == "/api/passport"
