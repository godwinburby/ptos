import datetime as dt
import random
import time

import ptos


def _ref_parse_line(line):
    """The pre-fast-path behaviour: strict v2, then v1 fallback."""
    line = line.rstrip("\r\n")
    try:
        return ptos._parse_v2(line)
    except ValueError:
        return ptos._parse_v1(line)


def _outcome(f, line):
    try:
        return ("ok", f(line))
    except Exception as e:
        return ("err", type(e).__name__)


_ATOMS = [
    "type=expense", "a=1", 'b="x y"', 'c="q\\"q"', "d=\\x", "e=", "=v", "k",
    "|", "note=hi", 'note="a b"', "tag=t", "tag=u", 'x="un', 'y="a"b',
    'z=a"b', "\u00a0", "\x0b", "\t", "  ", "u=\u00e9\u65e5", "w=a=b", "p=a|b",
    "type=other", "\x1c",
]

_EXOTIC = [
    "2026-03-11 type=x",
    "2026-3-11 type=x",
    "2026-02-30 type=x a=1",
    "2026-03-11 type=expense note=\"Team lunch\"",
    '2026-03-14 type=income source=salary amount=4500 note="March salary, including bonus"',
    '2026-03-13 type=note title="Meeting with Dr. Mehta" category=work',
    "2026-03-12 type=expense amount=40 tag=auto tag=bus note=commute",
    "2026-03-11  type=x  a=1",
    "2026-03-11\ttype=x\ta=1",
    "2026-03-11 type=x a=\"\"",
    "2026-03-11 type=x a=",
    "2026-03-11 type=x =v",
    "2026-03-11 type=x a=\"unterminated",
    "2026-03-11 type=x a=\"bad\\escape\"",
    "2026-03-11 amount=1 type=x",
    "2026-03-11 type=x note=a note=b",
    "2026-03-11 type=x a=\"one\" b=two",
    '2026-03-11 type=x a="one"b=two',
    "2026-10-08 type=purchase amount=215 note=\"1 chicken roll, 4 chicken samosa , 1 burger and 1 bread pocket\"",
    "2026-10-07 type=expense amount=27 tag=metro tag=thykoodam",
    "2026-03-11 type=x tag=",
    "2026-03-11 type=x a=\"a\\nb\"",
    "type=x",
    "",
    "   ",
    "2026-03-11 | legacy note",
    "2026-03-11 type=x amount=5 | legacy note",
    "|",
    "2026-03-11 type=x a=b=c",
]


def _fuzz_lines(n, seed=9):
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        parts = [rng.choice(_ATOMS) for _ in range(rng.randint(0, 7))]
        sep = rng.choice([" ", " ", " ", "  ", "\t", "\u00a0", "\x0b"])
        out.append("2026-03-11" + sep + sep.join(parts))
    return out


def _v1_corpus(n=2000):
    lines = []
    for i in range(n):
        d = dt.date(2026, 1, 1) + dt.timedelta(days=i % 365)
        lines.append(
            "%s type=expense category=food amount=%d tag=lunch | legacy note %d"
            % (d.isoformat(), i % 500, i))
    return lines


def _v2_corpus(n=2000):
    lines = []
    for i in range(n):
        d = dt.date(2026, 1, 1) + dt.timedelta(days=i % 365)
        lines.append(ptos.build_record_line(
            d.isoformat(),
            {"type": "expense", "category": "food", "amount": str(i % 500),
             "tag": ["lunch"]},
            "note %d" % i))
    return lines


def _best(f, n=7):
    ts = []
    for _ in range(n):
        t = time.perf_counter()
        f()
        ts.append(time.perf_counter() - t)
    return min(ts)


class TestFuzzEquivalence:
    def test_generated_lines_match_reference(self):
        lines = _fuzz_lines(5000) + _EXOTIC
        mismatches = []
        for line in lines:
            a = _outcome(ptos.parse_line, line)
            b = _outcome(_ref_parse_line, line)
            if a != b:
                mismatches.append((line, a, b))
        assert mismatches == [], f"{len(mismatches)} mismatches, first: {mismatches[:3]}"

    def test_exotic_cases_match_reference(self):
        for line in _EXOTIC:
            assert (_outcome(ptos.parse_line, line)
                    == _outcome(_ref_parse_line, line)), repr(line)

    def test_fast_path_handles_common_v2_directly(self):
        line = "2026-03-12 type=expense amount=40 tag=auto tag=bus note=commute"
        assert ptos._parse_v2_fast(line) == ptos._parse_v2(line)
        assert ptos._parse_v2_fast("2026-03-11 type=x | legacy") is None
        assert ptos._parse_v2_fast("2026-03-11 type=x amount=5 | legacy") is None


class TestBenchmarkGuard:
    def _ratio(self, corpus):
        old = _best(lambda: [_ref_parse_line(l) for l in corpus])
        new = _best(lambda: [ptos.parse_line(l) for l in corpus])
        return new / old, new, old

    def test_v2_fast_path_not_slower_than_strict_first(self):
        ratio, new, old = self._ratio(_v2_corpus())
        assert ratio <= 1.5, (
            f"v2 parse {new*1e3:.1f}ms vs strict-first {old*1e3:.1f}ms (ratio {ratio:.2f})")

    def test_v1_path_not_slower_than_strict_first(self):
        ratio, new, old = self._ratio(_v1_corpus())
        assert ratio <= 1.5, (
            f"v1 parse {new*1e3:.1f}ms vs strict-first {old*1e3:.1f}ms (ratio {ratio:.2f})")


class TestEndToEndScan:
    def test_scan_reads_mixed_corpus(self):
        path = ptos.os.path.join(ptos.RECORDS_DIR, "2026.log")
        lines = _v2_corpus(100) + _v1_corpus(100)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        results, _total, parsed = ptos.scan_records(
            dt.date(2026, 1, 1), dt.date(2026, 12, 31), [], None,
            include_demo=True, return_parsed=True)
        assert len(results) == 200
        assert len(parsed) == 200
        assert all(r[1].get("type") == "expense" for r in parsed)
