from dataclasses import dataclass
from typing import Literal, Optional, Sequence, Union

import lark
from packaging.version import Version as PyVersion
from semver import VersionInfo as SemVersion


class Sentinel:
    """
    This is a special version that is either always smaller or always bigger
    than any other version. This allows for open-ended intervals, like
    (1.0.0, MAX_VER) will signify ">=1.0.0".
    """

    def __init__(self, always_bigger: bool):
        self.always_bigger = always_bigger

    def __eq__(self, other):
        return isinstance(other, Sentinel) and self.always_bigger == other.always_bigger

    def __lt__(self, other):
        return not self.always_bigger

    def __gt__(self, other):
        return self.always_bigger

    def __le__(self, other):
        return self < other or self == other

    def __ge__(self, other):
        return self > other or self == other

    def __repr__(self):
        return "MAX_VER" if self.always_bigger else "MIN_VER"


MAX_VER = Sentinel(True)
MIN_VER = Sentinel(False)


VersionPart = Union[int, Literal["x"]]


@dataclass(frozen=True)
class PartialVersion:
    """
    The core idea behind the SemVer spec is that versions can be expressed as
    partials, which are potentially incomplete (or potentially complete)
    version numbers. Like "1.x" or "1.1.1".

    Then you can build stuff from that. Like "~1.1.1" or ">=2.4.1".

    What we're doing here is representing these partial versions as well as
    offering ways to apply the modifiers to them in order to get a concrete
    range of real SemVer values.
    """

    major: VersionPart
    minor: Optional[VersionPart] = None
    patch: Optional[VersionPart] = None
    prerelease: str = ""
    build: str = ""

    def _range_x(self) -> Optional["Range"]:
        """
        This happened to be common between several functions so we've
        factorized it here.
        """

        if self.major == "x":
            return Range(Bound(MIN_VER), Bound(MAX_VER))

        if self.minor is None or self.minor == "x":
            if self.major == 0:
                min_ver = MIN_VER
            else:
                min_ver = SemVersion(self.major, 0, 0)

            return Range(
                Bound(min_ver),
                Bound(
                    SemVersion(self.major + 1, 0, 0, prerelease="0"), inclusive=False
                ),
            )

        if self.patch is None or self.patch == "x":
            return Range(
                Bound(SemVersion(self.major, self.minor, 0)),
                Bound(
                    SemVersion(self.major, self.minor + 1, 0, prerelease="0"),
                    inclusive=False,
                ),
            )

    def as_range(self) -> "Range":
        """
        The range form is the range you'll get without a modifier.
        """

        if r := self._range_x():
            return r

        return Range(
            Bound(
                SemVersion(
                    self.major, self.minor, self.patch, prerelease=self.prerelease
                )
            ),
            Bound(
                SemVersion(
                    self.major, self.minor, self.patch, prerelease=self.prerelease
                )
            ),
        )

    def primitive(self, comparator: str) -> "Range":
        """
        Depending on the operator that was found, we'll call a different way of
        dealing with it. Basically, it's super fucked-up and mind-bending.
        """

        match comparator:
            case ">=":
                return self._primitive_ge()
            case ">":
                return self._primitive_gt()
            case "<=":
                return self._primitive_le()
            case "<":
                return self._primitive_lt()
            case "=":
                return self._primitive_eq()

    def _primitive_ge(self) -> "Range":
        """
        See primitive()
        """

        if self.major == "x":
            return Range(Bound(MIN_VER), Bound(MAX_VER))

        if self.minor is None or self.minor == "x":
            return Range(
                Bound(SemVersion(self.major, 0, 0)),
                Bound(MAX_VER),
            )

        if self.patch is None or self.patch == "x":
            return Range(
                Bound(SemVersion(self.major, self.minor, 0)),
                Bound(MAX_VER),
            )

        return Range(
            Bound(
                SemVersion(
                    self.major, self.minor, self.patch, prerelease=self.prerelease
                )
            ),
            Bound(MAX_VER),
        )

    def _primitive_gt(self) -> "Range":
        """
        See primitive()
        """

        if self.major == "x":
            return Range(Bound(MAX_VER), Bound(MAX_VER))

        if self.minor is None or self.minor == "x":
            return Range(
                Bound(SemVersion(self.major + 1, 0, 0)),
                Bound(MAX_VER),
            )

        if self.patch is None or self.patch == "x":
            return Range(
                Bound(SemVersion(self.major, self.minor + 1, 0)),
                Bound(MAX_VER),
            )

        return Range(
            Bound(
                SemVersion(
                    self.major, self.minor, self.patch, prerelease=self.prerelease
                ),
                inclusive=False,
            ),
            Bound(MAX_VER),
        )

    def _primitive_le(self) -> "Range":
        """
        See primitive()
        """

        if self.major == "x":
            return Range(Bound(MIN_VER), Bound(MAX_VER))

        if self.minor is None or self.minor == "x":
            return Range(
                Bound(MIN_VER),
                Bound(
                    SemVersion(self.major + 1, 0, 0, prerelease="0"), inclusive=False
                ),
            )

        if self.patch is None or self.patch == "x":
            return Range(
                Bound(MIN_VER),
                Bound(
                    SemVersion(self.major, self.minor + 1, 0, prerelease="0"),
                    inclusive=False,
                ),
            )

        return Range(
            Bound(MIN_VER),
            Bound(
                SemVersion(
                    self.major, self.minor, self.patch, prerelease=self.prerelease
                ),
                inclusive=True,
            ),
        )

    def _primitive_lt(self) -> "Range":
        """
        See primitive()
        """

        if self.major == "x":
            return Range(Bound(MIN_VER), Bound(MIN_VER))

        if self.minor is None or self.minor == "x":
            return Range(
                Bound(MIN_VER),
                Bound(SemVersion(self.major, 0, 0, prerelease="0"), inclusive=False),
            )

        if self.patch is None or self.patch == "x":
            return Range(
                Bound(MIN_VER),
                Bound(
                    SemVersion(self.major, self.minor, 0, prerelease="0"),
                    inclusive=False,
                ),
            )

        return Range(
            Bound(MIN_VER),
            Bound(
                SemVersion(
                    self.major, self.minor, self.patch, prerelease=self.prerelease
                ),
                inclusive=False,
            ),
        )

    def _primitive_eq(self) -> "Range":
        """
        See primitive()
        """

        return self.as_range()

    def tilde(self):
        """
        Apply the tilde logic
        """

        if r := self._range_x():
            return r

        return Range(
            Bound(
                SemVersion(
                    self.major, self.minor, self.patch, prerelease=self.prerelease
                )
            ),
            Bound(
                SemVersion(self.major, self.minor + 1, 0, prerelease="0"),
                inclusive=False,
            ),
        )

    def caret(self):
        """
        Apply the caret logic
        """

        if self.major == "x":
            return Range(Bound(MIN_VER), Bound(MAX_VER))

        if self.major == 0:
            return self.tilde()

        if (
            self.minor is None
            or self.minor == "x"
            or self.patch is None
            or self.patch == "x"
        ):
            minor = self.minor if isinstance(self.minor, int) else 0

            return Range(
                Bound(SemVersion(self.major, minor, 0)),
                Bound(
                    SemVersion(self.major + 1, 0, 0, prerelease="0"), inclusive=False
                ),
            )

        return Range(
            Bound(
                SemVersion(
                    self.major, self.minor, self.patch, prerelease=self.prerelease
                )
            ),
            Bound(SemVersion(self.major + 1, 0, 0, prerelease="0"), inclusive=False),
        )


