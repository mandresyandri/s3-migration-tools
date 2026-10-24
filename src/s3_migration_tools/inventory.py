"""Inventaire des objets d'un bucket et calcul du diff source -> destination."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ObjectInfo:
    key: str
    size: int
    etag: str


def list_objects(client, bucket: str, prefix: str = "") -> Iterator[ObjectInfo]:
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            yield ObjectInfo(key=obj["Key"], size=obj["Size"], etag=obj["ETag"].strip('"'))


def index_objects(client, bucket: str, prefix: str = "") -> dict[str, ObjectInfo]:
    return {o.key: o for o in list_objects(client, bucket, prefix)}


@dataclass
class Diff:
    missing: list[ObjectInfo] = field(default_factory=list)  # absents de la destination
    different: list[ObjectInfo] = field(default_factory=list)  # taille différente
    identical: list[ObjectInfo] = field(default_factory=list)
    extra: list[ObjectInfo] = field(default_factory=list)  # présents seulement en destination

    @property
    def to_copy(self) -> list[ObjectInfo]:
        return self.missing + self.different

    @property
    def bytes_to_copy(self) -> int:
        return sum(o.size for o in self.to_copy)


def compute_diff(src: dict[str, ObjectInfo], dst: dict[str, ObjectInfo]) -> Diff:
    # On compare sur la taille : les ETags ne sont pas comparables entre fournisseurs
    # dès qu'un objet a été uploadé en multipart.
    diff = Diff()
    for key, obj in src.items():
        other = dst.get(key)
        if other is None:
            diff.missing.append(obj)
        elif other.size != obj.size:
            diff.different.append(obj)
        else:
            diff.identical.append(obj)
    diff.extra = [o for k, o in dst.items() if k not in src]
    return diff
