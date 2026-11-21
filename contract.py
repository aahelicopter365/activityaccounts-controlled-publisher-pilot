"""Small, explicit OpenAPI profile and approved synthetic qualification sample."""

import json
import re
import sys

SAMPLE_BODY = {"text": "Hello pilot"}


def metrics(text):
    import hashlib

    return {
        "characters": len(text),
        "words": len(text.split()),
        "lines": len(text.splitlines()),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def specification(hostname):
    if not isinstance(hostname, str) or not re.fullmatch(
        r"[a-z0-9.-]+\.[a-z]{2,63}", hostname
    ):
        raise ValueError(
            "Provide the public HTTPS hostname without a URL or credentials"
        )
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Controlled external text metrics test",
            "version": "1",
            "description": "Operator-controlled external test API. This is not an independent publisher relationship. Use synthetic text only.",
        },
        "servers": [{"url": "https://" + hostname}],
        "paths": {
            "/v1/text-metrics": {
                "post": {
                    "operationId": "text-metrics",
                    "summary": "Count characters, whitespace-separated words and split lines",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["text"],
                                    "properties": {
                                        "text": {
                                            "type": "string",
                                            "minLength": 1,
                                            "maxLength": 1024,
                                        }
                                    },
                                },
                                "example": SAMPLE_BODY,
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Deterministic metrics; the publisher also records a bounded receipt containing hashes only",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "required": [
                                            "characters",
                                            "words",
                                            "lines",
                                            "sha256",
                                        ],
                                        "properties": {
                                            "characters": {
                                                "type": "integer",
                                                "minimum": 1,
                                                "maximum": 1024,
                                            },
                                            "words": {
                                                "type": "integer",
                                                "minimum": 0,
                                                "maximum": 1024,
                                            },
                                            "lines": {
                                                "type": "integer",
                                                "minimum": 1,
                                                "maximum": 1024,
                                            },
                                            "sha256": {
                                                "type": "string",
                                                "minLength": 64,
                                                "maxLength": 64,
                                            },
                                        },
                                    },
                                    "example": metrics(SAMPLE_BODY["text"]),
                                }
                            },
                        },
                    },
                },
            },
        },
    }


def submission(hostname):
    return {
        "name": "CONTROLLED EXTERNAL TEST — Text Metrics",
        "description": "A controlled, independently hosted test deployment for marketplace qualification. No outside publisher relationship is claimed. Synthetic text only.",
        "category": "Controlled test",
        "hostname": hostname,
        "spec": specification(hostname),
        "samples": {
            "text-metrics": {
                "body": SAMPLE_BODY,
                "expected": metrics(SAMPLE_BODY["text"]),
            }
        },
        "plans": [
            {
                "id": "pilot",
                "price_units": 1_000_000,
                "allowance": 5,
                "duration_seconds": 86400,
                "calls_per_minute": 60,
            }
        ],
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: python -m marketplace.external_test.contract PUBLIC_HOSTNAME"
        )
    print(json.dumps(submission(sys.argv[1]), indent=2))
