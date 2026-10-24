"""Configuration d'un endpoint S3, lue depuis les variables d'environnement.

Chaque endpoint est identifié par un préfixe (ex. SRC, DST) :
    SRC_ENDPOINT_URL, SRC_ACCESS_KEY_ID, SRC_SECRET_ACCESS_KEY, SRC_REGION, SRC_BUCKET
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class S3Endpoint:
    name: str
    endpoint_url: str | None
    access_key_id: str
    secret_access_key: str
    bucket: str
    region: str = "us-east-1"
    addressing_style: str = "auto"  # "path" pour certains S3 compatibles (MinIO, ...)

    @classmethod
    def from_env(cls, prefix: str, bucket: str | None = None) -> S3Endpoint:
        load_dotenv()
        p = prefix.upper().rstrip("_") + "_"

        def get(key: str, default: str | None = None) -> str | None:
            return os.getenv(p + key, default)

        missing = [k for k in ("ACCESS_KEY_ID", "SECRET_ACCESS_KEY") if not get(k)]
        resolved_bucket = bucket or get("BUCKET")
        if not resolved_bucket:
            missing.append("BUCKET")
        if missing:
            raise ValueError(
                f"Variables manquantes pour {prefix}: " + ", ".join(p + m for m in missing)
            )

        return cls(
            name=prefix.lower(),
            endpoint_url=get("ENDPOINT_URL") or None,
            access_key_id=get("ACCESS_KEY_ID"),
            secret_access_key=get("SECRET_ACCESS_KEY"),
            bucket=resolved_bucket,
            region=get("REGION", "us-east-1"),
            addressing_style=get("ADDRESSING_STYLE", "auto"),
        )