Ver = Union[Sentinel, SemVersion]


@dataclass(frozen=True)
class Bound:
    """
    This is one end of a range. This is also sortable so that we can compute
    ranges overlaps and intersections easily.

    A bound is a version number, which can be inclusive or exclusive.
    """

    version: Ver
    inclusive: bool = True

    def _lt_bound(self, other: "Bound") -> bool:
        if (
            self.version.__class__ is other.version.__class__
            and self.version == other.version
        ):
            return self.inclusive and not other.inclusive

        if isinstance(self.version, Sentinel):
            return self.version.__lt__(other.version)
        elif isinstance(other.version, Sentinel):
            return other.version.__gt__(self.version)
        else:
            return self.version < other.version

    def _lt_version(self, other: SemVersion) -> bool:
        if self.inclusive:
            return self.version <= other
        else:
            return self.version < other

    def __lt__(self, other):
        if isinstance(other, Bound):
            return self._lt_bound(other)
        elif isinstance(other, SemVersion):
            return self._lt_version(other)
        else:
            raise ValueError(f"Cannot compare {type(other)} to Bound")

    def __le__(self, other):
        if isinstance(other, SemVersion):
            return self._lt_version(other)
        else:
            return self < other or self == other

    def __gt__(self, other):
        if isinstance(other, SemVersion):
            if self.inclusive:
                return self.version >= other
            else:
                return self.version > other
        else:
            return not self <= other

    def __ge__(self, other):
        if isinstance(other, SemVersion):
            return self > other
        else:
            return self > other or self == other

    def as_py_bound(self):
        """
        Convert from SemVer conventions to Python conventions
        """

        if isinstance(self.version, Sentinel):
            return PyBound(self.version)
        else:
            py = PyVersion(
                f"{self.version.finalize_version()}{self.version.prerelease or ''}{self.version.build or ''}"
            )
            return PyBound(py, self.inclusive)


