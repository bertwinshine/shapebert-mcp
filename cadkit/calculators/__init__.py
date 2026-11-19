"""Engineering calculators matching the formulas in knowledge/domains/*.md.

Results are plain dicts with pass/fail ``checks`` so the assistant never does the
arithmetic itself.
"""

from . import boat, fasteners, flanges, gears, shafts, sheet_metal, weldments

__all__ = ["boat", "fasteners", "flanges", "gears", "shafts", "sheet_metal", "weldments"]
