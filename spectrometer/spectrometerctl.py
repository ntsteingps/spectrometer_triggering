# spectrometerctl.py

from spectrometer import Spectrometer

import datetime
import os


class DirEntry:
    def __init__(self, name, size=None, mtime=None, dir=False):
        self.name = name
        self.size = size
        self.mtime = mtime
        self.dir = dir

    @classmethod
    def from_json(cls, json):
        dir = json.get('isDirectory') or False
        name = json.get('name')
        name = name.replace('//', '/')
        size = int(json.get('size') or "0")
        mtime = json.get('mtime')
        if mtime is not None:
            mtime = datetime.datetime.fromtimestamp(mtime)

        return cls(name, size=size, mtime=mtime, dir=dir)

    def __repr__(self):
        r = f"{self.name}"
        r += f", size: {self.size}" if self.size else ""
        r += f", mtime: {self.mtime.isoformat()}" if self.mtime else ""
        r += f" (dir)" if self.dir else ""
        return r


class SpectrometerCtl:
    def __init__(self, addr="10.0.65.50", port=8100, log_cmd=False):
        self.target = Spectrometer(addr=addr, port=port, log_cmd=log_cmd)
        self.default_timeout = 5
        self.default_retry = 0

    def connect(self):
        while True:
            if self.is_connected():
                return
            print("Connecting ...")
            r, _, err = self.target.call('isCapturing', timeout=3, retry=1)
            if err is not None:
                print(f"Error: {err.__class__.__name__} {err}")
            else:
                capturing = r.get("response") or False
                print(f"Status: " + ("capturing" if capturing else "not capturing"))

    def is_connected(self):
        return self.target.is_connected()

    def is_capturing(self, timeout=None, retry=None):
        timeout = timeout or self.default_timeout
        retry = retry or self.default_retry
        r, _, err = self.target.call('isCapturing', timeout=timeout, retry=retry)
        return r.get("capturing") or False, err

    def list_files(self, prefix, recursive=False, timeout=None, retry=None):
        timeout = timeout or self.default_timeout
        retry = retry or self.default_retry
        files, err = None, None

        if prefix.endswith('/') and prefix != '/':
            prefix = prefix[:-1]

        files, err = self._list_files(os.path.dirname(prefix), timeout, retry)
        if err is not None:
            return None, err

        if recursive:
            prefixes = [f for f in files if f.name.startswith(prefix)]
            files = [] + prefixes
            for prefix in prefixes:
                rfiles, err = self._list_files_r(prefix.name, timeout, retry)
                if err is not None:
                    return None, err
                files += rfiles
        else:
            files = [f for f in files if f.name.startswith(prefix)]
            if len(files) == 1:
                prefix = files[0]
                rfiles, err = self._list_files(prefix.name, timeout, retry)
                if err is not None:
                    return None, err
                files += rfiles

        files.sort(key=lambda e: e.name)
        return files, err

    def copy_files(self, prefix, output_prefix, verbose=False, timeout=None, retry=None):
        files, err = self.list_files(prefix, recursive=True, timeout=timeout, retry=retry)
        if err is not None:
            return err
        files = [f for f in files if not f.dir]

        for f in files:
            i = f.name
            if i.startswith("/"):
                i = i[1:]
            o = os.path.join(output_prefix, i)
            if verbose:
                print(f"Copying file {f.name}")
            err = self._copy_file(f, o, timeout=timeout, retry=retry)
            if err is not None:
                return err
        return None

    def delete_file(self, filename, recursive=False, timeout=None, retry=None):
        timeout = timeout or self.default_timeout
        retry = retry or self.default_retry
        if recursive:
            return self._delete_file_r(filename, timeout=timeout, retry=retry)
        return self._delete_file(filename, timeout=timeout, retry=retry)

    def start_capture(self, maxCubes=0, maxFramePerCube=0, prefix="", timeout=None, retry=None):
        timeout = timeout or self.default_timeout
        retry = retry or self.default_retry

        params = {"maxCubes": maxCubes, "maxFramePerCube": maxFramePerCube, "prefix": prefix}
        r, _, err = self.target.call('capture', params, timeout=timeout, retry=retry)
        if err is not None:
            return False, err

        # success = r.get("success") or False
        response = r.get("response") or {}
        folder = response.get("folder") or ""
        errorMessage = r.get("errorMessage")
        return folder, errorMessage

    def stop_capture(self, timeout=None, retry=None):
        timeout = timeout or self.default_timeout
        retry = retry or self.default_retry

        r, _, err = self.target.call('stopCapture', timeout=timeout, retry=retry)
        if err is not None:
            return False, err
        success = r.get("success") or False
        errorMessage = r.get("errorMessage")
        return success, errorMessage

    def configure(self, opts, timeout=None, retry=None):
        timeout = timeout or self.default_timeout
        retry = retry or self.default_retry

        r, _, err = self.target.call('configure', opts, timeout=timeout, retry=retry)
        if err is not None:
            return False, err
        success = r.get("success") or False
        errorMessage = r.get("errorMessage")
        return success, errorMessage

    def gps_monitor(self, opts, timeout=None, retry=None):
        timeout = timeout or self.default_timeout
        retry = retry or self.default_retry

        r, _, err = self.target.call('gpsMonitor', opts, timeout=timeout, retry=retry)
        if err is not None:
            return False, err
        success = r.get("success") or False
        errorMessage = r.get("errorMessage")
        return success, errorMessage

    # ------------------------------------------------------------------------
    # Private methods
    # ------------------------------------------------------------------------

    def _list_files(self, prefix, timeout, retry):
        r, _, err = self.target.call('listFiles', prefix, timeout=timeout, retry=retry)
        if err is not None:
            return None, err
        files = [DirEntry.from_json(e) for e in r.get("response") or []]
        files.sort(key=lambda e: e.name)
        return files, err

    def _list_files_r(self, prefix, timeout, retry):
        files, err = self._list_files(prefix, timeout, retry)
        if err is not None:
            return None, err
        rfiles = []
        for f in files:
            if not f.dir:
                continue
            rrfiles, err = self._list_files_r(f.name, timeout, retry)
            if err is not None:
                return None, err

            rfiles += rrfiles

        files += rfiles
        files.sort(key=lambda e: e.name)
        return files, err

    def _copy_file(self, f, output, timeout, retry):
        dirname = os.path.dirname(output)
        os.makedirs(dirname, exist_ok=True)
        if os.path.exists(output):
            size = os.stat(output).st_size
            if size == f.size:
                return None

        offset = 0
        chunk_size = 4 * 1024 * 1024
        with open(output, "wb") as fp:
            while True:
                r, data, err = self.target.call(
                    "getFile",
                    {'name': f.name, 'offset': offset, 'bytes': chunk_size},
                    timeout=timeout,
                    retry=retry,
                )
                if err is not None:
                    return err

                n = (r.get('response') or {}).get('sentBytes') or 0

                if n != len(data):
                    return RuntimeError(f"size mismatch, received {len(data)}, response {n}")

                fp.write(data)
                offset += len(data)
                if offset >= f.size:
                    break

        return None

    def _delete_file(self, filename, timeout, retry):
        r, _, err = self.target.call('deleteFile', filename, timeout=timeout, retry=retry)
        if err is not None:
            return False, err
        success = r.get("success") or False
        errorMessage = r.get("errorMessage")
        return success, errorMessage

    def _delete_file_r(self, filename, timeout, retry):
        files, err = self.list_files(filename, recursive=True, timeout=timeout, retry=retry)
        if err is not None:
            return False, err

        for f in [f.name for f in files if not f.dir]:
            _, err = self._delete_file(f, timeout, retry)
            if err is not None:
                return False, err

        dirs = [f.name for f in files if f.dir]
        dirs.sort(reverse=True)
        for d in dirs:
            _, err = self._delete_file(d, timeout, retry)
            if err is not None:
                return False, err
        return True, None
