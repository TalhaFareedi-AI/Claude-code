from app import catalog


def test_fallbacks_preserve_tier_and_private_route_restrictions(db):
    primary = next(model for model in catalog.listing(db) if model["tier"] == "smart")
    fallback = catalog.fallbacks(db, primary["id"], n=1)[0]
    db.run("UPDATE model_catalog SET private_route=0 WHERE id=?", (fallback,))
    private = catalog.fallbacks(db, primary["id"], n=20, private_only=True, tiers_allowed=["smart"])
    assert fallback not in private
    assert private
    assert all(catalog.get(db, mid)["private_route"] and catalog.get(db, mid)["tier"] == "smart" for mid in private)
    assert catalog.fallbacks(db, primary["id"], tiers_allowed=["quick"]) == []


def test_live_catalog_preserves_an_explicit_zero_cache_price(db):
    catalog.sync_live(db, [{"id": "example/research-model", "pricing": {
        "prompt": "0.000001", "completion": "0.000002", "input_cache_read": "0",
    }}])
    model = catalog.get(db, "example/research-model")
    assert model["price_cached"] == 0
    assert model["approved"] == 0
