from npym.api.apps.pkg_trans.resolver import hash_data


def test_hash_data():
    assert hash_data("test") == "4d967a30"
    assert hash_data(dict(foo=42)) == hash_data(dict(foo=42))
    assert hash_data(dict(foo=42, bar=True)) == hash_data(dict(bar=True, foo=42))
