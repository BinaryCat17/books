"""Module 2: many books, truth, numbers.

A bench is a book directory that also has `truth/`. This package opens one
(`bench.Bench`), opens a run of a detector or a reader over it
(`bench.Run`), measures the run against the truth (`metrics`) and lays the
numbers side by side (`table`). It imports `processing` and `core`, never
the other way round: the measured path must not know how it is measured.
"""
