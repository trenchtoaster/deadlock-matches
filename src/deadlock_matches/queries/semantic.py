"""Metric views: dimensions and measures defined once, composed by summarize()."""

from __future__ import annotations

import functools
import inspect
import operator
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from functools import reduce
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Protocol

import polars as pl

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence
    from pathlib import Path


def try_divide(numerator: pl.Expr, denominator: pl.Expr) -> pl.Expr:
    """Divide one aggregate by another, null rather than inf when the denominator is zero.

    - both sides stay aggregates so the rate recomputes at whatever grain
      summarize groups by, instead of averaging per-group rates
    - the raw value comes back unscaled and unrounded, percent signs and
      decimal places belong wherever the number is printed
    """
    return (
        pl.when(denominator.is_not_null() & (denominator != 0))
        .then(numerator / denominator)
        .otherwise(pl.lit(None, dtype=pl.Float64))
    )


@dataclass(frozen=True)
class Dimension:
    """A groupable column and the expression that derives it.

    - display_name is the heading a report prints, the declared name stays
      the one queries use
    - synonyms are other names that reach the same dimension, so two callers
      asking differently still land on one definition and one column
    """

    expr: pl.Expr
    comment: str = ""
    resolve: Callable[[Any], pl.Expr] | None = field(default=None, repr=False)
    display_name: str = ""
    synonyms: tuple[str, ...] = ()

    def filter_expr(self, value: Any) -> pl.Expr:
        """Build the filter for one value, a collection of values, or a ready expression.

        - a collection resolves member by member, so a dimension that maps
          names to ids still validates each name
        """
        if isinstance(value, pl.Expr):
            return value

        if isinstance(value, (list, tuple, set, frozenset)):
            values = list(value)

            if self.resolve is None:
                return self.expr.is_in(values)

            return reduce(
                operator.or_,
                (self.resolve(member) for member in values),
                pl.lit(value=False),
            )

        if self.resolve is not None:
            return self.resolve(value)

        return self.expr == value


@dataclass(frozen=True)
class Format:
    """How a number is printed, which the unit deliberately never says.

    - scale multiplies on the way out, so a proportion stays a proportion
      everywhere except inside the string, and game units print as meters
      without any column ever holding meters
    - a measure that declares no format gets the one its unit implies,
      which is what stops a percent being scaled at one call site and
      missed at another
    - small keeps decimals a column of whole numbers would otherwise round
      away, so a source worth four a minute does not print beside one worth
      nine thousand as though both were whole
    """

    decimals: int = 0
    scale: float = 1.0
    group: bool = False
    prefix: str = ""
    suffix: str = ""
    small: int = 0

    SMALL_BELOW: ClassVar[int] = 10

    def places(self, scaled: float) -> int:
        """Count the decimals one value prints with."""
        if not self.small or abs(scaled) >= self.SMALL_BELOW:
            return self.decimals

        return self.decimals if abs(scaled - round(scaled)) < 1e-9 else self.small

    def render(self, value: float | None, blank: str = "", *, sign: bool = False) -> str:
        """Print one value, or blank when it is null.

        - sign keeps a leading + on a positive number, which a gap column
          needs and a plain value column does not
        """
        if value is None:
            return blank

        scaled = value * self.scale
        separator = "," if self.group else ""
        flag = "+" if sign else ""

        return f"{self.prefix}{scaled:{flag}{separator}.{self.places(scaled)}f}{self.suffix}"


_UNIT_FORMATS = {
    "badge": Format(),
    "count": Format(group=True),
    "minutes": Format(decimals=1),
    "proportion": Format(decimals=1, scale=100, suffix="%"),
    "ratio": Format(decimals=2),
    "souls": Format(group=True),
    "subrank": Format(decimals=1),
}

UNITS = frozenset(_UNIT_FORMATS)


SEMIADDITIVE = frozenset({"first", "last"})

RANGES = frozenset({"cumulative"})

DIRECTIONS = frozenset({"maximize", "minimize"})

MISSING_POLICIES = frozenset({"null", "zero"})


@dataclass(frozen=True)
class Window:
    """How a measure reads a series that summing rows would get wrong.

    - order names the column a series runs along, a timestamp or a date. A
      range window may name several, one axis at its different grains, and
      the query accumulates down whichever of them it grouped by
    - partition names the columns one series is identified by. semiadditive
      collapses each series to its first or last sample before the measure
      aggregates, which is the only safe read of a running total
    - range="cumulative" turns the grouped result into a running total down
      the ordered dimension, which then has to be one of the group by names
    """

    order: str | tuple[str, ...]
    partition: tuple[str, ...] = ()
    semiadditive: str = ""
    range: str = ""

    def __post_init__(self) -> None:
        """Reject an unknown reduction, or a semiadditive window with no single series to collapse."""
        if self.semiadditive and self.semiadditive not in SEMIADDITIVE:
            known = ", ".join(sorted(SEMIADDITIVE))
            msg = f"unknown semiadditive {self.semiadditive!r}; available: {known}"
            raise ValueError(msg)

        if self.range and self.range not in RANGES:
            known = ", ".join(sorted(RANGES))
            msg = f"unknown range {self.range!r}; available: {known}"
            raise ValueError(msg)

        if not self.semiadditive and not self.range:
            msg = f"window on {self.order!r} does nothing, give it a semiadditive or a range"
            raise ValueError(msg)

        if not self.semiadditive:
            return

        if not self.partition:
            msg = f"semiadditive window on {self.order!r} needs the partition its series run within"
            raise ValueError(msg)

        if len(self.orders) != 1:
            msg = (
                f"semiadditive window orders by {list(self.orders)}, which has to be the "
                "one column the samples run along"
            )
            raise ValueError(msg)

    @property
    def orders(self) -> tuple[str, ...]:
        """The ordered columns, however many grains the axis was declared at."""
        return (self.order,) if isinstance(self.order, str) else tuple(self.order)

    @property
    def note(self) -> str:
        """The accumulation as one tag for the view dictionary.

        - the semiadditive collapse is left out because it covers every
          measure of the view, so the dictionary says it once instead
        """
        return f"[{self.range} by {' or '.join(self.orders)}]" if self.range else ""


