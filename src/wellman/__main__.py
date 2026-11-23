"""Execution entrypoint for `python -m wellman`."""

import sys

from wellman.cli import main


def _dispatch(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "sync-hosts":
        from wellman.host_agent_sync import main as sync_hosts_main

        return sync_hosts_main(args[1:])
    return main(args if argv is not None else None)


if __name__ == "__main__":
    sys.exit(_dispatch())
