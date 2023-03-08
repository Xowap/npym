import pytest
from semver import VersionInfo as SemVersion

from npym.api.apps.pkg_trans.version_man import (
    MAX_VER,
    MIN_VER,
    Bound,
    PartialVersion,
    Range,
    _intersect_ranges,
    intersect_ranges,
    parse_spec,
    sem_range_to_py_range,
)


def test_bound():
    assert Bound(SemVersion(2, 0, 0)) <= Bound(SemVersion(2, 0, 0))
    assert Bound(SemVersion(2, 0, 0)) < Bound(SemVersion(3, 0, 0))
    assert Bound(SemVersion(3, 0, 0)) > Bound(SemVersion(2, 0, 0))
    assert Bound(SemVersion(3, 0, 0)) >= Bound(SemVersion(2, 0, 0))
    assert Bound(SemVersion(2, 0, 0)) == Bound(SemVersion(2, 0, 0))
    assert Bound(SemVersion(2, 0, 0)) != Bound(SemVersion(2, 0, 0), inclusive=False)
    assert Bound(SemVersion(2, 0, 0)) < Bound(SemVersion(2, 0, 0), inclusive=False)


def test_partial_version_as_range():
    assert PartialVersion("x").as_range() == Range(
        min=Bound(MIN_VER),
        max=Bound(MAX_VER),
    )
    assert PartialVersion(1, "x").as_range() == Range(
        min=Bound(SemVersion(1, 0, 0), inclusive=True),
        max=Bound(SemVersion(2, 0, 0, prerelease="0"), inclusive=False),
    )
    assert PartialVersion(1, 1, "x").as_range() == Range(
        min=Bound(SemVersion(1, 1, 0), inclusive=True),
        max=Bound(SemVersion(1, 2, 0, prerelease="0"), inclusive=False),
    )
    assert PartialVersion(1, 1, 1, "foo", "bar").as_range() == Range(
        min=Bound(SemVersion(1, 1, 1, prerelease="foo"), inclusive=True),
        max=Bound(SemVersion(1, 1, 1, prerelease="foo"), inclusive=True),
    )


def test_partial_version_primitive_ge():
    assert PartialVersion("x").primitive(">=") == Range(
        min=Bound(MIN_VER),
        max=Bound(MAX_VER),
    )
    assert PartialVersion(1, "x").primitive(">=") == Range(
        min=Bound(SemVersion(1, 0, 0), inclusive=True),
        max=Bound(MAX_VER),
    )
    assert PartialVersion(1, 1, "x").primitive(">=") == Range(
        min=Bound(SemVersion(1, 1, 0), inclusive=True),
        max=Bound(MAX_VER),
    )
    assert PartialVersion(1, 1, 1, "foo", "bar").primitive(">=") == Range(
        min=Bound(SemVersion(1, 1, 1, prerelease="foo"), inclusive=True),
        max=Bound(MAX_VER),
    )


def test_partial_version_primitive_gt():
    assert PartialVersion("x").primitive(">") == Range(
        min=Bound(MAX_VER),
        max=Bound(MAX_VER),
    )
    assert PartialVersion(1, "x").primitive(">") == Range(
        min=Bound(SemVersion(2, 0, 0), inclusive=True),
        max=Bound(MAX_VER),
    )
    assert PartialVersion(1, 1, "x").primitive(">") == Range(
        min=Bound(SemVersion(1, 2, 0), inclusive=True),
        max=Bound(MAX_VER),
    )
    assert PartialVersion(1, 1, 1, "foo", "bar").primitive(">") == Range(
        min=Bound(SemVersion(1, 1, 1, prerelease="foo"), inclusive=False),
        max=Bound(MAX_VER),
    )