@dataclass(frozen=True)
class Measure:
    """An aggregate expression that stays correct at any grouping.

    - write rates with try_divide() over two aggregates, never as the mean
      of a per-row rate, or the number stops recomposing
    - unit says what the number means, the one thing a comment cannot be
      read for. It never scales, rounds, or formats anything. format does
      all three, and defaults to whatever the unit implies
    - expr can be a callable taking the other measures by name, so a rate
      divides two named measures instead of respelling both of them
    - window covers what plain aggregation gets wrong: a running total that
      has to be read at its last sample, or a result that has to accumulate
    - direction says which way is good, which a gap is meaningless without.
      It describes the measure, never the delta, so turning a sign into good
      or bad news is left to whatever prints it
    - missing says what an absent group contributes in compare. Counts and
      sums use "zero"; rates, means, medians, extrema, and windowed values
      keep the safe "null" default
    """

    expr: pl.Expr | Callable[[Mapping[str, pl.Expr]], pl.Expr]
    unit: str
    comment: str = ""
    display_name: str = ""
    synonyms: tuple[str, ...] = ()
    format: Format | None = None
    window: Window | None = None
    direction: str = ""
    missing: Literal["null", "zero"] = "null"

    def __post_init__(self) -> None:
        """Reject a unit or a direction outside the known vocabulary."""
        if self.unit not in UNITS:
            known = ", ".join(sorted(UNITS))
            msg = f"unknown unit {self.unit!r}; available: {known}"
            raise ValueError(msg)

        if self.direction and self.direction not in DIRECTIONS:
            known = ", ".join(sorted(DIRECTIONS))
            msg = f"unknown direction {self.direction!r}; available: {known}"
            raise ValueError(msg)

        if self.missing not in MISSING_POLICIES:
            known = ", ".join(sorted(MISSING_POLICIES))
            msg = f"unknown missing policy {self.missing!r}; available: {known}"
            raise ValueError(msg)

    @property
    def display_format(self) -> Format:
        """The declared format, or the one the unit implies."""
        return _UNIT_FORMATS[self.unit] if self.format is None else self.format


class _Siblings(Mapping[str, pl.Expr]):
    """The other measures of one source, resolved by name the first time each is read."""

    def __init__(self, names: Sequence[str], resolve: Callable[[str], pl.Expr]) -> None:
        self._names = tuple(names)
        self._resolve = resolve

    def __getitem__(self, name: str) -> pl.Expr:
        return self._resolve(name)

    def __iter__(self) -> Iterator[str]:
        return iter(self._names)

    def __len__(self) -> int:
        return len(self._names)


def resolve_measures(measures: Mapping[str, Measure]) -> dict[str, Measure]:
    """Substitute sibling expressions into the measures written from other measures.

    - already resolved measures pass straight through, so running this twice
      over the same mapping changes nothing
    """
    resolved: dict[str, pl.Expr] = {}
    resolving: list[str] = []

    def expression(name: str) -> pl.Expr:
        if name in resolved:
            return resolved[name]

        if name in resolving:
            trail = " -> ".join([*resolving, name])
            msg = f"measure {resolving[0]!r} composes itself: {trail}"
            raise ValueError(msg)

        if name not in measures:
            known = ", ".join(sorted(measures))
            msg = f"composed measure reads unknown measure {name!r}; available: {known}"
            raise ValueError(msg)

        measure = measures[name]

        if isinstance(measure.expr, pl.Expr):
            resolved[name] = measure.expr

            return measure.expr

        resolving.append(name)
        built = measure.expr(_Siblings(tuple(measures), expression))
        resolving.pop()

        if not isinstance(built, pl.Expr):
            msg = f"measure {name!r} composed to {type(built).__name__}, not an expression"
            raise TypeError(msg)

        resolved[name] = built

        return built

    return {name: replace(measure, expr=expression(name)) for name, measure in measures.items()}


def _aggregate(measure: Measure) -> pl.Expr:
    """Read the resolved expression off a measure, insisting composition already ran."""
    if isinstance(measure.expr, pl.Expr):
        return measure.expr

    msg = "measure is still composed, resolve_measures did not run over it"
    raise TypeError(msg)


def _field(entries: Mapping[str, Any], name: str, owner: str, kind: str) -> tuple[str, Any]:
    """Look up one dimension or measure by its declared name or by a synonym."""
    if name in entries:
        return name, entries[name]

    for declared, spec in entries.items():
        if name in spec.synonyms:
            return declared, spec

    known = ", ".join(sorted(entries))
    msg = f"{owner} has no {kind} {name!r}; available: {known}"
    raise ValueError(msg)


def check_synonyms(entries: Mapping[str, Any], owner: str, kind: str) -> None:
    """Reject a synonym that shadows a declared name or that two entries both claim."""
    claimed: dict[str, str] = {}

    for declared, spec in entries.items():
        for synonym in spec.synonyms:
            if synonym in entries:
                msg = (
                    f"{owner}: {kind} {declared!r} claims the synonym {synonym!r}, already a {kind}"
                )
                raise ValueError(msg)

            if synonym in claimed:
                msg = (
                    f"{owner}: {kind}s {claimed[synonym]!r} and {declared!r} both claim "
                    f"the synonym {synonym!r}"
                )
                raise ValueError(msg)

            claimed[synonym] = declared


def collapsing_window(measures: Mapping[str, Measure]) -> Window | None:
    """The semiadditive window a set of measures shares, or None when none of them has one."""
    windows = {
        measure.window
        for measure in measures.values()
        if measure.window is not None and measure.window.semiadditive
    }

    return windows.pop() if windows else None


