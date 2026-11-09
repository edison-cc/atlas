"""Shared JSON output for Atlas commands."""

import json


def print_json(**data):
    print(json.dumps({"schema_version": 1, **data}, ensure_ascii=False, separators=(",", ":")))


def pagination(returned, total, has_more):
    return {"returned": returned, "total": total, "has_more": has_more}
