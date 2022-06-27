# connection.py
# -----------------------
# Socket abstraction layer to connect to spectrometer and communicate according
# the spectrometer custom protocol using asynchronous and timeouts based io

import socket
import select
import errno
import time


class Connection:
    def __init__(self, addr, port, timeout=1.0, default_timeout=1.0, read_timeout=0.2):
        self.addr = addr
        self.port = port
        self.default_timeout = default_timeout
        self.read_timeout = read_timeout
        # self.connection_timeout = connection_timeout
        self.socket = self._connect(timeout)
        self.buf = b''

    def _connect(self, timeout):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect((self.addr, self.port))
        except (socket.timeout, TimeoutError):
            raise TimeoutError()

        s.settimeout(None)
        s.setblocking(0)
        return s

    def _fillBuf(self, timeout):
        count = 0
        while True:
            try:
                b = self.socket.recv(4096)
                count += len(b)
                self.buf += b

            except OSError as err:
                if err.errno == errno.EAGAIN:
                    if count > 0:
                        return count
                    r, w, s = select.select([self.socket], [], [], timeout)
                    if len(r) < 1:
                        return count
                elif (
                    err.errno == errno.ECONNABORTED
                    or err.errno == errno.ECONNREFUSED
                    or err.errno == errno.ECONNRESET
                    or err.errno == errno.ENOTCONN
                ):
                    self.socket.close()
                    self.socket = None
                    raise

    def read(self, n=0, timeout=None):
        if timeout is None:
            timeout = self.default_timeout
        deadline = time.time() + timeout
        if n == 0:
            self._fillBuf(0)
            if len(self.buf) == 0:
                self._fillBuf(max(0, deadline - time.time()))
            b = self.buf
            self.buf = b''
            return b

        while True:
            if len(self.buf) >= n:
                b = self.buf[0:n]
                self.buf = self.buf[n:]
                return b
            cnt = self._fillBuf(max(self.read_timeout, deadline - time.time()))
            if cnt == 0:
                b = self.buf
                self.buf = b''
                return b

    def read_past(self, seq, timeout=None):
        if timeout is None:
            timeout = self.default_timeout
        deadline = time.time() + timeout
        sindex = 0
        while True:
            if len(self.buf) >= len(seq):
                index = self.buf.find(seq, sindex)
                if index >= 0:
                    index += len(seq)
                    b = self.buf[0:index]
                    self.buf = self.buf[index:]
                    return b
                sindex = max(0, len(self.buf) - len(seq))
            cnt = self._fillBuf(max(self.read_timeout, deadline - time.time()))
            if cnt == 0:
                return b''

    def write(self, buf):
        self.socket.sendall(buf)