def check_windows(measures: Mapping[str, Measure], owner: str) -> None:
    """Reject measures that would disagree about which rows the query even sees.

    - a semiadditive window collapses the whole frame to one row per series,
      so a measure that did not ask for it would silently start counting
      samples instead of rows. Every measure on the view declares the same
      window or none of them does
    """
    windows = {
        measure.window
        for measure in measures.values()
        if measure.window is not None and measure.window.semiadditive
    }

    if not windows:
        return

    if len(windows) > 1:
        msg = f"{owner}: measures declare {len(windows)} different semiadditive windows, pick one"
        raise ValueError(msg)

    window = next(iter(windows))
    different = sorted(
        name
        for name, measure in measures.items()
        if measure.window is not None and measure.window != window
    )

    if different:
        msg = (
            f"{owner}: measures {different} declare a different window while others are "
            "semiadditive. The collapse applies to the whole query, so every measure has "
            "to declare the same window."
        )
        raise ValueError(msg)

    plain = sorted(name for name, measure in measures.items() if measure.window is None)

    if plain:
        msg = (
            f"{owner}: measures {plain} have no window while others are semiadditive. "
            "The collapse applies to the whole query, so every measure has to declare it."
        )
        raise ValueError(msg)


CARDINALITIES = frozenset({"many_to_one", "one_to_one"})

_POLARS_VALIDATE: dict[str, Literal["m:1", "1:1"]] = {"many_to_one": "m:1", "one_to_one": "1:1"}


@dataclass(frozen=True)
class Join:
    """A lookup table a view enriches its rows with, reached through its alias.

    - always a left join with a validated cardinality, so it can add columns
      but can never add, drop, or duplicate a source row. An inner or semi
      join would change the row set, which makes skipping it unsafe
    - every column it carries lands as "alias.column", so which joins a query
      needs falls out of the aliases its expressions name, with no
      hand-maintained list to go stale
    - using names the columns both sides share, on takes one equality (or a
      sequence of them) between a source column and an alias.column
    - keys must already be on the source, chained joins are not supported
    """

    table: str
    name: str = ""
    using: str | Sequence[str] | None = None
    on: pl.Expr | Sequence[pl.Expr] | None = None
    cardinality: str = "many_to_one"
    comment: str = ""

    def __post_init__(self) -> None:
        """Reject a join without exactly one key form, or with an unknown cardinality."""
        if (self.using is None) == (self.on is None):
            msg = f"join on {self.table!r} needs exactly one of using= or on="
            raise ValueError(msg)

        if self.cardinality not in CARDINALITIES:
            known = ", ".join(sorted(CARDINALITIES))
            msg = (
                f"join on {self.table!r} has unknown cardinality "
                f"{self.cardinality!r}; available: {known}"
            )
            raise ValueError(msg)

    @property
    def alias(self) -> str:
        """The name every column this join carries is prefixed with."""
        return self.name or self.table

    @property
    def keys(self) -> tuple[str, ...]:
        """The shared key columns of a using join."""
        if self.using is None:
            return ()

        return (self.using,) if isinstance(self.using, str) else tuple(self.using)

    @property
    def predicates(self) -> tuple[pl.Expr, ...]:
        """The equality expressions of an on join."""
        if self.on is None:
            return ()

        return (self.on,) if isinstance(self.on, pl.Expr) else tuple(self.on)

    @property
    def validate(self) -> Literal["m:1", "1:1"]:
        """The polars validate code for the declared cardinality."""
        return _POLARS_VALIDATE[self.cardinality]


@dataclass(frozen=True, kw_only=True)
class MetricView:
    """A source, the lookups it joins, and the dimensions and measures over them.

    - source is a table name, a callable returning a LazyFrame, or another
      MetricView, whose dimensions the child can then group and filter by
    - filter is the view level predicate, the rows this view never contains
    - name, grain, dimensions, and measures are filled in by the view
      decorator, so a registered factory returns only the parameterized half
    """

    source: str | Callable[[], pl.LazyFrame] | MetricView
    name: str = ""
    grain: tuple[str, ...] = ()
    dimensions: Mapping[str, Dimension] = field(default_factory=dict)
    measures: Mapping[str, Measure] = field(default_factory=dict)
    joins: tuple[Join, ...] = ()
    filter: pl.Expr | None = None

    def __post_init__(self) -> None:
        """Reject colliding join aliases and synonyms, and substitute composed measures."""
        aliases = [join.alias for join in self.joins]
        repeated = sorted({alias for alias in aliases if aliases.count(alias) > 1})

        if repeated:
            msg = f"{self.label}: joins share the alias {repeated}, give one of them a name"
            raise ValueError(msg)

        check_synonyms(self.dimensions, self.label, "dimension")
        check_synonyms(self.measures, self.label, "measure")
        check_windows(self.measures, self.label)
        object.__setattr__(self, "measures", resolve_measures(self.measures))

    @property
    def label(self) -> str:
        """The view name for error messages, or a placeholder while it is unnamed."""
        return self.name or "view"

    def dimension(self, name: str) -> Dimension:
        """Look up one dimension by its name or a synonym.

        - an unknown name raises with the valid ones listed
        """
        return _field(self.dimensions, name, self.label, "dimension")[1]

    def measure(self, name: str) -> Measure:
        """Look up one measure by its name or a synonym.

        - an unknown name raises with the valid ones listed
        """
        return _field(self.measures, name, self.label, "measure")[1]


class ViewFactory(Protocol):
    """A named function returning the parameterized half of a metric view."""

    __name__: str

    def __call__(self, *positional: Any, **arguments: Any) -> MetricView:
        """Bind the parameters and return the source, joins, and filter."""
        ...


def view_parameters(factory: ViewFactory) -> dict[str, inspect.Parameter]:
    """Read a view factory signature as the parameters the view takes.

    - parquet_dir is not one of them. Every other argument is a value that
      lands inside an expression, while parquet_dir picks which files the
      source reads, so it stays ambient and scan() resolves it
    - a parameter after a defaulted one must carry a default too, which
      Python enforces for positional parameters but not for keyword-only ones
    """
    name = factory.__name__
    parameters: dict[str, inspect.Parameter] = {}
    defaulted = None

    for key, parameter in inspect.signature(factory).parameters.items():
        if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            msg = f"view factory {name!r} cannot take {parameter}, parameters must be named"
            raise ValueError(msg)

        if key == "parquet_dir":
            continue

        if parameter.default is parameter.empty:
            if defaulted is not None:
                msg = (
                    f"view factory {name!r} takes required parameter {key!r} after "
                    f"{defaulted!r}, which has a default"
                )
                raise ValueError(msg)

        else:
            defaulted = key

        parameters[key] = parameter

    return parameters