# noinspection PyUnresolvedReferences
class RangeStrMixin:
    def __str__(self):
        """
        This is where we do the conversion to Python version specifiers. They
        are a bit different from the JS ones obviously. We just dump all the
        ranges as they are with some logic on top to try and detect some
        special cases that can be simplified (like two bounds are same? then
        ask for exact version instead of range).
        """

        min_s = isinstance(self.min.version, Sentinel)
        max_s = isinstance(self.max.version, Sentinel)

        if min_s and max_s:
            if min_s != max_s:
                return ">=0.0.0"
            else:
                return "<0.0.0"
        elif min_s:
            if self.min.inclusive:
                return f"<={self.max.version}"
            else:
                return f"<{self.max.version}"
        elif max_s:
            if self.max.inclusive:
                return f">={self.min.version}"
            else:
                return f">{self.min.version}"
        else:
            if (
                self.min.inclusive
                and self.max.inclusive
                and self.min.version == self.max.version
            ):
                return f"=={self.min.version}"

            if self.min.inclusive and self.max.inclusive:
                return f">={self.min.version},<={self.max.version}"
            elif self.min.inclusive:
                return f">={self.min.version},<{self.max.version}"
            elif self.max.inclusive:
                return f">{self.min.version},<={self.max.version}"
            else:
                return f">{self.min.version},<{self.max.version}"

    def __repr__(self):
        return f"{self.__class__.__name__}({self})"


@dataclass(frozen=True, repr=False)
class Range(RangeStrMixin):
    """
    A range between two bounds. This object is essential to the way we compute
    things in the sense that we transform every single partial into a range,
    which then allows to make computations on the ranges (like merge them if
    they intersect, apply different kind of conditions, etc).
    """

    min: Bound = Bound(MIN_VER)
    max: Bound = Bound(MAX_VER)

    def as_py_range(self):
        return PyRange(self.min.as_py_bound(), self.max.as_py_bound())

    def contains(self, version: SemVersion) -> bool:
        """
        Check if a version is contained in this range
        """

        return self.min.__lt__(version) and self.max.__gt__(version)


PyVer = Union[Sentinel, PyVersion]


@dataclass(frozen=True)
class PyBound:
    """
    Same as Bound but following Python conventions
    """

    version: PyVer
    inclusive: bool = True


@dataclass(frozen=True, repr=False)
class PyRange(RangeStrMixin):
    """
    Same as Range but following Python conventions
    """

    min: PyBound = PyBound(MIN_VER)
    max: PyBound = PyBound(MAX_VER)


@dataclass(frozen=True)
class PrimitiveNode:
    """
    Intermediate representation for parsing
    """

    op: Literal["<", "<=", ">", ">=", "="]
    version: PartialVersion


@dataclass(frozen=True)
class TildeNode:
    """
    Intermediate representation for parsing
    """

    version: PartialVersion


@dataclass(frozen=True)
class CaretNode:
    """
    Intermediate representation for parsing
    """

    version: PartialVersion


@dataclass(frozen=True)
class HyphenNode:
    """
    Intermediate representation for parsing
    """

    range: "Range"


@dataclass(frozen=True)
class SimpleSet:
    """
    Intermediate representation for parsing
    """

    ranges: Sequence[Range]


# Adapted from https://docs.npmjs.com/cli/v6/using-npm/semver#range-grammar
GRAMMAR = """
range_set: range range_or*
range_or: / *\|\| */ range
range: hyphen | simple_set
hyphen: partial " - " partial
simple_set: simple (" " simple)*
simple: primitive | partial | tilde | caret
primitive: comparator partial
         | comparator / +/ partial
comparator: /( >= | <= | > | < | =)/x
partial: xr [ "." xr [ "." xr [ qualifier ] ] ]
xr: wildcard | nr
wildcard: "x" | "X" | "*"
nr: /(0|[1-9][0-9]*)/
tilde: "~" partial
caret: "^" partial
qualifier: ("-" pre)? ("+" build)?
pre: parts
build: parts
parts: part ("." part)*
part: nr | /[-0-9A-Za-z]+/
"""

LARK_GRAMMAR = lark.Lark(GRAMMAR, start="range_set")


def _is_overlapping(a: Range, b: Range) -> bool:
    """
    Checks if two ranges are overlapping
    """

    return a.min <= b.max and b.min <= a.max


