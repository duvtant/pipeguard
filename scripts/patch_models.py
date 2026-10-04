"""Edit core/models.py (shared file: David and Olise must ack the change). Safe to run twice.

1. calls.evaluation and calls.ended_at (post-call webhook).
2. Database defaults for plan_items.crew and quality_flags.detail. Olise's engine inserts into those tables
   without those two columns, and a NOT NULL column with only a Python-side default rejects the insert.

Run from the repo root:  python scripts/patch_models.py
"""
import re
from pathlib import Path

path = Path("core/models.py")
src = path.read_text(encoding="utf-8")
done = []

# 1. New Call columns
if "evaluation:" not in src or "ended_at:" not in src:
    pattern = re.compile(r"^(    received_via: Optional\[str\] = None.*)$", re.M)
    if len(pattern.findall(src)) != 1:
        raise SystemExit("could not find the single 'received_via' line in class Call: edit core/models.py by hand")
    NEW = (
        "\n    # ElevenLabs report card, [{criteria_id, result, rationale}]. Null when the call has none.\n"
        "    evaluation: Optional[list] = Field(default=None, sa_column=Column(JSONB))\n"
        "    # Set when the phone page reports hang-up. The sweeper pulls the transcript if no webhook arrives.\n"
        "    ended_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))"
    )
    src = pattern.sub(lambda m: m.group(1) + NEW, src)
    done.append("calls.evaluation, calls.ended_at")


def add_default(src: str, cls: str, old_field: str, new_field: str) -> str | None:
    """Replace the first `old_field` line inside class `cls`. Returns None if it cannot be found."""
    m = re.search(rf"(class {cls}\(SQLModel, table=True\):.*?\n)(    {re.escape(old_field)}[^\n]*)", src, re.S)
    if not m:
        return None
    return src[:m.start(2)] + new_field + src[m.end(2):]


# 2. Database defaults for columns the engine's raw inserts leave out
if 'sa_column_kwargs={"server_default": "0"}' not in src:
    out = add_default(src, "PlanItem", "crew: int = 0",
                      '    crew: int = Field(default=0, sa_column_kwargs={"server_default": "0"})  # 0-based crew slot')
    if out is None:
        raise SystemExit("could not find 'crew: int = 0' in class PlanItem: edit core/models.py by hand")
    src = out
    done.append("plan_items.crew default")
if "sa_column_kwargs={\"server_default\": \"\"}" not in src:
    out = add_default(src, "QualityFlag", 'detail: str = ""',
                      '    detail: str = Field(default="", sa_column_kwargs={"server_default": ""})  # note from the quality check')
    if out is None:
        raise SystemExit("could not find 'detail: str = \"\"' in class QualityFlag: edit core/models.py by hand")
    src = out
    done.append("quality_flags.detail default")

if done:
    path.write_text(src, encoding="utf-8")
    print("patched core/models.py:", ", ".join(done))
else:
    print("core/models.py already has everything, nothing to do")