def _unread_source() -> pl.LazyFrame:
    """Stand in for the source an lf= summary never reaches."""
    msg = "this view was summarized over a supplied frame and has no source of its own to read"
    raise TypeError(msg)


@dataclass(frozen=True, kw_only=True)
class ViewSpec:
    """A registered metric view: what it declares, and the factory that binds its parameters.

    - the declared half is readable without building anything, so a view with
      a required parameter still describes and still grain checks
    """

    name: str
    grain: tuple[str, ...]
    dimensions: Mapping[str, Dimension]
    measures: Mapping[str, Measure]
    factory: Callable[..., MetricView] = field(repr=False, compare=False, hash=False)
    parameters: Mapping[str, inspect.Parameter] = field(repr=False, compare=False, hash=False)

    def build(self, *positional: Any, **arguments: Any) -> MetricView:
        """Bind the parameters and fill the declared half into what the factory returned."""
        unknown = sorted(set(arguments) - set(self.parameters))

        if unknown:
            known = ", ".join(self.parameters) or "none"
            msg = f"{self.name} has no parameter {', '.join(unknown)}; available: {known}"
            raise ValueError(msg)

        built = self.factory(*positional, **arguments)

        if not isinstance(built, MetricView):
            msg = f"view factory {self.name!r} returned {type(built).__name__}, not a MetricView"
            raise TypeError(msg)

        return replace(
            built,
            name=self.name,
            grain=self.grain,
            dimensions=self.dimensions,
            measures=self.measures,
        )

    def dimension(self, name: str) -> Dimension:
        """Look up one dimension by its name or a synonym.

        - an unknown name raises with the valid ones listed
        """
        return _field(self.dimensions, name, self.name, "dimension")[1]

    def measure(self, name: str) -> Measure:
        """Look up one measure by its name or a synonym.

        - an unknown name raises with the valid ones listed
        """
        return _field(self.measures, name, self.name, "measure")[1]

    def declared(self) -> MetricView:
        """The declared half alone, for a caller supplying the rows instead of the source.

        - the parameters stay unbound, which is the point: a frame that is
          already built has answered whatever they would have decided
        """
        return MetricView(
            source=_unread_source,
            name=self.name,
            grain=self.grain,
            dimensions=self.dimensions,
            measures=self.measures,
        )


_VIEWS: dict[str, ViewSpec] = {}

_SPEC_BY_FACTORY: dict[Any, ViewSpec] = {}


def view(
    *,
    grain: Sequence[str],
    dimensions: Mapping[str, Dimension],
    measures: Mapping[str, Measure],
) -> Callable[[ViewFactory], Callable[..., MetricView]]:
    """Register a factory that binds a metric view over a source and its joins.

    - the factory returns the parameterized half, a MetricView carrying
      source, joins, and filter, and the declared half is added here
    - registering the wrapper means summarize can tell a view from any other
      callable without calling it to find out
    """
    if not grain:
        msg = "a metric view needs a non-empty grain"
        raise ValueError(msg)

    if not measures:
        msg = "a metric view needs at least one measure"
        raise ValueError(msg)

    def decorate(factory: ViewFactory) -> Callable[..., MetricView]:
        name = factory.__name__

        if name in _VIEWS:
            msg = f"view {name!r} is already registered"
            raise ValueError(msg)

        check_synonyms(dimensions, name, "dimension")
        check_synonyms(measures, name, "measure")
        check_windows(measures, name)

        spec = ViewSpec(
            name=name,
            grain=tuple(grain),
            dimensions=dict(dimensions),
            measures=resolve_measures(measures),
            factory=factory,
            parameters=view_parameters(factory),
        )
        _VIEWS[name] = spec

        @functools.wraps(factory)
        def build(*positional: Any, **arguments: Any) -> MetricView:
            return spec.build(*positional, **arguments)

        _SPEC_BY_FACTORY[build] = spec

        return build

    return decorate


def registered_views() -> tuple[ViewSpec, ...]:
    """Return every registered view in stable name order, without building any of them."""
    return tuple(_VIEWS[name] for name in sorted(_VIEWS))


def view_spec(source: Any) -> ViewSpec | None:
    """Return the registered view a source names, or None when it is not one.

    - takes a registered factory or its name, and never calls an unmarked
      function to find out what it returns
    """
    if isinstance(source, str):
        return _VIEWS.get(source)

    if callable(source):
        return _SPEC_BY_FACTORY.get(source)

    return None


def semantic_spec(source: str | Callable[..., Any]) -> ViewSpec:
    """Resolve a registered view from its factory or its name."""
    spec = view_spec(source)

    if spec is None:
        name = source if isinstance(source, str) else getattr(source, "__name__", str(source))
        known = ", ".join(sorted(_VIEWS))
        msg = f"{name!r} is not a metric view; registered views: {known}"
        raise ValueError(msg)

    return spec


def _reject_built_view_arguments(metric_view: MetricView, arguments: Mapping[str, Any]) -> None:
    """Reject arguments aimed at a view whose parameters are already bound."""
    if arguments:
        msg = (
            f"{metric_view.label} is already built and takes no arguments, "
            f"got: {', '.join(sorted(arguments))}"
        )
        raise ValueError(msg)


def resolve_view(source: Any, **arguments: Any) -> MetricView | None:
    """Build the view a source names, or return None when it is not one.

    - takes the view itself, a registered factory, or its name, and never
      calls an unmarked function to find out what it returns
    """
    if isinstance(source, MetricView):
        _reject_built_view_arguments(source, arguments)

        return source

    spec = view_spec(source)

    return None if spec is None else spec.build(**arguments)


def _naming_notes(spec: Dimension | Measure) -> list[str]:
    """The display name and synonyms of one field, as text for the dictionary."""
    notes = []

    if spec.display_name:
        notes.append(f"[{spec.display_name}]")

    if spec.synonyms:
        notes.append(f"(also {', '.join(spec.synonyms)})")

    return notes


