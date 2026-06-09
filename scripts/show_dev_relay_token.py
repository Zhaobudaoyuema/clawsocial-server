"""Print local machine GUID and dev relay token (for registering new dev PCs)."""
from __future__ import annotations

from app.deid.worker.dev_machine_token import (
    ALLOWED_DEV_MACHINE_GUIDS,
    describe_local_dev_machine,
    get_local_dev_relay_token,
    read_local_machine_guid,
    token_from_machine_guid,
)


def main() -> None:
    info = describe_local_dev_machine()
    guid = info["machine_guid"]
    print("=== DEID dev relay (machine token) ===")
    print(f"platform:     {info['platform']}")
    print(f"machine_guid: {guid or '(unknown)'}")
    if guid:
        print(f"token:        {token_from_machine_guid(guid)}")
        print(f"registered:   {info['registered']}")
        if not info["registered"]:
            print()
            print("To enable relay from this PC, add to ALLOWED_DEV_MACHINE_GUIDS in")
            print("app/deid/worker/dev_machine_token.py:")
            print(f'    "{guid.lower()}",')
    print(f"relay_url:    {info['relay_url'] or '(set DEID_WORKER_RELAY_URL)'}")
    print(f"auto_token:   {get_local_dev_relay_token() or '(none)'}")
    print(f"allowlist:    {len(ALLOWED_DEV_MACHINE_GUIDS)} machine(s)")


if __name__ == "__main__":
    main()
