"""Read the public annual.csv and emit the fixed-1968 window sensitivity CSV."""

import argparse
import csv
import sys
from decimal import Decimal, DecimalException, localcontext
from fractions import Fraction
from pathlib import Path


PIVOT = 1968
MAX_WIDTH = 15
QUERIES = ("Robert Merton", "Harriet Zuckerman")
REQUIRED_COLUMNS = {"corpus", "year", "query", "ngram_order", "status", "fraction"}
METRICS = (
    "merton_per_billion",
    "zuckerman_per_billion",
    "signed_gap_per_billion",
    "absolute_gap_per_billion",
    "ratio",
)


def read_annual(path):
    values = {query: {} for query in QUERIES}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = csv.DictReader(stream)
        if not REQUIRED_COLUMNS <= set(rows.fieldnames or ()):
            raise ValueError("annual.csv is missing required columns")
        for row in rows:
            query = row["query"]
            if row["corpus"] != "english_current" or query not in values:
                continue
            year = int(row["year"])
            if year == PIVOT or abs(year - PIVOT) > MAX_WIDTH:
                continue
            location = f"{query}, {year}"
            if row["ngram_order"] != "2":
                raise ValueError(f"expected bigram order for {location}")
            if year in values[query]:
                raise ValueError(f"duplicate annual observation for {location}")
            values[query][year] = None
            status = row["status"]
            if status not in {"returned_positive", "returned_zero"} or not row["fraction"]:
                continue
            fraction = Decimal(row["fraction"])
            if not fraction.is_finite() or not 0 <= fraction <= 1:
                raise ValueError(f"invalid fraction for {location}")
            if (fraction == 0) != (status == "returned_zero"):
                raise ValueError(f"fraction disagrees with status for {location}")
            values[query][year] = Fraction(fraction)
    return values


def annual_mean(series, years):
    annual = [series.get(year) for year in years]
    if None in annual:
        return None
    return sum(annual) * 10**9 / len(annual)


def metrics(values, years):
    merton, zuckerman = (annual_mean(values[query], years) for query in QUERIES)
    if merton is None or zuckerman is None:
        return merton, zuckerman, None, None, None
    gap = merton - zuckerman
    ratio = merton / zuckerman if zuckerman > 0 else None
    return merton, zuckerman, gap, abs(gap), ratio


def decimal_cell(value):
    if value is None:
        return ""
    with localcontext() as context:
        context.prec = 30
        return str(Decimal(value.numerator) / Decimal(value.denominator))


def write_sweep(values, stream):
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow([
        "width_years", "pre_start", "pre_end", "post_start", "post_end",
        *(f"{prefix}_{metric}" for prefix in ("pre", "post", "change") for metric in METRICS),
        "joint_pattern",
    ])
    for width in range(1, MAX_WIDTH + 1):
        pre = metrics(values, range(PIVOT - width, PIVOT))
        post = metrics(values, range(PIVOT + 1, PIVOT + width + 1))
        changes = [
            after - before if before is not None and after is not None else None
            for before, after in zip(pre, post)
        ]
        gap_change, ratio_change = changes[-2:]
        if gap_change is None or ratio_change is None:
            joint = "undefined"
        else:
            joint = "retained" if gap_change > 0 and ratio_change < 0 else "failed"
        writer.writerow([
            width, PIVOT - width, PIVOT - 1, PIVOT + 1, PIVOT + width,
            *(decimal_cell(value) for value in (*pre, *post, *changes)),
            joint,
        ])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("annual_csv", type=Path, help="path to the public annual.csv")
    args = parser.parse_args()
    try:
        values = read_annual(args.annual_csv)
    except (OSError, ValueError, TypeError, csv.Error, DecimalException) as error:
        parser.exit(2, f"{parser.prog}: {error}\n")
    sys.stdout.reconfigure(newline="")
    write_sweep(values, sys.stdout)


if __name__ == "__main__":
    main()
