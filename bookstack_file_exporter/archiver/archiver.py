from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import functools
import logging
import os

from bookstack_file_exporter.exporter.node import Node
from bookstack_file_exporter.archiver import util
from bookstack_file_exporter.archiver.node_archiver import (
    NodeArchiver,
    BookArchiver,
    ChapterArchiver,
    PageArchiver,
)
from bookstack_file_exporter.archiver.s3_archiver import S3CompatibleArchiver
from bookstack_file_exporter.config_helper.remote import S3ProviderConfig
from bookstack_file_exporter.notify.models import ExportStatus, UploadOutcome
from bookstack_file_exporter.config_helper.config_helper import ConfigNode
from bookstack_file_exporter.common import util as common_util
from bookstack_file_exporter.common.util import HttpHelper

log = logging.getLogger(__name__)

_DATE_STR_FORMAT = "%Y-%m-%d_%H-%M-%S"

# Cap concurrent target uploads: targets are typically 1-3; beyond a few, wall clock
# is bounded by upload bandwidth, not target count. Not user-configurable until
# someone needs it (adding a knob later is non-breaking).
_MAX_UPLOAD_WORKERS = 4


class AggregateUploadError(Exception):
    """All upload targets failed AND no durable local copy survives (keep_last < 0)."""


# pylint: disable=too-many-instance-attributes
class Archiver:
    """
    Archiver helps handle archive duties: pulls all the necessary files from upstream
    and then pushes them to the specified backup location(s)

    Args:
        :config: <ConfigNode> = Configuration with user inputs and general options.
        :http_client: <HttpHelper> = http helper functions with config from user inputs

    Returns:
        Archiver instance with attributes that are accessible
        for use for handling bookstack exports and remote uploads.
    """
    def __init__(self, config: ConfigNode, http_client: HttpHelper,
                 node_archiver=None, s3_archiver_cls=S3CompatibleArchiver):
        self.config = config
        # for convenience
        self.base_dir = self._level_base_dir(config.base_dir_name,
                                             config.user_inputs.export_level)
        self.archive_dir = self._generate_root_folder(self.base_dir)
        self._archiver: NodeArchiver = (
            node_archiver if node_archiver is not None else self._build_archiver(http_client)
        )
        self._s3_archiver_cls = s3_archiver_cls

    def _build_archiver(self, http_client: HttpHelper) -> NodeArchiver:
        """Return the appropriate archiver based on the configured export level."""
        export_level = self.config.user_inputs.export_level
        export_meta: bool = self.config.user_inputs.assets.export_meta
        if export_level == "books":
            return BookArchiver(
                archive_dir=self.archive_dir,
                api_urls=self.config.urls,
                export_formats=self.config.user_inputs.formats,
                http_client=http_client,
                export_meta=export_meta,
                asset_config=self.config.user_inputs.assets,
                export_workers=self.config.user_inputs.export_workers,
            )
        if export_level == "chapters":
            return ChapterArchiver(
                archive_dir=self.archive_dir,
                api_urls=self.config.urls,
                export_formats=self.config.user_inputs.formats,
                http_client=http_client,
                export_meta=export_meta,
                asset_config=self.config.user_inputs.assets,
                export_workers=self.config.user_inputs.export_workers,
            )
        # default: "pages"
        return PageArchiver(self.archive_dir, self.config, http_client)

    def create_export_dir(self):
        """create directory for archiving"""
        output_dir = self.config.output_dir
        if not output_dir:
            log.info("No output path specified, using current directory for archive")
            return
        log.info("Creating base directory for archive: %s", output_dir)
        try:
            util.create_dir(output_dir)
        except PermissionError as perm_err:
            # create_dir uses mkdir(exist_ok=True), which never raises for an
            # existing directory (writable or not) — the docker mounted-volume
            # case is tolerated there, not here. Reaching this catch means the
            # resolved output dir is missing AND creating it was denied: a real
            # misconfig, so fail now with a pointed message instead of dying
            # later at the first archive write.
            log.error(
                "Cannot create export directory '%s': %s - the path does not "
                "exist and creation was denied; fix output_path/-o or its "
                "parent directory permissions",
                output_dir, perm_err)
            raise

    def set_stop(self, stop):
        """Inject the shutdown flag into the node archiver for cooperative cancel.

        One-shot mode never calls this, so the archiver's flag stays None (no-op
        at every checkpoint). Scheduled mode forwards its threading.Event here.
        """
        self._archiver.set_stop(stop)

    def discard_incomplete(self):
        """Abort the archive stream and remove this run's .tgz.incomplete; never the final .tgz.

        Abort-then-unlink: the stream handle is closed (best-effort) before the
        file is removed, and abort poisons the stream so no straggler write can
        recreate the .incomplete after cleanup. Idempotent and missing-file
        tolerant: on the success path finalize() already detached the handle and
        renamed the .incomplete away, so this is a no-op.
        """
        self._archiver.abort_archive()
        incomplete = self._archiver.incomplete_file
        if os.path.exists(incomplete):
            log.info("Cleaning up incomplete archive: %s", incomplete)
            util.remove_file(incomplete)

    def sweep_orphans(self):
        """Delete prior-run .tar / .tgz.incomplete orphans (SIGKILL backstop).

        Run at the start of a cycle, BEFORE this run writes any tar or .incomplete.
        Safety comes from that ordering, not the glob: scan_archives globs
        {base}_*{ext}, which would also match this run's own filenames — but none
        exist on disk yet, so only earlier runs' leftovers are removed. Moving this
        call after any write would make it delete the live tar.

        Globs on the unscoped base_dir_name (e.g. `bkps/bookstack_export`), not the
        level-scoped base_dir (`bkps/bookstack_export_books`): intermediates are always
        junk regardless of export level, so `bkps/bookstack_export_*` clears incompletes
        stranded by prior runs at any level. The `bkps/bookstack_export_` prefix still
        anchors the scan so unrelated files are never touched.
        (keep_last retention deliberately stays level-scoped — those are deliverables.)
        Also retro-cleans .tar orphans stranded by pre-v3 versions (which staged
        an intermediate .tar before gzipping) and by past failed cycles.
        """
        tgz_ext = self._archiver.file_extension_map['tgz']
        for ext in (self._archiver.file_extension_map['tar'], f"{tgz_ext}.incomplete"):
            for path in util.scan_archives(self.config.base_dir_name, ext):
                util.remove_file(path)

    def get_bookstack_exports(self, nodes: dict[int, Node]):
        """export all node content (polymorphic: pages, books, or chapters)"""
        log.info("Exporting all bookstack contents")
        self._archiver.archive(nodes)

    @property
    def has_exported_content(self) -> bool:
        """True if the streaming .incomplete exists, i.e. at least one file was written.

        Checked against the archive on disk (ground truth) rather than a flag
        threaded up from the archivers, so it cannot drift from what was actually
        archived. The stream opens lazily on the first write, so mere Archiver
        construction never creates the file.
        """
        return os.path.exists(self._archiver.incomplete_file)

    def create_archive(self):
        """finalize the streaming archive: close and atomically rename to .tgz"""
        self._archiver.finalize_archive()

    # send to remote systems
    def archive_remote(self) -> list[UploadOutcome]:
        """Upload to every configured target, attempting all even if some fail.

        Returns one UploadOutcome per target (dest on success, error on upload
        failure, or dest+warning when the upload landed but retention cleanup failed),
        in config order. Never raises on a per-target upload error — aggregate status
        is decided by resolve_remote_status.

        Targets upload concurrently (one thread each, capped at _MAX_UPLOAD_WORKERS):
        the work is I/O-bound (HeadBucket RTT, multi-MB upload, retention listing), the
        same rationale as node_archiver's export_workers pool. Each _upload constructs
        its own S3CompatibleArchiver with its own boto3 Session, so no client state is
        shared across threads. executor.map preserves input order, and _upload's
        catch-all means no worker exception can propagate out of map().
        """
        entries = self.config.object_storage_config or []
        if not entries:
            return []
        allow_prune = self.prune_allowed
        if len(entries) == 1:
            return [self._upload(entries[0], allow_prune=allow_prune)]
        workers = min(len(entries), _MAX_UPLOAD_WORKERS)
        upload = functools.partial(self._upload, allow_prune=allow_prune)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            return list(executor.map(upload, entries))

    def _upload(self, provider_config: S3ProviderConfig,
                allow_prune: bool = True) -> UploadOutcome:
        label = provider_config.name
        try:
            archiver = self._s3_archiver_cls(provider_config)
            dest = archiver.upload_backup(self._archiver.archive_file)
        except Exception as err:  # pylint: disable=broad-except
            # attempt-all: record and continue so other targets still run
            log.error("Upload to target '%s' failed: %s", label, err)
            return UploadOutcome(label=label, dest=None, error=str(err))
        # Partial run: the degraded archive still uploads (a thin copy beats no
        # copy) but must not trigger retention that evicts complete backups.
        if not allow_prune:
            return UploadOutcome(label=label, dest=dest, error=None)
        # Upload landed. A retention-prune failure is housekeeping, not a backup failure:
        # keep dest (never flip to failed) but flag a warning so the run is degraded.
        try:
            pruned = archiver.clean_up(
                self._archiver.file_extension_map['tgz'],
                self.config.user_inputs.export_level)
        except Exception as err:  # pylint: disable=broad-except
            log.error("Remote retention cleanup for target '%s' failed (upload OK): %s",
                      label, err)
            return UploadOutcome(label=label, dest=dest, error=None, warning=str(err))
        return UploadOutcome(label=label, dest=dest, error=None, pruned=pruned)

    def resolve_remote_status(self, outcomes: list[UploadOutcome]) -> ExportStatus:
        """Derive run status from upload outcomes. Raise AggregateUploadError only when
        NO durable copy survives: every upload failed AND keep_last<0 retains no local
        copy across runs (this run's file lingers but a later successful run prunes it).
        A target that uploaded but whose retention cleanup failed (warning) downgrades
        SUCCESS to PARTIAL."""
        if not outcomes:
            return ExportStatus.SUCCESS
        n_ok = sum(1 for o in outcomes if o.dest is not None)
        if n_ok == len(outcomes) and not any(o.warning for o in outcomes):
            return ExportStatus.SUCCESS
        if n_ok == 0 and self.config.user_inputs.keep_last < 0:
            failed = ", ".join(o.label for o in outcomes)
            raise AggregateUploadError(
                f"all upload targets failed; only the local copy remains and "
                f"keep_last<0 means a later successful run will prune it: {failed}")
        return ExportStatus.PARTIAL

    def clean_up(self) -> list[str]:
        """remove archive after sending to remote target; return files deleted"""
        # this captures keep_last = 0
        if not self.config.user_inputs.keep_last:
            return []
        if not self.prune_allowed:
            return []
        to_delete = self._get_stale_archives()
        if to_delete:
            self._delete_files(to_delete)
        return to_delete

    @property
    def archive_file(self) -> str:
        """full path to the produced .tgz archive"""
        return self._archiver.archive_file

    @property
    def failed_nodes(self) -> list[str]:
        """Node exports skipped after fetch failures (archive-relative paths)."""
        return self._archiver.failed_node_exports

    @property
    def failed_assets(self) -> list[str]:
        """Asset downloads skipped after fetch failures (prefix/page/name paths)."""
        return self._archiver.failed_asset_downloads

    @property
    def content_written(self) -> bool:
        """True once at least one node (document) export landed in the tar."""
        return self._archiver.content_written

    @property
    def prune_allowed(self) -> bool:
        """False when this run dropped content and the user has not opted into
        prune_on_partial: a degraded (partial) archive must never evict complete
        backups, locally or remotely. Content loss only — a failed upload never
        prunes its own target anyway, and resolve_remote_status guards the
        no-durable-copy case. Consumed by clean_up, archive_remote, and run.py's
        NotifyResult."""
        if self.config.user_inputs.prune_on_partial:
            return True
        return not (self.failed_nodes or self.failed_assets)

    @property
    def retention_configured(self) -> bool:
        """True when any pruning could actually happen (top-level keep_last set,
        or any object_storage target with keep_last > 0). Gates the 'pruning
        skipped' messaging so keep_last-less users are not told about a skip of
        an action that was never going to run."""
        if self.config.user_inputs.keep_last:
            return True
        return any(t.keep_last > 0
                   for t in self.config.user_inputs.object_storage or [])

    def _get_stale_archives(self) -> list[str]:
        # if user is uploading to object storage
        # delete the local .tgz archive since we have it there already
        archive_list: list[str] = util.scan_archives(self.base_dir,
                                                     self._archiver.file_extension_map['tgz'])
        if not archive_list:
            log.debug("No archive files found to clean up")
            return []
        # Retention only ever touches THIS run's export level -- a pages run must
        # not prune books/chapters archives that share the output directory.
        export_level = self.config.user_inputs.export_level
        archive_list = [p for p in archive_list
                        if common_util.same_export_level(os.path.basename(p), export_level)]
        if not archive_list:
            return []
        # if negative number, we remove all local archives for this level
        # assume user is using remote storage and will upload there
        if self.config.user_inputs.keep_last < 0:
            log.debug("Local archive files will be deleted, keep_last: -1")
            return archive_list
        # keep_last > 0: full and partial archives are independent retention groups,
        # each keeping the newest keep_last. A partial run adds a partial, so it can
        # never push the full count over keep_last -> partials never evict fulls.
        partial_suffix = f"_partial{self._archiver.file_extension_map['tgz']}"
        partials = [p for p in archive_list if os.path.basename(p).endswith(partial_suffix)]
        fulls = [p for p in archive_list if not os.path.basename(p).endswith(partial_suffix)]
        return self._filter_archives(fulls) + self._filter_archives(partials)

    def _filter_archives(self, file_list: list[str]) -> list[str]:
        """get older archives based on keep number"""
        files_to_clean = common_util.oldest_beyond_keep(
            file_list,
            # ctime is inode-change time, not creation time -- a chmod/chown -R or
            # volume restore resets it, making prune order arbitrary. The filename
            # embeds the run timestamp (..._%Y-%m-%d_%H-%M-%S.tgz), which sorts
            # lexicographically in chronological order, so use that instead.
            key=os.path.basename,
            keep_last=self.config.user_inputs.keep_last,
        )
        log.debug("%d local archives will be cleaned up", len(files_to_clean))
        return files_to_clean

    def _delete_files(self, file_list: list[str]):
        for file in file_list:
            util.remove_file(file)

    @staticmethod
    def _level_base_dir(base_dir: str, export_level: str) -> str:
        """Append the export level to the archive base name for non-default levels.

        `pages` (the default) stays byte-identical to prior behavior; `books` and
        `chapters` get a distinguishable name (e.g. `bkps_books`). Because keep_last
        cleanup globs on this base, retention is naturally scoped per level.
        """
        if export_level == "pages":
            return base_dir
        return f"{base_dir}_{export_level}"

    @staticmethod
    def _generate_root_folder(base_folder_name: str) -> str:
        """return base archive name"""
        return base_folder_name + "_" + datetime.now(timezone.utc).strftime(_DATE_STR_FORMAT)
