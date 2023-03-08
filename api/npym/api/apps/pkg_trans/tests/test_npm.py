import pytest

from npym.api.apps.pkg_trans.npm import NormName, Npm, _norm_py_name


@pytest.fixture
def npm():
    return Npm()


def test_get_package_info(npm: Npm):
    info = npm.get_package_info("prettier")
    assert info["name"] == "prettier"
    assert info["description"] == "Prettier is an opinionated code formatter"


def test_norm_py_name():
    assert _norm_py_name("prettier") == "prettier"
    assert _norm_py_name("foo__bar") == "foo-bar"
    assert _norm_py_name("foo/bar/baz42!!") == "foo-bar-baz42"


def test_make_norm_name(npm: Npm):
    assert npm._make_norm_name("prettier") == NormName(package="prettier")
    assert npm._make_norm_name("foo__bar") == NormName(package="foo-bar")
    assert npm._make_norm_name("foo/bar/baz42!!") == NormName(package="foo-bar-baz42")
    assert npm._make_norm_name("@foo/bar") == NormName(package="bar", org="foo")
    assert npm._make_norm_name("foo.bar") == NormName(package="foo-bar")


def test_safe_py_name(npm: Npm):
    assert (
        npm._make_norm_name("@14islands/r3f-scroll-rig").py_name
        == "npym.n14islands.r3f-scroll-rig"
    )
    assert npm._make_norm_name("@42/42").py_name == "npym.n42.n42"
    assert npm._make_norm_name("@_/_").py_name == "npym.undefined.undefined"
    assert npm._make_norm_name("42").py_name == "npym.n42"