def describe_views(name: str | None = None) -> str:
    """View dictionary as text, one view or all of them when name is None.

    - lists what summarize accepts, so the dimension and measure names do not
      have to be read out of the source
    - the arguments come first because one of them can decide what a measure
      counts, the way stat does on damage_source_games and compare_intervals
    """
    specs = registered_views()

    if name is not None:
        specs = (semantic_spec(name),)

    lines = []

    for spec in specs:
        grain, arguments = spec.grain, spec.parameters
        dimensions, measures = spec.dimensions, spec.measures
        collapse = collapsing_window(measures)
        headline = f"{spec.name}  one row per {', '.join(grain)}"

        if collapse is not None:
            headline += (
                f". Every measure reads the {collapse.semiadditive} sample of each "
                f"{', '.join(collapse.partition)} series, never the sum of the samples"
            )

        lines.append(headline)
        width = max(len(n) for n in (*arguments, *dimensions, *measures))

        lines.append("  arguments")

        for key, argument in arguments.items():
            default = (
                "required" if argument.default is argument.empty else f"= {argument.default!r}"
            )
            lines.append(f"    {key:<{width}}  {default}")

        lines.append("  group by")

        for key, dimension in dimensions.items():
            notes = [*_naming_notes(dimension)]

            if dimension.comment:
                notes.append(dimension.comment)

            if dimension.resolve is not None:
                notes.append("Takes a name and checks it.")

            lines.append(f"    {key:<{width}}  {' '.join(notes)}".rstrip())

        lines.append("  measures")

        for key, measure in measures.items():
            notes = [*_naming_notes(measure)]

            if measure.missing == "zero":
                notes.append("[zero if missing]")

            if measure.direction:
                notes.append(f"[{measure.direction}]")

            if measure.window is not None and measure.window.note:
                notes.append(measure.window.note)

            notes.append(measure.comment)
            lines.append(f"    {key:<{width}}  {measure.unit:<11} {' '.join(notes)}".rstrip())

        lines.append("")

    return "\n".join(lines).rstrip()


def _chosen_measures(
    measures: Mapping[str, Measure], requested: Sequence[str], owner: str
) -> list[tuple[str, Measure]]:
    """Resolve each requested measure to its declared name and spec, synonyms included."""
    return [_field(measures, asked, owner, "measure") for asked in requested]


def _named_aggregates(chosen: Sequence[tuple[str, Measure]]) -> list[pl.Expr]:
    """Alias each chosen measure under its declared name, so a synonym lands there too."""
    return [_aggregate(spec).alias(declared) for declared, spec in chosen]


def _collapse_series(lazy: pl.LazyFrame, window: Window) -> pl.LazyFrame:
    """Reduce every series to one sample, the only safe read of a running total."""
    ordered = pl.all().sort_by(window.orders[0])
    picked = ordered.last() if window.semiadditive == "last" else ordered.first()

    return lazy.group_by(list(window.partition)).agg(picked)


def _accumulate(
    result: pl.LazyFrame, chosen: Sequence[tuple[str, Measure]], group: Sequence[str], owner: str
) -> pl.LazyFrame:
    """Turn every cumulative measure into a running total down its ordered dimension."""
    running = [
        (name, spec.window)
        for name, spec in chosen
        if spec.window is not None and spec.window.range == "cumulative"
    ]

    if not running:
        return result

    for name, window in running:
        orders = () if window is None else window.orders
        order = next((key for key in orders if key in group), None)

        if order is None:
            wanted = " or ".join(orders) or "nothing"
            msg = f"{owner}: measure {name!r} accumulates by {wanted}, so group by it as well"
            raise ValueError(msg)

        others = [key for key in group if key != order]
        total = pl.col(name).cum_sum()
        result = result.sort([*others, order]).with_columns(
            (total.over(others) if others else total).alias(name)
        )

    return result.sort(list(group))


def _named_dimensions(
    dimensions: Mapping[str, Dimension], by: str | Sequence[str], owner: str
) -> tuple[list[str], list[pl.Expr]]:
    """Alias each requested dimension under its declared name, and return the group keys."""
    requested = [by] if isinstance(by, str) else list(by)
    group = []
    grouped = []

    for asked in requested:
        declared, spec = _field(dimensions, asked, owner, "dimension")
        group.append(declared)
        grouped.append(spec.expr.alias(declared))

    return group, grouped


def _referenced(expressions: Sequence[pl.Expr]) -> set[str]:
    """Every source column the given expressions read."""
    names: set[str] = set()

    for expression in expressions:
        names |= set(expression.meta.root_names())

    return names


def _filtered_dimensions(
    dimensions: Mapping[str, Dimension], predicates: Sequence[pl.Expr]
) -> dict[str, Dimension]:
    """The dimensions a filter names directly, which have to be columns before it runs.

    - only a raw expression lands here. A value filter is built from the
      expression the dimension declares, so it already reads source columns
    """
    return {name: dimensions[name] for name in _referenced(predicates) if name in dimensions}


def _callable_frame(metric_view: MetricView, source: Callable[[], pl.LazyFrame]) -> pl.LazyFrame:
    """Call a callable source and insist it stayed lazy."""
    frame = source()

    if not isinstance(frame, pl.LazyFrame):
        msg = (
            f"{metric_view.label}: source returned {type(frame).__name__}, not a LazyFrame. "
            "A source that collects internally stops the view filter from reaching the scan, "
            "with nothing to say so."
        )
        raise TypeError(msg)

    return frame


def view_columns(metric_view: MetricView, scan_table: Callable[[str], pl.LazyFrame]) -> set[str]:
    """Every column the view can expose, joined lookups included.

    - joins are read for their schema rather than pruned here, so a declared
      expression is checked against what the view could reach, not against
      what one query happened to pull in
    """
    source = metric_view.source

    if isinstance(source, MetricView):
        columns = view_columns(source, scan_table) | set(source.dimensions)

    elif isinstance(source, str):
        columns = set(scan_table(source).collect_schema().names())

    else:
        columns = set(_callable_frame(metric_view, source).collect_schema().names())

    for join in metric_view.joins:
        columns |= {
            f"{join.alias}.{name}" for name in scan_table(join.table).collect_schema().names()
        }

    return columns


