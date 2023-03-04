from npym.api.apps.pkg_trans.translator import (
    DedupMapEntry,
    dedup_map,
    dedup_python_key,
)


def test_dedup_map():
    assert dedup_map({"foo": 1, "FOO": 2}, dedup_python_key) == {
        "foo": DedupMapEntry("foo", "foo", 1),
        "foo_1": DedupMapEntry("FOO", "foo_1", 2),
    }

    assert dedup_map({"foo.bar": 1, "foo/bar": 2, "foo-bar": 3}, dedup_python_key) == {
        "foo_bar": DedupMapEntry("foo.bar", "foo_bar", 1),
        "foo_bar_1": DedupMapEntry("foo/bar", "foo_bar_1", 2),
        "foo_bar_2": DedupMapEntry("foo-bar", "foo_bar_2", 3),
    }