def test_partial_version_primitive_le():
    assert PartialVersion("x").primitive("<=") == Range(
        min=Bound(MIN_VER),
        max=Bound(MAX_VER),
    )
    assert PartialVersion(1, "x").primitive("<=") == Range(
        min=Bound(MIN_VER),
        max=Bound(SemVersion(2, 0, 0, prerelease="0"), inclusive=False),
    )
    assert PartialVersion(1, 1, "x").primitive("<=") == Range(
        min=Bound(MIN_VER),
        max=Bound(SemVersion(1, 2, 0, prerelease="0"), inclusive=False),
    )
    assert PartialVersion(1, 1, 1, "foo", "bar").primitive("<=") == Range(
        min=Bound(MIN_VER),
        max=Bound(SemVersion(1, 1, 1, prerelease="foo"), inclusive=True),
    )


def test_partial_version_primitive_lt():
    assert PartialVersion("x").primitive("<") == Range(
        min=Bound(MIN_VER),
        max=Bound(MIN_VER),
    )
    assert PartialVersion(1, "x").primitive("<") == Range(
        min=Bound(MIN_VER),
        max=Bound(SemVersion(1, 0, 0, prerelease="0"), inclusive=False),
    )
    assert PartialVersion(1, 1, "x").primitive("<") == Range(
        min=Bound(MIN_VER),
        max=Bound(SemVersion(1, 1, 0, prerelease="0"), inclusive=False),
    )
    assert PartialVersion(1, 1, 1, "foo", "bar").primitive("<") == Range(
        min=Bound(MIN_VER),
        max=Bound(SemVersion(1, 1, 1, prerelease="foo"), inclusive=False),
    )


def test_partial_version_primitive_eq():
    assert PartialVersion("x").primitive("=") == Range(
        min=Bound(MIN_VER),
        max=Bound(MAX_VER),
    )
    assert PartialVersion(1, "x").primitive("=") == Range(
        min=Bound(SemVersion(1, 0, 0), inclusive=True),
        max=Bound(SemVersion(2, 0, 0, prerelease="0"), inclusive=False),
    )
    assert PartialVersion(1, 1, "x").primitive("=") == Range(
        min=Bound(SemVersion(1, 1, 0), inclusive=True),
        max=Bound(SemVersion(1, 2, 0, prerelease="0"), inclusive=False),
    )
    assert PartialVersion(1, 1, 1, "foo", "bar").primitive("=") == Range(
        min=Bound(SemVersion(1, 1, 1, prerelease="foo"), inclusive=True),
        max=Bound(SemVersion(1, 1, 1, prerelease="foo"), inclusive=True),
    )


# noinspection DuplicatedCode
def test_partial_version_tilde():
    assert PartialVersion("x").tilde() == Range(
        min=Bound(MIN_VER),
        max=Bound(MAX_VER),
    )
    assert PartialVersion(0, "x").tilde() == Range(
        min=Bound(MIN_VER),
        max=Bound(SemVersion(1, 0, 0, prerelease="0"), inclusive=False),
    )
    assert PartialVersion(1, "x").tilde() == Range(
        min=Bound(SemVersion(1, 0, 0), inclusive=True),
        max=Bound(SemVersion(2, 0, 0, prerelease="0"), inclusive=False),
    )
    assert PartialVersion(1, 1, "x").tilde() == Range(
        min=Bound(SemVersion(1, 1, 0), inclusive=True),
        max=Bound(SemVersion(1, 2, 0, prerelease="0"), inclusive=False),
    )
    assert PartialVersion(1, 1, 1, "foo", "bar").tilde() == Range(
        min=Bound(SemVersion(1, 1, 1, prerelease="foo"), inclusive=True),
        max=Bound(SemVersion(1, 2, 0, prerelease="0"), inclusive=False),
    )