def validate_view_columns(
    metric_view: MetricView, scan_table: Callable[[str], pl.LazyFrame]
) -> None:
    """Check every declared expression against the columns the view can expose.

    - runs over all the dimensions and measures, not only the ones a query
      asked for, so a typo in a measure nobody called still fails
    """
    available = view_columns(metric_view, scan_table)
    declared = [
        *((f"dimension {name!r}", spec.expr) for name, spec in metric_view.dimensions.items()),
        *((f"measure {name!r}", _aggregate(spec)) for name, spec in metric_view.measures.items()),
    ]

    if metric_view.filter is not None:
        declared.append(("filter", metric_view.filter))

    for label, expression in declared:
        unknown = sorted(set(expression.meta.root_names()) - available)

        if unknown:
            msg = (
                f"{metric_view.label}: {label} reads {unknown}, which the source "
                "and its joins do not have"
            )
            raise ValueError(msg)

    window = collapsing_window(metric_view.measures)

    if window is not None:
        unknown = sorted({*window.orders, *window.partition} - available)

        if unknown:
            msg = (
                f"{metric_view.label}: the semiadditive window orders and partitions by "
                f"{unknown}, which the source and its joins do not have"
            )
            raise ValueError(msg)


def _join_sides(
    metric_view: MetricView, join: Join, predicate: pl.Expr, columns: set[str]
) -> tuple[pl.Expr, pl.Expr]:
    """Split one join equality into its source side and its lookup side."""
    prefix = f"{join.alias}."
    sides = predicate.meta.pop()
    shape = (
        f"{metric_view.label}: join on {join.table!r} needs on= written as an equality "
        f"between a source column and a {prefix}column"
    )

    if len(sides) != 2:
        raise ValueError(shape)

    lookup = [side for side in sides if _reads_only(side, prefix)]
    source = [side for side in sides if not _reads_only(side, prefix)]

    if len(lookup) != 1 or len(source) != 1:
        raise ValueError(shape)

    missing = sorted(set(source[0].meta.root_names()) - columns)

    if missing:
        msg = (
            f"{metric_view.label}: join on {join.table!r} keys off {missing}, which the "
            "source does not have. A join key must come from the source, not from another join."
        )
        raise ValueError(msg)

    return source[0], lookup[0]


def _reads_only(expression: pl.Expr, prefix: str) -> bool:
    """Whether an expression reads columns and every one of them carries the prefix."""
    names = expression.meta.root_names()

    return bool(names) and all(name.startswith(prefix) for name in names)


def _apply_join(
    metric_view: MetricView,
    lazy: pl.LazyFrame,
    join: Join,
    scan_table: Callable[[str], pl.LazyFrame],
    columns: set[str],
) -> pl.LazyFrame:
    """Left join one lookup, prefixing every column it carries with the join alias."""
    right = scan_table(join.table)
    right = right.rename({name: f"{join.alias}.{name}" for name in right.collect_schema().names()})

    if join.using is not None:
        missing = sorted(set(join.keys) - columns)

        if missing:
            msg = (
                f"{metric_view.label}: join on {join.table!r} needs key columns {missing}, "
                "which the source does not have. A join key must come from the source, "
                "not from another join."
            )
            raise ValueError(msg)

        return lazy.join(
            right,
            left_on=list(join.keys),
            right_on=[f"{join.alias}.{key}" for key in join.keys],
            how="left",
            validate=join.validate,
        )

    pairs = [_join_sides(metric_view, join, predicate, columns) for predicate in join.predicates]

    return lazy.join(
        right,
        left_on=[source for source, _ in pairs],
        right_on=[lookup for _, lookup in pairs],
        how="left",
        validate=join.validate,
    )


def _source_frame(
    metric_view: MetricView, needed: set[str] | None, scan_table: Callable[[str], pl.LazyFrame]
) -> pl.LazyFrame:
    """Build the frame the view sits on, resolving the three source forms."""
    source = metric_view.source

    if isinstance(source, str):
        return scan_table(source)

    if not isinstance(source, MetricView):
        return _callable_frame(metric_view, source)

    if needed is None:
        return _view_frame(source, None, scan_table)

    inherited = [name for name in source.dimensions if name in needed]

    return _view_frame(source, [*inherited, *sorted(needed - set(source.dimensions))], scan_table)


def build_view_frame(
    metric_view: MetricView,
    needed: set[str] | None,
    scan_table: Callable[[str], pl.LazyFrame],
) -> pl.LazyFrame:
    """Scan the source and add only the joins a needed column names by alias.

    - a join contributes when a needed column is prefixed with its alias, so
      pruning follows the expressions instead of a hand kept list
    - None asks for everything the view has, joins included
    """
    validate_view_columns(metric_view, scan_table)

    if needed is not None and metric_view.filter is not None:
        needed = needed | _referenced([metric_view.filter])

    lazy = _source_frame(metric_view, needed, scan_table)
    columns = set(lazy.collect_schema().names())
    aliases = (
        {join.alias for join in metric_view.joins}
        if needed is None
        else {name.split(".", 1)[0] for name in needed if "." in name}
    )

    for join in metric_view.joins:
        if join.alias not in aliases:
            continue

        lazy = _apply_join(metric_view, lazy, join, scan_table, columns)

    return lazy.filter(metric_view.filter) if metric_view.filter is not None else lazy


def view_frame(
    metric_view: MetricView,
    columns: Sequence[str] | None = None,
    parquet_dir: str | Path | None = None,
    scan_table: Callable[[str], pl.LazyFrame] | None = None,
) -> pl.LazyFrame:
    """Build one view as a frame, with its dimensions carried as columns of their own.

    - columns names what the caller goes on to read, so a join nothing asks
      for stays out. It prunes and materializes, it does not project
    - None takes everything the view declares, joins included
    - parquet_dir stays ambient for the build, which a callable source needs
      as much as a table one does
    """
    from deadlock_matches.queries.core import parquet_dir_context, scan

    with parquet_dir_context(parquet_dir):
        return _view_frame(metric_view, columns, scan if scan_table is None else scan_table)


