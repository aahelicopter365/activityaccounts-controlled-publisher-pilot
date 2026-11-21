"""Bounded standalone external test API; no gateway code, keys or wallet secrets."""

import asyncio
import hashlib
import json
import os
import re
import sqlite3
import time
from contextlib import suppress
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .contract import metrics, specification

MAX_BODY = 16 * 1024
MAX_RECEIPTS = 1000
CHALLENGE_PATH = "/.well-known/activityaccounts-marketplace"


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def parse_body(raw):
    def unique(pairs):
        result = dict(pairs)
        if len(result) != len(pairs):
            raise ValueError("Duplicate fields")
        return result

    body = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
    if not isinstance(body, dict) or set(body) != {"text"}:
        raise ValueError("Expected only the text field")
    text = body["text"]
    if not isinstance(text, str) or not 1 <= len(text) <= 1024:
        raise ValueError("Text must contain 1–1024 characters")
    text.encode("utf-8")
    return body


def create_app(database, challenge, hostname, *, synthetic_receipt_log=False):
    if type(synthetic_receipt_log) is not bool:
        raise TypeError("Synthetic receipt logging must be explicitly enabled")
    if not isinstance(challenge, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]{32}", challenge
    ):
        raise ValueError("Set the public marketplace ownership challenge")
    spec = specification(hostname)
    database = Path(database).resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as db:
        db.execute("PRAGMA journal_mode = WAL")
        db.execute("""CREATE TABLE IF NOT EXISTS receipt (
            id INTEGER PRIMARY KEY, received_at INTEGER NOT NULL,
            operation TEXT NOT NULL, request_sha256 TEXT NOT NULL,
            response_sha256 TEXT NOT NULL, status INTEGER NOT NULL)""")
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    slots = asyncio.Semaphore(8)

    @app.middleware("http")
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/health")
    def health():
        return {"status": "controlled-external-test"}

    @app.get("/openapi.json")
    def openapi():
        return spec

    @app.get(CHALLENGE_PATH)
    def ownership():
        return {"challenge": challenge}

    @app.post("/v1/text-metrics")
    async def text_metrics(request: Request):
        if slots.locked():
            return JSONResponse({"error": "Test API capacity reached"}, status_code=429)
        if (
            request.url.query
            or request.headers.get("content-type", "").partition(";")[0].lower()
            != "application/json"
        ):
            return JSONResponse(
                {"error": "Use a JSON request without query parameters"},
                status_code=400,
            )
        async with slots:
            try:
                raw = bytearray()
                async with asyncio.timeout(2):
                    async for chunk in request.stream():
                        if len(raw) + len(chunk) > MAX_BODY:
                            return JSONResponse(
                                {"error": "Request is too large"}, status_code=413
                            )
                        raw.extend(chunk)
                body = parse_body(raw)
                result = metrics(body["text"])
            except (ValueError, TypeError, UnicodeError, RecursionError):
                return JSONResponse(
                    {"error": "Use a text string of 1–1024 characters"}, status_code=400
                )
            except TimeoutError:
                return JSONResponse({"error": "Request timed out"}, status_code=408)
            try:
                # Persist the receipt before returning success. No raw input or auth is recorded.
                received_at = int(time.time())
                request_digest = hashlib.sha256(canonical(body)).hexdigest()
                response_digest = hashlib.sha256(canonical(result)).hexdigest()
                with sqlite3.connect(database, timeout=1) as db:
                    db.execute("BEGIN IMMEDIATE")
                    if (
                        db.execute("SELECT count(*) FROM receipt").fetchone()[0]
                        >= MAX_RECEIPTS
                    ):
                        return JSONResponse(
                            {"error": "Test receipt capacity reached"}, status_code=503
                        )
                    cursor = db.execute(
                        "INSERT INTO receipt (received_at, operation, request_sha256, response_sha256, status) VALUES (?, ?, ?, ?, 200)",
                        (
                            received_at,
                            "text-metrics",
                            request_digest,
                            response_digest,
                        ),
                    )
                    receipt = cursor.lastrowid
            except sqlite3.Error:
                return JSONResponse(
                    {"error": "Test receipt storage unavailable"}, status_code=503
                )
            if synthetic_receipt_log:
                # This bounded, fixed-shape line is opt-in for authorized synthetic tests only.
                # Emit only after SQLite commits. A closed log sink must not change API billing.
                with suppress(OSError, ValueError):
                    print(
                        json.dumps(
                            {
                                "event": "controlled.synthetic_receipt",
                                "id": receipt,
                                "received_at": received_at,
                                "operation": "text-metrics",
                                "request_sha256": request_digest,
                                "response_sha256": response_digest,
                                "status": 200,
                            },
                            separators=(",", ":"),
                        ),
                        flush=True,
                    )
            return JSONResponse(
                result, headers={"X-Controlled-Publisher-Receipt": str(receipt)}
            )

    return app


def configured_app():
    return create_app(
        os.environ["AA_EXTERNAL_RECEIPTS_DB"],
        os.environ["AA_EXTERNAL_CHALLENGE"],
        os.environ["AA_EXTERNAL_HOSTNAME"],
        synthetic_receipt_log=os.environ.get("AA_EXTERNAL_SYNTHETIC_RECEIPT_LOG")
        == "1",
    )