# noinspection DuplicatedCode
def test_partial_version_caret():
    assert PartialVersion("x").caret() == Range(
        min=Bound(MIN_VER),
        max=Bound(MAX_VER),
    )
    assert PartialVersion(0, "x").caret() == Range(
        min=Bound(MIN_VER),
        max=Bound(SemVersion(1, 0, 0, prerelease="0"), inclusive=False),
    )
    assert PartialVersion(0, 1, "x").caret() == Range(
        min=Bound(SemVersion(0, 1, 0), inclusive=True),
        max=Bound(SemVersion(0, 2, 0, prerelease="0"), inclusive=False),
    )
    assert PartialVersion(0, 1, 1, "foo", "bar").caret() == Range(
        min=Bound(SemVersion(0, 1, 1, prerelease="foo"), inclusive=True),
        max=Bound(SemVersion(0, 2, 0, prerelease="0"), inclusive=False),
    )
    assert PartialVersion(1, "x").caret() == Range(
        min=Bound(SemVersion(1, 0, 0), inclusive=True),
        max=Bound(SemVersion(2, 0, 0, prerelease="0"), inclusive=False),
    )
    assert PartialVersion(1, 1, "x").caret() == Range(
        min=Bound(SemVersion(1, 1, 0), inclusive=True),
        max=Bound(SemVersion(2, 0, 0, prerelease="0"), inclusive=False),
    )
    assert PartialVersion(1, 1, 1, "foo", "bar").caret() == Range(
        min=Bound(SemVersion(1, 1, 1, prerelease="foo"), inclusive=True),
        max=Bound(SemVersion(2, 0, 0, prerelease="0"), inclusive=False),
    )


def test_intersect_ranges():
    assert _intersect_ranges(
        a=Range(
            min=Bound(SemVersion(1, 0, 0)),
            max=Bound(SemVersion(2, 0, 0)),
        ),
        b=Range(
            min=Bound(SemVersion(1, 0, 0)),
            max=Bound(SemVersion(2, 0, 0)),
        ),
    ) == [
        Range(
            min=Bound(SemVersion(1, 0, 0)),
            max=Bound(SemVersion(2, 0, 0)),
        )
    ]

    assert (
        _intersect_ranges(
            a=Range(
                min=Bound(SemVersion(1, 0, 0)),
                max=Bound(SemVersion(2, 0, 0)),
            ),
            b=Range(
                min=Bound(SemVersion(2, 0, 0), inclusive=False),
                max=Bound(SemVersion(3, 0, 0)),
            ),
        )
        == []
    )

    assert _intersect_ranges(
        a=Range(
            min=Bound(SemVersion(1, 0, 0)),
            max=Bound(SemVersion(2, 0, 0)),
        ),
        b=Range(
            min=Bound(SemVersion(2, 0, 0)),
            max=Bound(SemVersion(3, 0, 0)),
        ),
    ) == [
        Range(
            min=Bound(SemVersion(2, 0, 0), inclusive=True),
            max=Bound(SemVersion(2, 0, 0), inclusive=True),
        )
    ]

    assert intersect_ranges(
        [
            Range(Bound(SemVersion(1, 0, 0), inclusive=False), Bound(MAX_VER)),
            Range(
                Bound(MIN_VER),
                Bound(SemVersion(4, 0, 0, prerelease="0"), inclusive=False),
            ),
        ]
    ) == [
        Range(
            min=Bound(SemVersion(1, 0, 0), inclusive=False),
            max=Bound(SemVersion(4, 0, 0, prerelease="0"), inclusive=False),
        ),
    ]

    assert intersect_ranges(
        [
            Range(Bound(SemVersion(1, 0, 0), inclusive=False), Bound(MAX_VER)),
            Range(Bound(MIN_VER), Bound(SemVersion(4, 0, 0), inclusive=False)),
            Range(
                Bound(MIN_VER),
                Bound(SemVersion(3, 5, 0, prerelease="0"), inclusive=False),
            ),
            Range(Bound(SemVersion(1, 2, 0), inclusive=False), Bound(MAX_VER)),
        ]
    ) == [
        Range(
            min=Bound(SemVersion(1, 2, 0), inclusive=False),
            max=Bound(SemVersion(3, 5, 0, prerelease="0"), inclusive=False),
        ),
    ]