def _view_frame(
    metric_view: MetricView,
    columns: Sequence[str] | None,
    scan_table: Callable[[str], pl.LazyFrame],
) -> pl.LazyFrame:
    """Build a view as a frame against one already resolved scan function."""
    dimensions = metric_view.dimensions

    if columns is None:
        wanted = list(dimensions)
        needed = None

    else:
        wanted = [name for name in columns if name in dimensions]
        needed = _referenced([dimensions[name].expr for name in wanted])
        needed |= {name for name in columns if name not in dimensions}

    lazy = build_view_frame(metric_view, needed, scan_table)

    if not wanted:
        return lazy

    return lazy.with_columns(dimensions[name].expr.alias(name) for name in wanted)


def _summarize_view(
    metric_view: MetricView,
    by: str | Sequence[str],
    measures: Sequence[str],
    filters: Mapping[str, Any] | None,
    lf: pl.LazyFrame | None = None,
) -> pl.LazyFrame:
    """Group a view, pulling in only the joins the requested columns need."""
    from deadlock_matches.queries.core import scan

    if not measures:
        msg = f"summarize({metric_view.label}) needs at least one measure"
        raise ValueError(msg)

    predicates = [
        metric_view.dimension(name).filter_expr(value) for name, value in (filters or {}).items()
    ]
    chosen = _chosen_measures(metric_view.measures, measures, metric_view.label)
    aggregates = _named_aggregates(chosen)
    group, grouped = _named_dimensions(metric_view.dimensions, by, metric_view.label)
    window = collapsing_window(dict(chosen))
    filtered = _filtered_dimensions(metric_view.dimensions, predicates)
    needed = _referenced([*predicates, *aggregates, *grouped]) - set(filtered)
    needed |= _referenced([dimension.expr for dimension in filtered.values()])

    if window is not None:
        needed |= {*window.orders, *window.partition}

    if lf is not None:
        lazy = _lazy_rows(metric_view.label, lf)

    else:
        lazy = build_view_frame(metric_view, needed, scan)

    if filtered:
        lazy = lazy.with_columns(dimension.expr.alias(name) for name, dimension in filtered.items())

    if window is not None:
        lazy = _collapse_series(lazy, window)

    for predicate in predicates:
        lazy = lazy.filter(predicate)

    if not group:
        return lazy.select(aggregates)

    grouped_result = lazy.with_columns(grouped).group_by(group).agg(aggregates).sort(group)

    return _accumulate(grouped_result, chosen, group, metric_view.label)


def _lazy_rows(label: str, lf: Any) -> pl.LazyFrame:
    """Insist a supplied row set is lazy, so the whole summary stays one plan.

    - .lazy() on a collected frame costs nothing and reads no files again, so
      taking either kind would only hide which one a caller handed over
    """
    if isinstance(lf, pl.LazyFrame):
        return lf

    msg = (
        f"{label}: lf takes a LazyFrame, not a {type(lf).__name__}. "
        "Call .lazy() on a collected frame."
    )
    raise TypeError(msg)


def _reject_lf_arguments(label: str, lf: pl.LazyFrame | None, arguments: Mapping[str, Any]) -> None:
    """Reject a ready-made row set handed in alongside the arguments that would build one."""
    if lf is not None and arguments:
        names = ", ".join(sorted(arguments))
        msg = f"summarize({label}) cannot take lf with source arguments: {names}"
        raise ValueError(msg)


def summarize(
    source: str | Callable[..., Any] | MetricView,
    by: str | Sequence[str] = (),
    measures: Sequence[str] = (),
    filters: Mapping[str, Any] | None = None,
    lf: pl.LazyFrame | None = None,
    **source_kwargs: Any,
) -> pl.LazyFrame:
    """Group a metric view by its dimensions and aggregate its measures.

    - by and measures name entries the source declares, filters maps a
      dimension name to a value, a collection of values, or an expression
    - source_kwargs go to the view factory, so accounts, tz, days, since,
      and hero still work
    - parquet_dir goes to the view as the ambient export directory rather
      than as a parameter, because it picks files rather than filtering rows
    - lf supplies an already-built source frame instead, so a report can
      reuse one scan while keeping the declared dimensions and measures. It
      has to be lazy, which .lazy() makes a collected frame for free
    - always returns a lazy frame; collect only at the presentation boundary
    """
    from deadlock_matches.queries.core import parquet_dir_context

    if isinstance(source, MetricView):
        parquet_dir = source_kwargs.pop("parquet_dir", None)
        _reject_built_view_arguments(source, source_kwargs)

        with parquet_dir_context(parquet_dir):
            return _summarize_view(source, by, measures, filters, lf)

    spec = semantic_spec(source)
    parquet_dir = source_kwargs.pop("parquet_dir", None)
    _reject_lf_arguments(spec.name, lf, source_kwargs)

    if lf is not None:
        return _summarize_view(spec.declared(), by, measures, filters, lf)

    with parquet_dir_context(parquet_dir):
        return _summarize_view(spec.build(**source_kwargs), by, measures, filters, lf)


