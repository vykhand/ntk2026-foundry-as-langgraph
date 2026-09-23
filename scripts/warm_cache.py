"""Fill the notebooks' offline cache off the stage clock.

    uv run warm-cache                 # every key it knows how to fill
    uv run warm-cache --key act2-versions

`notebooks/cache/*.json` is what every notebook falls back to when the network is slow or gone
(`NTK_DEMO_OFFLINE=1`). The notebooks fill it themselves whenever a live call succeeds — but they
call with a **short** timeout on purpose, because a stage demo cannot afford a cell that hangs, and
a cold `DefaultAzureCredential` alone takes longer than that. The result is a cache that quietly
stays a version or two behind: the Act 2 table showed v6 for two deploys after v6.

So: same code path, same cache file, no stage clock. Run this after every `azd deploy`, and after
a programme refresh, before you rehearse.

Only keys whose live call is read-only and cheap live here. `act1`, `act3-*` and `act4-invoke` are
model calls — they refresh by running the notebook (or the recorder) with the network up, which is
also the only way to be sure the cached answer is one the agent would really give today.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "notebooks"))

import _ntk as ntk  # noqa: E402  - needs notebooks/ on the path first

from scripts.rollback import version_payload  # noqa: E402

# key → (what it is, how to fetch it, how long to allow)
WARMERS = {
    "act2-versions": ("the deployed agent's immutable version list", version_payload, 120.0),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fill the notebooks offline cache off the stage clock")
    parser.add_argument("--key", action="append", default=None,
                        help="only this cache key (repeatable)")
    args = parser.parse_args(argv)

    if ntk.OFFLINE:
        print("NTK_DEMO_OFFLINE is set — unset it, or this refreshes nothing")
        return 2

    keys = args.key or list(WARMERS)
    unknown = [k for k in keys if k not in WARMERS]
    if unknown:
        print(f"unknown key(s): {unknown} — choose from {sorted(WARMERS)}")
        return 2

    failed = False
    for key in keys:
        what, fetch, timeout = WARMERS[key]
        payload = ntk.cached(key, fetch, timeout=timeout)
        path = ntk.cache_path(key).relative_to(ROOT)
        if "error" in payload:
            print(f"  ! {key}: {payload['error']}")
            failed = True
        elif payload.get("_stale"):
            print(f"  ! {key}: still stale — {payload.get('_note', '')}")
            failed = True
        else:
            extra = ""
            if key == "act2-versions":
                extra = f" · latest v{payload.get('latest_version', '?')}"
            print(f"  ✔ {key}: {what}{extra} → {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