def test_parse_spec():
    assert parse_spec(">1 <=3 <=3.4 >1.2 || 5.x") == [
        Range(
            min=Bound(SemVersion(2, 0, 0), inclusive=True),
            max=Bound(SemVersion(3, 5, 0, prerelease="0"), inclusive=False),
        ),
        Range(
            min=Bound(SemVersion(5, 0, 0)),
            max=Bound(SemVersion(6, 0, 0, prerelease="0"), inclusive=False),
        ),
    ]

    assert parse_spec("1.x || 2.x || 3.x") == [
        Range(
            min=Bound(SemVersion(1, 0, 0), inclusive=True),
            max=Bound(SemVersion(2, 0, 0, prerelease="0"), inclusive=False),
        ),
        Range(
            min=Bound(SemVersion(2, 0, 0), inclusive=True),
            max=Bound(SemVersion(3, 0, 0, prerelease="0"), inclusive=False),
        ),
        Range(
            min=Bound(SemVersion(3, 0, 0), inclusive=True),
            max=Bound(SemVersion(4, 0, 0, prerelease="0"), inclusive=False),
        ),
    ]

    assert parse_spec("1.0.x-a.b+d.e") == [
        Range(
            min=Bound(SemVersion(1, 0, 0), inclusive=True),
            max=Bound(SemVersion(1, 1, 0, prerelease="0"), inclusive=False),
        ),
    ]

    assert parse_spec("~1") == [
        Range(
            min=Bound(SemVersion(1, 0, 0), inclusive=True),
            max=Bound(SemVersion(2, 0, 0, prerelease="0"), inclusive=False),
        )
    ]

    assert parse_spec("~1.1") == [
        Range(
            min=Bound(SemVersion(1, 1, 0), inclusive=True),
            max=Bound(SemVersion(1, 2, 0, prerelease="0"), inclusive=False),
        )
    ]

    assert parse_spec("^1") == [
        Range(
            min=Bound(SemVersion(1, 0, 0), inclusive=True),
            max=Bound(SemVersion(2, 0, 0, prerelease="0"), inclusive=False),
        )
    ]

    assert parse_spec("^0.1") == [
        Range(
            min=Bound(SemVersion(0, 1, 0), inclusive=True),
            max=Bound(SemVersion(0, 2, 0, prerelease="0"), inclusive=False),
        )
    ]

    assert parse_spec("^1.1") == [
        Range(
            min=Bound(SemVersion(1, 1, 0), inclusive=True),
            max=Bound(SemVersion(2, 0, 0, prerelease="0"), inclusive=False),
        )
    ]

    assert parse_spec("1.x - 2.x") == [
        Range(
            min=Bound(SemVersion(1, 0, 0), inclusive=True),
            max=Bound(SemVersion(3, 0, 0, prerelease="0"), inclusive=False),
        )
    ]

    assert parse_spec("1.0.0 - 2.9999.9999") == [
        Range(
            min=Bound(SemVersion(1, 0, 0)),
            max=Bound(SemVersion(2, 9999, 9999)),
        ),
    ]

    assert parse_spec(">=1.0.2 <2.1.2") == [
        Range(
            min=Bound(SemVersion(1, 0, 2)),
            max=Bound(SemVersion(2, 1, 2), inclusive=False),
        ),
    ]

    assert parse_spec(">1.0.2 <=2.3.4") == [
        Range(
            min=Bound(SemVersion(1, 0, 2), inclusive=False),
            max=Bound(SemVersion(2, 3, 4)),
        ),
    ]

    assert parse_spec("2.0.1") == [
        Range(
            min=Bound(SemVersion(2, 0, 1)),
            max=Bound(SemVersion(2, 0, 1)),
        ),
    ]

    assert parse_spec("<1.0.0 || >=2.3.1 <2.4.5 || >=2.5.2 <3.0.0") == [
        Range(
            max=Bound(SemVersion(1, 0, 0), inclusive=False),
        ),
        Range(
            min=Bound(SemVersion(2, 3, 1)),
            max=Bound(SemVersion(2, 4, 5), inclusive=False),
        ),
        Range(
            min=Bound(SemVersion(2, 5, 2)),
            max=Bound(SemVersion(3, 0, 0), inclusive=False),
        ),
    ]

    with pytest.raises(ValueError):
        parse_spec("http://asdf.com/asdf.tar.gz")

    assert parse_spec("~1.2") == [
        Range(
            min=Bound(SemVersion(1, 2, 0), inclusive=True),
            max=Bound(SemVersion(1, 3, 0, prerelease="0"), inclusive=False),
        ),
    ]

    assert parse_spec("~1.2.3") == [
        Range(
            min=Bound(SemVersion(1, 2, 3), inclusive=True),
            max=Bound(SemVersion(1, 3, 0, prerelease="0"), inclusive=False),
        ),
    ]

    assert parse_spec("2.x") == [
        Range(
            min=Bound(SemVersion(2, 0, 0), inclusive=True),
            max=Bound(SemVersion(3, 0, 0, prerelease="0"), inclusive=False),
        ),
    ]

    assert parse_spec("3.3.x") == [
        Range(
            min=Bound(SemVersion(3, 3, 0), inclusive=True),
            max=Bound(SemVersion(3, 4, 0, prerelease="0"), inclusive=False),
        ),
    ]

    assert parse_spec("~0.1.2") == [
        Range(
            min=Bound(SemVersion(0, 1, 2), inclusive=True),
            max=Bound(SemVersion(0, 2, 0, prerelease="0"), inclusive=False),
        ),
    ]

    assert parse_spec("~1.1.2") == [
        Range(
            min=Bound(SemVersion(1, 1, 2), inclusive=True),
            max=Bound(SemVersion(1, 2, 0, prerelease="0"), inclusive=False),
        ),
    ]

    assert parse_spec("^0.1.2") == [
        Range(
            min=Bound(SemVersion(0, 1, 2), inclusive=True),
            max=Bound(SemVersion(0, 2, 0, prerelease="0"), inclusive=False),
        ),
    ]

    assert parse_spec("^1.1.2") == [
        Range(
            min=Bound(SemVersion(1, 1, 2), inclusive=True),
            max=Bound(SemVersion(2, 0, 0, prerelease="0"), inclusive=False),
        ),
    ]

    with pytest.raises(ValueError):
        parse_spec("latest")

    with pytest.raises(ValueError):
        parse_spec("file:../dyl")


