"""Backup manifests retain data from both TG Manage and legacy installs."""

from __future__ import annotations

import tarfile

from backend.api.routes.ops import BACKUP_ARCHIVE_PATHS, BACKUP_STATUS_PATHS
from backend.services.backup_archive import DEFAULT_BACKUP_PATHS, create_backup_tarball


def test_backup_manifests_include_both_workdirs():
    for paths in (BACKUP_ARCHIVE_PATHS, BACKUP_STATUS_PATHS, DEFAULT_BACKUP_PATHS):
        assert ".tg_manage" in paths
        assert ".signer" in paths


def test_backup_preserves_legacy_and_new_workdir_content(tmp_path):
    data_dir = tmp_path / "data"
    for name in (".signer", ".tg_manage"):
        directory = data_dir / name
        directory.mkdir(parents=True)
        (directory / "config.json").write_text(name, encoding="utf-8")

    archive = create_backup_tarball(data_dir, tmp_path / "backup.tar.gz")
    with tarfile.open(archive, "r:gz") as tar:
        for name in (".signer", ".tg_manage"):
            assert tar.extractfile(f"{name}/config.json").read().decode() == name
