"""Bounded source acquisition; offline replay never calls this module."""

import argparse, hashlib, json, time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit
import requests


class PublicAuth(requests.auth.AuthBase):
    def __call__(self, request):
        return request


def utc():
    return datetime.now(timezone.utc).isoformat()


def save(path, obj):
    path.write_bytes((json.dumps(obj, indent=2) + "\n").encode())


def allowed(url, canonical):
    u = urlsplit(url)
    c = urlsplit(canonical)
    return (u.scheme, u.netloc, u.path.rstrip("/"), u.query, u.fragment) == (
        "https",
        c.netloc,
        c.path.rstrip("/"),
        "",
        "",
    )


def acquire(root, private, retry=False):
    private.mkdir(parents=True, exist_ok=True)
    plan = json.loads((root / "data/source_plan.json").read_text())
    rp = private / "receipts.json"
    records = json.loads(rp.read_text()) if rp.exists() else []
    if retry:
        denied = [r for r in records if r.get("status") == 429]
        assert len(denied) == 1 and not any(r.get("retry_attempt") for r in records)
        assert datetime.now(timezone.utc) >= datetime.fromisoformat(
            denied[0]["retry_not_before_utc"]
        )
    elif any(r.get("status") not in (200, 301, 302, 303, 307, 308) for r in records):
        raise RuntimeError("Prior unavailable source retained; no automatic repeat.")
    done = {r["package"] for r in records if r["status"] == 200}
    with requests.Session() as session:
        session.auth = PublicAuth()
        session.headers["User-Agent"] = (
            "download-spike-context/0.1 (+https://github.com/S3R3Bii/download-spike-context)"
        )
        for p in plan["packages"]:
            if p["package"] in done:
                continue
            url = p["url"]
            for redirect in range(2):
                assert (
                    allowed(url, p["url"]) and len(records) < plan["maximum_get_steps"]
                )
                last = (
                    datetime.fromisoformat(records[-1]["start_utc"]).timestamp()
                    if records
                    else 0
                )
                time.sleep(
                    max(0, plan["minimum_spacing_seconds"] - (time.time() - last))
                )
                session.cookies.clear()
                start = utc()
                try:
                    response = session.get(
                        url, timeout=(15, 45), stream=True, allow_redirects=False
                    )
                    body = bytearray()
                    for chunk in response.iter_content(16384):
                        body.extend(chunk)
                        if len(body) > plan["maximum_entity_bytes"]:
                            raise RuntimeError("entity bound")
                    raw = bytes(body)
                    assert (
                        sum(x["bytes"] for x in records) + len(raw)
                        <= plan["maximum_total_bytes"]
                    )
                    filename = f'{len(records)+1:02d}-{p["package"]}.body'
                    (private / filename).write_bytes(raw)
                    record = dict(
                        package=p["package"],
                        url=url,
                        start_utc=start,
                        end_utc=utc(),
                        status=response.status_code,
                        headers={
                            k.lower(): v
                            for k, v in response.headers.items()
                            if k.lower()
                            in [
                                "content-type",
                                "content-length",
                                "date",
                                "etag",
                                "last-modified",
                                "retry-after",
                                "cache-control",
                            ]
                        },
                        bytes=len(raw),
                        sha256=hashlib.sha256(raw).hexdigest(),
                        private_body=filename,
                        retry_attempt=retry,
                    )
                    if response.status_code == 429:
                        after = response.headers.get("Retry-After")
                        try:
                            wait = max(60, int(after))
                        except (ValueError, TypeError):
                            try:
                                wait = max(
                                    60,
                                    parsedate_to_datetime(after).timestamp()
                                    - time.time(),
                                )
                            except (ValueError, TypeError, AttributeError):
                                wait = 60
                        record["retry_not_before_utc"] = datetime.fromtimestamp(
                            time.time() + wait, timezone.utc
                        ).isoformat()
                    records.append(record)
                    save(rp, records)
                    print(
                        json.dumps(
                            {
                                k: record[k]
                                for k in [
                                    "package",
                                    "status",
                                    "bytes",
                                    "start_utc",
                                    "end_utc",
                                ]
                            }
                        ),
                        flush=True,
                    )
                    if response.status_code in (301, 302, 303, 307, 308):
                        target = requests.compat.urljoin(
                            url, response.headers["Location"]
                        )
                        assert redirect == 0 and allowed(
                            target, p["url"]
                        ), "Unapproved redirect"
                        url = target
                        continue
                    assert (
                        response.status_code == 200
                    ), "Source unavailable; original retained"
                    assert (
                        "json" in response.headers.get("Content-Type", "").lower()
                    ), "Expected JSON"
                    break
                except Exception as e:
                    save(
                        private / f"failure-{len(records):02d}.json",
                        dict(
                            timestamp_utc=utc(),
                            package=p["package"],
                            error_type=type(e).__name__,
                            message=str(e),
                            phase="source acquisition; no missing-as-zero projection",
                        ),
                    )
                    raise
    return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--retry-rate-limited", action="store_true")
    args = parser.parse_args()
    acquire(Path(__file__).resolve().parents[1], args.private, args.retry_rate_limited)
