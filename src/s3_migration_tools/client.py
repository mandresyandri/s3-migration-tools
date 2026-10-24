"""Création des clients boto3 compatibles avec les S3 non-AWS (Cellar, Scaleway, MinIO...)."""

from __future__ import annotations

import boto3
from botocore.config import Config

from s3_migration_tools.config import S3Endpoint


def make_client(ep: S3Endpoint, max_pool_connections: int = 32):
    config = Config(
        signature_version="s3v4",
        s3={"addressing_style": ep.addressing_style},
        retries={"max_attempts": 10, "mode": "adaptive"},
        max_pool_connections=max_pool_connections,
        # Les boto3 récents envoient des checksums CRC par défaut, que beaucoup
        # de S3 compatibles (Ceph/Cellar) refusent : on ne les envoie que si requis.
        request_checksum_calculation="when_required",
        response_checksum_validation="when_required",
    )
    return boto3.client(
        "s3",
        endpoint_url=ep.endpoint_url,
        aws_access_key_id=ep.access_key_id,
        aws_secret_access_key=ep.secret_access_key,
        region_name=ep.region,
        config=config,
    )
