"""CLI : check -> diff -> sync -> verify."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import typer
from botocore.exceptions import ClientError
from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Table

from s3_migration_tools.client import make_client
from s3_migration_tools.config import S3Endpoint
from s3_migration_tools.inventory import compute_diff, index_objects
from s3_migration_tools.transfer import copy_many

app = typer.Typer(
    help="Migration de données entre deux S3 (source -> destination).", no_args_is_help=True
)
console = Console()

SrcBucket = typer.Option(None, "--src-bucket", help="Écrase SRC_BUCKET")
DstBucket = typer.Option(None, "--dst-bucket", help="Écrase DST_BUCKET")
Prefix = typer.Option("", "--prefix", help="Ne traiter que les clés avec ce préfixe")


def _endpoints(src_bucket: str | None, dst_bucket: str | None):
    src = S3Endpoint.from_env("SRC", src_bucket)
    dst = S3Endpoint.from_env("DST", dst_bucket)
    return src, make_client(src), dst, make_client(dst)


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _diff(src, src_c, dst, dst_c, prefix: str):
    with console.status("Inventaire source..."):
        src_idx = index_objects(src_c, src.bucket, prefix)
    with console.status("Inventaire destination..."):
        dst_idx = index_objects(dst_c, dst.bucket, prefix)
    return compute_diff(src_idx, dst_idx)


def _print_diff(diff) -> None:
    table = Table(title="Diff source -> destination")
    table.add_column("Catégorie")
    table.add_column("Objets", justify="right")
    table.add_column("Volume", justify="right")
    for label, objs in [
        ("Manquants", diff.missing),
        ("Taille différente", diff.different),
        ("Identiques", diff.identical),
        ("Seulement en destination", diff.extra),
    ]:
        table.add_row(label, str(len(objs)), _human(sum(o.size for o in objs)))
    console.print(table)


@app.command()
def check(src_bucket: str = SrcBucket, dst_bucket: str = DstBucket):
    """Vérifie les accès aux deux buckets."""
    src, src_c, dst, dst_c = _endpoints(src_bucket, dst_bucket)
    ok = True
    for ep, client in ((src, src_c), (dst, dst_c)):
        try:
            client.head_bucket(Bucket=ep.bucket)
            console.print(f"[green]OK[/] {ep.name}: {ep.endpoint_url or 'AWS'} / {ep.bucket}")
        except ClientError as e:
            ok = False
            console.print(f"[red]KO[/] {ep.name}: {ep.bucket} -> {e}")
    raise typer.Exit(0 if ok else 1)


@app.command()
def diff(src_bucket: str = SrcBucket, dst_bucket: str = DstBucket, prefix: str = Prefix):
    """Compare les deux buckets sans rien copier."""
    src, src_c, dst, dst_c = _endpoints(src_bucket, dst_bucket)
    _print_diff(_diff(src, src_c, dst, dst_c, prefix))


@app.command()
def sync(
    src_bucket: str = SrcBucket,
    dst_bucket: str = DstBucket,
    prefix: str = Prefix,
    workers: int = typer.Option(8, help="Nombre d'objets copiés en parallèle"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Affiche ce qui serait copié"),
    report_dir: Path = typer.Option(Path("reports"), help="Dossier des rapports JSON"),
):
    """Copie les objets manquants ou différents. Relançable sans risque (idempotent)."""
    src, src_c, dst, dst_c = _endpoints(src_bucket, dst_bucket)
    d = _diff(src, src_c, dst, dst_c, prefix)
    _print_diff(d)

    if not d.to_copy:
        console.print("[green]Rien à copier, la destination est à jour.[/]")
        return
    if dry_run:
        for o in d.to_copy[:50]:
            console.print(f"  would copy {o.key} ({_human(o.size)})")
        if len(d.to_copy) > 50:
            console.print(f"  ... et {len(d.to_copy) - 50} autres")
        return

    with Progress(
        "[progress.description]{task.description}",
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(f"{src.bucket} -> {dst.bucket}", total=d.bytes_to_copy)

        def on_done(obj, err):
            progress.advance(task, obj.size)
            if err:
                progress.console.print(f"[red]Échec[/] {obj.key}: {err}")

        result = copy_many(
            d.to_copy, src_c, src.bucket, dst_c, dst.bucket, workers=workers, on_done=on_done
        )

    report_dir.mkdir(parents=True, exist_ok=True)
    report = report_dir / f"sync-{datetime.now():%Y%m%d-%H%M%S}.json"
    report.write_text(
        json.dumps(
            {
                "source": f"{src.endpoint_url}/{src.bucket}",
                "destination": f"{dst.endpoint_url}/{dst.bucket}",
                "prefix": prefix,
                "copied": len(result.copied),
                "bytes_copied": result.bytes_copied,
                "failed": result.failed,
            },
            indent=2,
        )
    )
    copied = f"{len(result.copied)} ({_human(result.bytes_copied)})"
    console.print(f"Copiés: {copied}, échecs: {len(result.failed)}")
    console.print(f"Rapport: {report}")
    raise typer.Exit(1 if result.failed else 0)


@app.command()
def verify(src_bucket: str = SrcBucket, dst_bucket: str = DstBucket, prefix: str = Prefix):
    """Vérifie que tous les objets de la source sont présents à l'identique en destination."""
    src, src_c, dst, dst_c = _endpoints(src_bucket, dst_bucket)
    d = _diff(src, src_c, dst, dst_c, prefix)
    _print_diff(d)
    if d.to_copy:
        console.print(f"[red]{len(d.to_copy)} objets manquants ou différents.[/]")
        raise typer.Exit(1)
    console.print("[green]Migration vérifiée : la destination contient toute la source.[/]")