def _intersect_ranges(a: Range, b: Range) -> Sequence[Range]:
    """
    Computes the intersection between two ranges
    """

    if not _is_overlapping(a, b):
        return []

    return [
        Range(
            min=max(a.min, b.min),
            max=min(a.max, b.max),
        )
    ]


def intersect_ranges(ranges: Sequence[Range]) -> Sequence[Range]:
    """
    Computes the intersection between all the provided ranges at once.
    """

    if not ranges:
        return []

    out = [ranges[0]]

    for r in ranges:
        new_out = []

        for o in out:
            new_out.extend(_intersect_ranges(o, r))

        out = new_out

    return out


def _union_ranges(a: Range, b: Range) -> Sequence[Range]:
    """
    Generates the union between two ranges. Could result in one or two ranges
    output.
    """

    if _is_overlapping(a, b):
        return [
            Range(
                min=min(a.min, b.min),
                max=max(a.max, b.max),
            )
        ]

    return [a, b]


def union_ranges(ranges: Sequence[Range]) -> Sequence[Range]:
    """
    Makes a big union of all the provided ranges, simplifying as much as
    possible.
    """

    if not ranges:
        return []

    out = [ranges[0]]

    for r in ranges:
        new_out = []

        for o in out:
            new_out.extend(_union_ranges(o, r))

        out = new_out

    return out


class VersionSpecTransformer(lark.Transformer):
    """
    Transformer to decode the AST from Lark which parsed the version spec
    using the EBNF grammar above. The output of this transformation is expected
    to be a list of Range objects which are accepted as a dependency.
    """

    def nr(self, items):
        return int(items[0].value)

    def wildcard(self, _):
        return "x"

    def xr(self, items):
        return items[0]

    def part(self, items):
        return items[0]

    def parts(self, items):
        return ".".join(items)

    def build(self, items):
        return dict(build=items[0])

    def pre(self, items):
        return dict(prerelease=items[0])

    def qualifier(self, items):
        out = {}

        for item in items:
            out.update(item)

        return out

    def partial(self, items):
        parts = items[:-1]
        extra = items[-1] or {}

        return PartialVersion(*parts, **extra)

    def simple(self, items):
        match items[0]:
            case PrimitiveNode(op, version):
                return version.primitive(op)
            case TildeNode(version):
                return version.tilde()
            case CaretNode(version):
                return version.caret()
            case PartialVersion():
                return items[0].as_range()

    def comparator(self, items):
        return items[0].value

    def primitive(self, items):
        interesting = [i for i in items if not isinstance(i, lark.Token)]
        return PrimitiveNode(*interesting)

    def tilde(self, items):
        return TildeNode(items[0])

    def caret(self, items):
        return CaretNode(items[0])

    def hyphen(self, items):
        p1, p2 = items
        return HyphenNode(Range(p1.as_range().min, p2.as_range().max))

    def simple_set(self, items):
        return SimpleSet(items)

    def range(self, items):
        match items[0]:
            case HyphenNode(range=r):
                return [r]
            case SimpleSet(ranges):
                return ranges
            case _:
                raise NotImplementedError

    def range_or(self, items):
        return items[1]

    def range_set(self, items):
        out = []

        for item in items:
            i = intersect_ranges(item)

            if i:
                out.extend(i)

        return out


def parse_spec(spec: str) -> Sequence[Range]:
    """
    Transforms a version spec into a list of ranges
    """

    try:
        tree = LARK_GRAMMAR.parse(spec)
    except lark.exceptions.UnexpectedCharacters:
        raise ValueError(f"Invalid version spec: {spec}")
    else:
        return VersionSpecTransformer().transform(tree)


def flatten_py_range(spec: str, ranges: Sequence[PyRange]) -> str:
    """
    Handles different cases of ranges.

    What is missing is if there are several ranges with a whole in the middle.
    Python provides a way to negate some versions but the conversion is not
    straightforward at all so for now we'll just crash and burn if this
    happens.
    """

    if len(ranges) == 0:
        return "<0.0.0"
    elif len(ranges) == 1:
        return f"{ranges[0]}"
    else:
        raise ValueError(f"Cannot convert spec: {spec}")


def sem_range_to_py_range(spec: str) -> str:
    """
    Converts a SemVer version specifier into something you can put in a wheel.
    """

    parsed_spec = parse_spec(spec)
    js_ranges = union_ranges(parsed_spec)
    py_ranges = [r.as_py_range() for r in js_ranges]

    return flatten_py_range(spec, py_ranges)
