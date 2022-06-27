# spectrometer.py
# ----------------------------------------------------------------------------
# Spectrometer interface abstraction layer, implementing the custom JSON /
# binary based command response protocol of the target.

import json
import time

from connection import Connection


class Spectrometer:
    def __init__(self, addr="10.0.65.50", port=8100, log_cmd=False):
        self.addr = addr
        self.port = port
        self.conn = None
        self.prompt = b'\r\nhpi> '
        self.log_cmd = log_cmd
        self.default_timeout = 5
        self.default_retry = 0

    # call performs the RPC call `cmd(args)` to the spectrometer over the
    # attached socket, and returns the decoded response and the binary payload
    # if any. A new connection is established if the socket is not already
    # connected. Any exception raised other than InterruptedError is captured as
    # an error. The function returns 3 values: (response, data, err)
    def call(self, cmd, args=None, timeout=None, retry=None):
        timeout = timeout or self.default_timeout
        retry = retry or self.default_retry

        b = self._format_cmd(cmd, args)

        retry_count = 0
        while True:
            deadline = time.time() + timeout
            try:
                response, data = self._call(b, timeout=timeout)
                return response, data, None
            except InterruptedError:
                raise
            except Exception as err:
                if self.log_cmd:
                    if err is not None:
                        print(err.__class__.__name__, str(err))
                if retry >= 0 and retry_count >= retry:
                    return {}, None, err
                retry_count += 1
                time.sleep(max(0, deadline - time.time()) / 2)

    def is_connected(self):
        return self.conn is not None

    # ------------------------------------------------------------------------
    # Private methods
    # ------------------------------------------------------------------------

    def _connect(self, timeout=None):
        if self.conn is None:
            if self.log_cmd:
                print("Connecting...")

            self.conn = Connection(self.addr, self.port, timeout=timeout)
            _ = self.conn.read_past(self.prompt, timeout=timeout)

    def _format_cmd(self, cmd, args=None):
        if args is None:
            return (cmd + '\r').encode('utf-8')
        if isinstance(args, str):
            return (cmd + '("' + args + '")' + '\r').encode('utf-8')
        return (cmd + '(' + json.dumps(args) + ')' + '\r').encode('utf-8')

    def _call(self, b, timeout=None):
        timeout = timeout or self.default_timeout
        deadline = time.time() + timeout

        self._connect(timeout=max(0, deadline - time.time()))
        if self.log_cmd:
            print(b)
        self.conn.write(b)

        data = self.conn.read_past(self.prompt, timeout=max(0, deadline - time.time()))
        return self._split_response(data)

    def _split_response(self, buf):
        prompt_index = buf.rfind(self.prompt)
        if prompt_index < 0:
            self.conn = None
            raise RuntimeError(f"missing trailing command prompt, data: ...{buf[-10:]}")

        response_index = buf.rfind(b'\r\n{', 0, prompt_index)
        if prompt_index < 0:
            self.conn = None
            raise RuntimeError(f"missing response json, data: {buf[:10]}...{buf[-10:]}")

        data = buf[:response_index]
        response = json.loads(buf[response_index + 2 : prompt_index].decode('utf-8'))
        if self.log_cmd:
            print(response)
        return response, data
