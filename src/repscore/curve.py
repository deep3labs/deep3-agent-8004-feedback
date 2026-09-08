from collections import Counter
from collections.abc import Iterable
from fractions import Fraction


def decode(value: int, decimals: int) -> Fraction:
    return Fraction(int(value), 10 ** int(decimals))


def curve(values: list[Fraction]) -> list[Fraction]:
    n = len(values)
    if n == 0:
        return []
    order = sorted(range(n), key=values.__getitem__)
    avg_rank = [Fraction(0)] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        rank = Fraction(i + j + 2, 2)                  # (below + below-or-equal + 1) / 2
        for k in range(i, j + 1):
            avg_rank[order[k]] = rank
        i = j + 1
    return [Fraction(100) * (r - Fraction(1, 2)) / n for r in avg_rank]


def disagreement(values: list[Fraction]) -> Fraction:
    n = len(values)
    if n < 2:
        return Fraction(0)
    agree = sum(c * (c - 1) for c in Counter(values).values())
    total = n * (n - 1)
    return Fraction(total - agree, total)


def weighted_mean(pairs: Iterable[tuple[Fraction, Fraction]]) -> Fraction:
    pairs = list(pairs)
    wsum = sum((w for w, _ in pairs), Fraction(0))
    if wsum == 0:
        return mean([v for _, v in pairs]) if pairs else Fraction(0)
    return sum((w * v for w, v in pairs), Fraction(0)) / wsum


def mean(values: list[Fraction]) -> Fraction:
    return sum(values, Fraction(0)) / len(values)


def to_2dp(frac: Fraction) -> str:
    hundredths = _round_half_even(frac * 100)
    sign = "-" if hundredths < 0 else ""
    h = abs(hundredths)
    return f"{sign}{h // 100}.{h % 100:02d}"


def _round_half_even(frac: Fraction) -> int:
    floor = frac.numerator // frac.denominator
    rem = frac - floor
    half = Fraction(1, 2)
    if rem < half:
        return floor
    if rem > half:
        return floor + 1
    return floor if floor % 2 == 0 else floor + 1
