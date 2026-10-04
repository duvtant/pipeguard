"""Add the new Call columns to core/models.py (shared file: David and Olise must ack the change).

New columns: calls.evaluation (ElevenLabs report card) and calls.ended_at (phone reported hang-up).
Safe to run twice. Run from the repo root:  python scripts/patch_models.py
"""
import re
from pathlib import Path

path = Path("core/models.py")
src = path.read_text(encoding="utf-8")

if "evaluation:" in src and "ended_at:" in src:
    raise SystemExit("core/models.py already has the new columns, nothing to do")

pattern = re.compile(r"^(    received_via: Optional\[str\] = None.*)$", re.M)
if len(pattern.findall(src)) != 1:
    raise SystemExit("could not find the single 'received_via' line in class Call: edit core/models.py by hand")

NEW = (
    "\n    # ElevenLabs report card, [{criteria_id, result, rationale}]. Null when the call has none.\n"
    "    evaluation: Optional[list] = Field(default=None, sa_column=Column(JSONB))\n"
    "    # Set when the phone page reports hang-up. The sweeper pulls the transcript if no webhook arrives.\n"
    "    ended_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))"
)
path.write_text(pattern.sub(lambda m: m.group(1) + NEW, src), encoding="utf-8")
print("patched core/models.py: calls.evaluation, calls.ended_at")
