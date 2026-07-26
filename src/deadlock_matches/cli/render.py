"""Print metric view results through the formats and directions their measures declare."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from deadlock_matches.queries.semantic import Format, view_measure

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from deadlock_matches.queries.semantic import Measure, MetricView


BLANK = "-"

GAP = "gap"

_READINGS = {"maximize": ("better", "worse"), "minimize": ("worse", "better")}


def reading(measure: Measure, gap: float | None) -> str:
    """Label a gap better or worse from the direction its measure declares.

    - a minimize measure reverses the sign, so fewer missed parries labels
      better while the number stays negative
    - a measure declaring no direction labels nothing
    """
    if not measure.direction or not gap:
        return ""

    return _READINGS[measure.direction][0 if gap > 0 else 1]


@dataclass(frozen=True)
class Key:
    """A text column holding a group key or a pair of counts printed as one.

    - a width of zero is filled in from the longest label the rows hold
    - labels swap a stored value for the name the report calls it
    """

    column: str
    heading: str = ""
    width: int = 0
    labels: Mapping[str, str] | None = None
    right: bool = False

    def text(self, row: Mapping[str, Any]) -> str:
        """Read the label one row prints in this column."""
        value = row.get(self.column)

        if value is None:
            return ""

        return str(self.labels.get(value, value) if self.labels else value)

    def cell(self, text: str) -> str:
        """Pad one label to the column width on the side it aligns to."""
        return text.rjust(self.width) if self.right else text.ljust(self.width)


@dataclass(frozen=True)
class Field:
    """A number column holding one measure on one side of a comparison.

    - side is the scope name a compare result prefixed the column with, or
      gap for the delta, and empty for a plain summarize result
    - format overrides what the measure declares, for a column that wants a
      different shape from the same number elsewhere
    """

    measure: str
    side: str = ""
    heading: str = ""
    width: int = 9
    format: Format | None = None

    @property
    def column(self) -> str:
        """The result column this field reads."""
        return f"{self.side}_{self.measure}" if self.side else self.measure

    @property
    def title(self) -> str:
        """The heading this column prints under."""
        return self.heading or self.measure

    @property
    def sign(self) -> bool:
        """Whether the column keeps a leading + on a positive number."""
        return self.side == GAP

    def cell(self, row: Mapping[str, Any], fmt: Format, blank: str) -> str:
        """Render one value and sign it when the column carries a delta."""
        return fmt.render(row.get(self.column), blank, sign=self.sign).rjust(self.width)


@dataclass(frozen=True)
class Metric:
    """A measure printed as a row of its own against both sides and the gap."""

    measure: str
    label: str = ""
    format: Format | None = None

    @property
    def title(self) -> str:
        """The label this row prints under."""
        return self.label or self.measure


def spread(
    measure: str,
    headings: Sequence[str],
    widths: Sequence[int],
    fmt: Format | None = None,
    sides: Sequence[str] = ("you", "them", GAP),
) -> list[Field]:
    """Lay one measure out as a column per side."""
    return [
        Field(measure, side, heading, width, fmt)
        for side, heading, width in zip(sides, headings, widths, strict=True)
    ]


def _formats(source: Any, columns: Sequence[Key | Field]) -> dict[str, Format]:
    """Resolve the format of every number column before any row renders."""
    return {
        column.column: (
            view_measure(source, column.measure).display_format
            if column.format is None
            else column.format
        )
        for column in columns
        if isinstance(column, Field)
    }


def _sized(columns: Sequence[Key | Field], rows: Sequence[Mapping[str, Any]]) -> list[Key | Field]:
    """Widen every key with no declared width to the longest label it holds."""
    return [
        replace(column, width=max((len(column.text(row)) for row in rows), default=0) + 2)
        if isinstance(column, Key) and not column.width
        else column
        for column in columns
    ]


def _line(
    row: Mapping[str, Any],
    columns: Sequence[Key | Field],
    formats: Mapping[str, Format],
    blank: str,
    indent: str,
) -> str:
    """Render one row across every column, labels and numbers alike."""
    return indent + "".join(
        column.cell(row, formats[column.column], blank)
        if isinstance(column, Field)
        else column.cell(column.text(row))
        for column in columns
    )


def headings(columns: Sequence[Key | Field], indent: str = "  ") -> str:
    """Build the header line with every column titled at its own width."""
    return indent + "".join(
        column.title.rjust(column.width)
        if isinstance(column, Field)
        else column.heading.rjust(column.width)
        if column.right
        else column.heading.ljust(column.width)
        for column in columns
    )


def table(
    source: str | Callable[..., Any] | MetricView,
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[Key | Field],
    indent: str = "  ",
) -> list[str]:
    """Build one line per result row over an ordered mix of label and number columns.

    - every number prints through the format its measure declares, so a
      proportion is a percent here and everywhere else without the caller
      scaling anything
    """
    sized = _sized(columns, rows)
    formats = _formats(source, sized)

    return [
        headings(sized, indent),
        *(_line(row, sized, formats, BLANK, indent) for row in rows),
    ]


def total_line(
    source: str | Callable[..., Any] | MetricView,
    total: Mapping[str, Any],
    columns: Sequence[Key | Field],
    rows: Sequence[Mapping[str, Any]] = (),
    label: str = "Total",
    blank: str = BLANK,
    indent: str = "  ",
) -> str:
    """Build the summing line that sits under a table on the same columns.

    - rows are the table it sits under, so a key sized to its labels lands
      at the same width in both
    - the first key carries the label, and a column the total leaves out
      prints blank rather than a number of its own
    """
    sized = _sized(columns, rows)
    formats = _formats(source, sized)
    labelled = next(i for i, column in enumerate(sized) if isinstance(column, Key))
    cells = []

    for i, column in enumerate(sized):
        if isinstance(column, Field):
            cells.append(column.cell(total, formats[column.column], blank))

        else:
            cells.append(column.cell(label if i == labelled else column.text(total)))

    return indent + "".join(cells)


def gap_lines(
    source: str | Callable[..., Any] | MetricView,
    row: Mapping[str, Any],
    metrics: Sequence[Metric],
    scopes: Sequence[str] = ("you", "them"),
    headers: Sequence[str] = ("Metric", "You", "Them", "Gap"),
    label_width: int = 22,
    width: int = 11,
    indent: str = "  ",
) -> list[str]:
    """Build one line per measure of a one-row comparison with both sides and the gap.

    - the trailing word labels the gap from the direction the measure
      declares, which is what tells a smaller number from a worse one
    - a measure neither side recorded prints nothing at all
    """
    label, *titles = headers
    lines = [indent + label.ljust(label_width) + "".join(t.rjust(width) for t in titles)]

    for metric in metrics:
        measure = view_measure(source, metric.measure)
        fmt = measure.display_format if metric.format is None else metric.format
        sides = (*scopes, GAP)
        values = [row.get(f"{side}_{metric.measure}") for side in sides]

        if all(value is None for value in values[:-1]):
            continue

        cells = "".join(
            fmt.render(value, BLANK, sign=side == GAP).rjust(width)
            for side, value in zip(sides, values, strict=True)
        )
        note = reading(measure, values[-1])
        lines.append((indent + metric.title.ljust(label_width) + cells + f"  {note}").rstrip())

    return lines
