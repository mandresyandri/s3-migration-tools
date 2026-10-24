"""Copie d'objets entre deux S3 de fournisseurs différents (pas de copie côté serveur possible).

Les objets sont streamés : lecture depuis la source et upload multipart vers la
destination, sans passer par le disque.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from boto3.s3.transfer import TransferConfig

from s3_migration_tools.inventory import ObjectInfo

TRANSFER_CONFIG = TransferConfig(
    multipart_threshold=64 * 1024 * 1024,
    multipart_chunksize=64 * 1024 * 1024,
    max_concurrency=4,
)

# Métadonnées HTTP conservées lors de la copie
_PRESERVED_HEADERS = {
    "ContentType": "ContentType",
    "ContentEncoding": "ContentEncoding",
    "ContentDisposition": "ContentDisposition",
    "ContentLanguage": "ContentLanguage",
    "CacheControl": "CacheControl",
}


@dataclass
class TransferResult:
    copied: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    bytes_copied: int = 0


def copy_object(src_client, src_bucket: str, dst_client, dst_bucket: str, key: str) -> None:
    resp = src_client.get_object(Bucket=src_bucket, Key=key)
    extra_args = {dst: resp[src] for src, dst in _PRESERVED_HEADERS.items() if resp.get(src)}
    if resp.get("Metadata"):
        extra_args["Metadata"] = resp["Metadata"]
    with resp["Body"] as body:
        dst_client.upload_fileobj(
            body, dst_bucket, key, ExtraArgs=extra_args, Config=TRANSFER_CONFIG
        )


def copy_many(
    objects: Iterable[ObjectInfo],
    src_client,
    src_bucket: str,
    dst_client,
    dst_bucket: str,
    workers: int = 8,
    on_done: Callable[[ObjectInfo, Exception | None], None] | None = None,
) -> TransferResult:
    result = TransferResult()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(copy_object, src_client, src_bucket, dst_client, dst_bucket, o.key): o
            for o in objects
        }
        for fut in as_completed(futures):
            obj = futures[fut]
            err = fut.exception()
            if err is None:
                result.copied.append(obj.key)
                result.bytes_copied += obj.size
            else:
                result.failed[obj.key] = repr(err)
            if on_done:
                on_done(obj, err)
    return result
