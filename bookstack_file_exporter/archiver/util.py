import json
import os
import logging
import tarfile
import threading
from io import BytesIO
import glob
from pathlib import Path

from bookstack_file_exporter.common.util import HttpHelper

log = logging.getLogger(__name__)

def get_byte_response(url: str, http_client: HttpHelper) -> bytes:
    """get byte response from http request"""
    response = http_client.http_get_request(url=url)
    return response.content

class ArchiveWriteError(Exception):
    """The streaming archive is unusable and must be discarded.

    Raised on the first failed member write (which poisons the stream), on any
    later write against a poisoned stream, and by finalize() when the stream is
    poisoned or the closing flush fails. Callers must never publish the
    .partial once this has been raised.
    """

class TarStream:
    """Single-owner streaming .tar.gz writer for one export run.

    Opens the target lazily on the first write ("w:gz" straight onto the
    .tgz.partial path), so an empty run never creates a file. All writes
    serialize under an internal lock — single-writer safety is structural,
    not a convention callers must remember. Compression runs inside the
    lock: concurrent WRITERS serialize
    on compress time, but fetching threads are unaffected (zlib releases the
    GIL during compression).

    Poisoning: a gzip stream, unlike an append-mode tar, is corrupted for all
    later members by one failed addfile. The first write error therefore
    poisons the stream — every subsequent write() and finalize() raises
    ArchiveWriteError — so a corrupt archive can never be published.
    """
    def __init__(self, path: str):
        self._path = path
        self._lock = threading.Lock()
        self._tar: tarfile.TarFile | None = None
        self._poisoned = False

    def write(self, file_path: str, data: bytes):
        """Append one member; thread-safe. Raises ArchiveWriteError on failure."""
        with self._lock:
            if self._poisoned:
                raise ArchiveWriteError(
                    f"archive stream already failed; dropping write of {file_path}")
            try:
                if self._tar is None:
                    # Handle is intentionally kept open across calls (not a
                    # `with` block); it's closed later by finalize()/abort().
                    self._tar = tarfile.open(self._path, "w:gz")  # pylint: disable=consider-using-with
                data_obj = BytesIO(data)
                tar_info = tarfile.TarInfo(name=file_path)
                tar_info.size = data_obj.getbuffer().nbytes
                log.debug("Adding file: %s with size: %d bytes to archive stream",
                          tar_info.name, tar_info.size)
                self._tar.addfile(tar_info, fileobj=data_obj)
            except Exception as err:  # pylint: disable=broad-exception-caught
                self._poisoned = True
                raise ArchiveWriteError(
                    f"archive write failed for {file_path}: {err}") from err

    def finalize(self):
        """Close the stream so the .partial is complete and publishable.

        Close-then-rename ordering is load-bearing: close() flushes the gzip
        trailer, and a failure here (or a poisoned stream) raises so the caller
        discards the .partial instead of renaming a truncated archive into place.
        No-op if nothing was ever written.
        """
        with self._lock:
            if self._poisoned:
                raise ArchiveWriteError("archive stream failed mid-run; not publishing")
            if self._tar is None:
                return
            tar = self._tar
            self._tar = None
            try:
                tar.close()
            except Exception as err:  # pylint: disable=broad-exception-caught
                self._poisoned = True
                raise ArchiveWriteError(
                    f"archive close failed; not publishing: {err}") from err

    def abort(self):
        """Best-effort close for the discard path; idempotent, never raises.

        Poisons the stream so no write can land after cleanup has started.
        Safe after finalize(): the handle is already detached, so the
        successfully published archive is untouched.
        """
        with self._lock:
            tar = self._tar
            self._tar = None
            self._poisoned = True
            if tar is not None:
                try:
                    tar.close()
                except Exception:  # pylint: disable=broad-exception-caught
                    log.debug("Ignoring close error while discarding archive stream",
                              exc_info=True)

def get_json_bytes(data: dict[str, str | int]) -> bytes:
    """dump dict to json file"""
    return json.dumps(data, indent=4).encode('utf-8')

# set as function in case we want to do checks or final actions later
def remove_file(file_path: str):
    """remove a file"""
    os.remove(file_path)

def scan_archives(base_dir: str, extension: str) -> list[str]:
    """scan export directory for archives"""
    file_pattern = f"{base_dir}_*{extension}"
    return glob.glob(file_pattern)

def create_dir(dir_path: str):
    """create a directory if not exists"""
    Path(dir_path).mkdir(parents=True, exist_ok=True)