def test_sem_convert():
    assert sem_range_to_py_range("1.0.0") == "==1.0.0"
    assert sem_range_to_py_range(">= 12.37.2") == ">=12.37.2"
    assert sem_range_to_py_range("1.*") == ">=1.0.0,<2.0.0"
    assert sem_range_to_py_range("1.x - 2.x") == ">=1.0.0,<3.0.0"
    assert sem_range_to_py_range("~1.2.3") == ">=1.2.3,<1.3.0"
    assert sem_range_to_py_range(">4") == ">=5.0.0"
    assert sem_range_to_py_range(">2 >4 <8 || 5.x") == ">=5.0.0,<8.0.0"


def test_range_ver_compare():
    assert parse_spec("1.0.0")[0].contains(SemVersion.parse("1.0.0"))
    assert not parse_spec("1.0.0")[0].contains(SemVersion.parse("1.0.1"))

    assert not parse_spec("1.x")[0].contains(SemVersion.parse("1.0.0-beta.1"))
    assert parse_spec("1.x")[0].contains(SemVersion.parse("1.0.0"))
    assert parse_spec("1.x")[0].contains(SemVersion.parse("1.2.0"))
    assert not parse_spec("1.x")[0].contains(SemVersion.parse("2.0.0"))

    assert not parse_spec("~1.2.3")[0].contains(SemVersion.parse("1.2.0"))
    assert parse_spec("~1.2.3")[0].contains(SemVersion.parse("1.2.3"))
    assert parse_spec("~1.2.3")[0].contains(SemVersion.parse("1.2.42"))
    assert not parse_spec("~1.2.3")[0].contains(SemVersion.parse("1.3.0"))