@dataclass(frozen=True)
class Scope:
    """One side of a comparison: the export it reads and the arguments it binds.

    - parquet_dir belongs here rather than among the arguments because it
      picks which files the source reads instead of filtering rows. The two
      sides of a real comparison read different exports, so a scope that was
      only a predicate could not express the tracked side at all
    - arguments go to the view factory, filters narrow the built view by
      dimension, and both are merged with whatever compare was given for
      both sides
    - lf supplies an already built source frame instead, and then the
      arguments have nothing left to decide
    """

    name: str
    parquet_dir: str | Path | None = None
    arguments: Mapping[str, Any] = field(default_factory=dict)
    filters: Mapping[str, Any] | None = None
    lf: pl.LazyFrame | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Reject an unnamed scope, a collected row set, or conflicting frame inputs."""
        if not self.name:
            msg = "a compare scope needs a name, it prefixes every column that side contributes"
            raise ValueError(msg)

        if self.lf is None:
            return

        _lazy_rows(f"scope {self.name!r}", self.lf)

        if self.parquet_dir is not None:
            msg = f"scope {self.name!r} supplies lf, so parquet_dir would be ignored"
            raise ValueError(msg)

        if self.arguments:
            names = ", ".join(sorted(self.arguments))
            msg = f"scope {self.name!r} supplies lf, so it cannot also take: {names}"
            raise ValueError(msg)


def view_fields(
    source: str | Callable[..., Any] | MetricView,
) -> tuple[str, Mapping[str, Dimension], Mapping[str, Measure]]:
    """Read what a view declares without binding the parameters of either side.

    - a comparison needs it before it builds anything, and so does whatever
      prints the result, which reads the formats and directions off here
    """
    if isinstance(source, MetricView):
        return source.label, source.dimensions, source.measures

    spec = semantic_spec(source)

    return spec.name, spec.dimensions, spec.measures


def view_measure(source: str | Callable[..., Any] | MetricView, name: str) -> Measure:
    """Look up one declared measure of a view by its name or a synonym.

    - what a report reads to print a number the way its measure says to,
      instead of respelling the scale and the decimals at the call site
    """
    owner, _, measures = view_fields(source)

    return _field(measures, name, owner, "measure")[1]


def _check_scopes(scopes: Sequence[Scope], owner: str) -> tuple[Scope, Scope]:
    """Insist on exactly two differently named sides."""
    if len(scopes) != 2:
        msg = f"compare({owner}) takes exactly two scopes, got {len(scopes)}"
        raise ValueError(msg)

    left, right = scopes

    if left.name == right.name:
        msg = f"compare({owner}): both scopes are named {left.name!r}, the columns would collide"
        raise ValueError(msg)

    for scope in scopes:
        if scope.name == "gap":
            msg = f"compare({owner}): 'gap' names the delta columns, pick another scope name"
            raise ValueError(msg)

    return left, right


def _scope_summary(
    source: str | Callable[..., Any] | MetricView,
    scope: Scope,
    by: str | Sequence[str],
    measures: Sequence[str],
    filters: Mapping[str, Any] | None,
    declared: Sequence[str],
) -> pl.LazyFrame:
    """Summarize one side and prefix its measure columns with the scope name."""
    owner, dimensions, _ = view_fields(source)
    merged: dict[str, pl.Expr] = {}

    for narrowed in (filters or {}, scope.filters or {}):
        for name, value in narrowed.items():
            dimension_name, dimension = _field(dimensions, name, owner, "dimension")
            predicate = dimension.filter_expr(value)
            merged[dimension_name] = (
                predicate if dimension_name not in merged else merged[dimension_name] & predicate
            )

    result = summarize(
        source,
        by,
        measures,
        merged or None,
        lf=scope.lf,
        parquet_dir=scope.parquet_dir,
        **scope.arguments,
    )

    return result.rename({name: f"{scope.name}_{name}" for name in declared})


def _signed(
    column: str,
    schema: Mapping[str, pl.DataType],
    *,
    missing: str,
) -> pl.Expr:
    """Read one side of a gap as a signed number, applying its missing-group policy.

    - counting measures come back unsigned, and an unsigned subtraction
      wraps instead of going negative, which is the whole point of a gap
    """
    read = pl.col(column)

    if missing == "zero":
        read = read.fill_null(0)

    return read.cast(pl.Int64) if schema[column].is_integer() else read


def compare(
    source: str | Callable[..., Any] | MetricView,
    scopes: Sequence[Scope],
    by: str | Sequence[str] = (),
    measures: Sequence[str] = (),
    filters: Mapping[str, Any] | None = None,
) -> pl.LazyFrame:
    """Summarize two row sets at one grain and carry the gap between them.

    - a delta across columns at the same grain is a measure, the way
      record_games.net is. A delta across row sets is not: the two sides live
      in different groups, and the pool gap at month grain is not derivable
      from the day by day gaps. So it is an operation on results instead
    - the gap always reads the first scope minus the second, which is the one
      thing five hand rolled compares had each decided separately
    - every group key either side has survives. A "zero" missing policy
      contributes zero to the gap; the default "null" policy leaves the gap
      null because an absent group has no rate, mean, median, or extremum
    - direction on a measure says which way is good, and turning that plus
      the sign into good or bad news belongs wherever the gap is printed
    """
    owner, dimensions, declared_measures = view_fields(source)
    left, right = _check_scopes(scopes, owner)

    if not measures:
        msg = f"compare({owner}) needs at least one measure"
        raise ValueError(msg)

    chosen = _chosen_measures(declared_measures, measures, owner)
    names = [declared for declared, _ in chosen]
    group, _ = _named_dimensions(dimensions, by, owner)
    sides = [_scope_summary(source, scope, by, measures, filters, names) for scope in (left, right)]

    if group:
        joined = sides[0].join(sides[1], on=group, how="full", coalesce=True)

    else:
        joined = sides[0].join(sides[1], how="cross")

    schema = joined.collect_schema()
    gaps = [
        (
            _signed(f"{left.name}_{name}", schema, missing=measure.missing)
            - _signed(f"{right.name}_{name}", schema, missing=measure.missing)
        ).alias(f"gap_{name}")
        for name, measure in chosen
    ]

    return joined.with_columns(gaps).sort(group) if group else joined.with_columns(gaps)


def validate_grain(source: str | Callable[..., Any], result: pl.DataFrame | pl.LazyFrame) -> None:
    """Check that a view result carries its grain columns and is unique on them."""
    spec = semantic_spec(source)
    frame = result.collect() if isinstance(result, pl.LazyFrame) else result
    missing = set(spec.grain) - set(frame.columns)

    if missing:
        msg = f"{spec.name}: result is missing grain columns {sorted(missing)}"
        raise AssertionError(msg)

    if frame.select(spec.grain).is_duplicated().any():
        msg = f"{spec.name}: result is not unique on grain {spec.grain}"
        raise AssertionError(msg)
