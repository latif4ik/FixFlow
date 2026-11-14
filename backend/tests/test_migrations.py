from sqlalchemy import text


def test_btree_gist_extension_installed(db_engine) -> None:
    with db_engine.connect() as conn:
        found = conn.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'btree_gist'")
        ).scalar()
    assert found == "btree_gist"
