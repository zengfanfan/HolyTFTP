import os
import sys
import socket
import gevent
from gevent import monkey, queue
from .packet import *
from ..log import log
from ..globals import g
from ..config import cfg

TFTP_RETRY = 5
BUFFER_SIZE = 0xffff

monkey.patch_all()  # use monkey to replace original socket (and others) module
socket.setdefaulttimeout(TFTP_TIMEOUT)


class TftpServer(object):
    PORT = 69
    WORKER_NUMBER = 4

    def __init__(self, port=PORT):
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.queue = queue.Queue()
        self.peers = {}  # [address] = session
        self.start_callback = self.nop_callback
        self.update_callback = self.nop_callback
        self.stop_callback = self.nop_callback

    def nop_callback(self, *args, **kwargs):
        pass

    def set_callback(self, start=None, update=None, stop=None):
        self.start_callback = start or self.nop_callback
        self.update_callback = update or self.nop_callback
        self.stop_callback = stop or self.nop_callback

    def start(self):
        bind_ok = False
        for i in range(self.port, 0x10000):
            try:
                self.sock.bind(("0.0.0.0", i))
            except OSError as e:
                log.info("Failed to bind port %d" % i, e)
                if i == self.port:
                    g.warn("Failed to bind port %d: %s" % (self.port, e))
            else:
                self.port = i
                bind_ok = True
                break
        if not bind_ok:
            log.fatal("No port available")
            g.error("No port available.")
            sys.exit(1)

        self.sock.setblocking(True)

        g.spawn(self.boss)

        for i in range(TftpServer.WORKER_NUMBER):
            g.spawn(self.worker, i + 1)

    def boss(self):
        log.info("boss is ready")
        while True:
            try:
                data, address = self.sock.recvfrom(BUFFER_SIZE)
                log.info("B#0 << %s:%d: UDP L=%d" % (address[0], address[1], len(data)))
                if self.peers.get(address) is not None:
                    log.debug("B#0 -- %s:%d: duplicate session, ignored." % address)
                    continue  # duplicate session
                self.queue.put((data, address))
                self.peers[address] = True
            except socket.timeout:
                log.debug("B#0: wait timeout and retry ...")
            except socket.error as e:
                log.error(e)
            finally:
                gevent.sleep()

    def worker(self, index):
        log.info("worker#%d is ready" % index)
        while True:
            data, address = self.queue.get()
            log.info("W#%d << %s:%d: UDP L=%d" % (index, address[0], address[1], len(data)))
            s = TftpSession(self, index, data, address)
            self.peers[s.peer] = s
            s.run()
            log.warn("W#%d -- %s:%d: session is terminated" % (index, address[0], address[1]))
            self.peers[s.peer] = None
            del s
            gevent.sleep()


class TftpSession(object):

    def __init__(self, server, index, data, address):
        self.server = server
        self.index = index
        self.data = data
        self.peer = address
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(TFTP_TIMEOUT)
        self.req = None
        self.filename = None
        self.block = 0
        self.total_block = 0
        self.retry = 0
        self.finished = False
        self.sending_pkt = None

    def send(self, pkt, record=True):
        log.info("W#%d >> %s:%d: %s" % (self.index, self.peer[0], self.peer[1], pkt))
        if record:
            self.sending_pkt = pkt
        if pkt.code == TftpOpCode.Error:
            title = "Denied" if pkt.errcode in [TftpErrCode.AccessViolation, TftpErrCode.FileNotFound] else "Error"
            self.server.stop_callback(self.peer, False, title, TftpErrCode.str(pkt.errcode) + ": " + pkt.msg)
            self.finished = True
        try:
            return self.sock.sendto(bytes(pkt), self.peer)
        except socket.error as e:
            log.debug("W#%d -- %s:%d: error: %s" % (self.index, self.peer[0], self.peer[1], e))

    def run(self):
        # parse and check first packet
        self.req = TftpReqPacket(self.data)
        result = self.req.parse()
        log.info("W#%d << %s:%d: %s" % (self.index, self.peer[0], self.peer[1], self.req))
        if result is False:
            return self.sock.close()  # simply ignore

        # get direction
        r = (self.req.code == TftpOpCode.ReadRequest)
        # get file size
        size = 0
        if self.req.filename:
            self.filename = cfg.get_real_path(self.req.filename)
            if r and self.filename and os.access(self.filename, os.F_OK):
                size = os.path.getsize(self.filename)
            elif not r and self.req.tsize:
                size = self.req.tsize
        self.server.start_callback(self.peer, r, self.req.filename, size,
                                   self.filename or self.req.filename)
        if result is not True:  # error occurred
            return self.send(TftpErrorPacket(*result))
        if not self.filename:
            return self.send(TftpErrorPacket(TftpErrCode.FileNotFound, "File Not Found"))
        if self.req.timeout:
            self.sock.settimeout(self.req.timeout)

        # start session
        if r:  # READ
            if not os.access(self.filename, os.F_OK):
                return self.send(TftpErrorPacket(TftpErrCode.FileNotFound, "File Not Found"))
            if not os.access(self.filename, os.R_OK):
                return self.send(TftpErrorPacket(TftpErrCode.AccessViolation, "Access Denied"))
            if self.req.accepted_options:
                # send OptionACK
                self.send(TftpAckPacket.from_previous_packet(self.req))
            else:
                try:
                    with open(self.filename, "rb") as f:
                        data = f.read(self.req.block_size)
                        self.total_block += 1
                        self.block = self.total_block % 0x10000
                        self.send(TftpDataPacket(self.block, data))
                        self.server.update_callback(
                            self.peer, (self.total_block - 1) * self.req.block_size + len(data))
                        if len(data) < self.req.block_size:
                            self.finished = True
                except FileNotFoundError as e:
                    log.error("W#%d: cannot open file %s" % (self.index, self.filename))
                    return self.send(TftpErrorPacket(TftpErrCode.FileNotFound, e.strerror))
                except OSError as e:
                    log.error("Failed to open file %s:" % self.filename, e)
                    return self.send(TftpErrorPacket(TftpErrCode.AccessViolation, e.strerror))
        else:  # WRITE
            if (os.access(self.filename, os.F_OK)
                    and not os.access(self.filename, os.W_OK))\
                or (not os.access(self.filename, os.F_OK)
                    and not os.access(os.path.dirname(self.filename), os.W_OK)):
                return self.send(TftpErrorPacket(TftpErrCode.AccessViolation, "Access Denied"))
            self.send(TftpAckPacket.from_previous_packet(self.req))

        # wait next packet
        while True:
            try:
                data, address = self.sock.recvfrom(BUFFER_SIZE)
                if address != self.peer:
                    log.debug("W#%d: %s: is not peer %s" % (self.index, address, self.peer))
                    self.send(TftpErrorPacket(TftpErrCode.UnknownTID))
                else:
                    log.info("W#%d << %s:%d: UDP L=%d" % (self.index, self.peer[0], self.peer[1], len(data)))
                    if self.step(data) is True:
                        return
            except socket.timeout:
                if self.timeout() > TFTP_RETRY:
                    if not self.finished:
                        log.error("W#%d: timeout" % self.index)
                        self.server.stop_callback(self.peer, False, "Timeout")
                    else:
                        self.server.stop_callback(self.peer, True, "")
                    return
            except socket.error as e:
                log.error("W#%d: error:" % self.index, e)
                self.server.stop_callback(self.peer, False, "Error", str(e))
                return

    def timeout(self):
        if self.finished and self.req.code == TftpOpCode.WriteRequest:
            log.info("W#%d: final ack is sent %ds ago, terminated."
                     % (self.index, self.sock.gettimeout()))
            return TFTP_RETRY + 1
        log.debug("W#%d: timeout and retry" % self.index)
        self.retry += 1
        self.send(self.sending_pkt)
        return self.retry

    def step(self, data):
        if self.req.code == TftpOpCode.ReadRequest:  # READ
            ack = TftpAckPacket.from_bytes(data)
            if not ack:
                return
            log.info("W#%d << %s:%d: %s" % (self.index, self.peer[0], self.peer[1], str(ack)))
            if ack.block != self.block:
                log.info("W#%d: ignore block %d(not %d)" % (self.index, ack.block, self.block))
                return
            if self.finished:
                log.info("W#%d: got final ack, terminated." % self.index)
                self.server.stop_callback(self.peer, True, "")
                return True  # got the final ack, terminate the session
            try:
                with open(self.filename, "rb") as f:
                    f.seek(self.total_block * self.req.block_size)
                    data = f.read(self.req.block_size)
                    self.total_block += 1
                    self.block = self.total_block % 0x10000
                    self.send(TftpDataPacket(self.block, data))
                    self.server.update_callback(
                        self.peer, (self.total_block - 1) * self.req.block_size + len(data))
                    if len(data) < self.req.block_size:
                        self.finished = True
                        # instead of terminate it immediately,
                        # we wait a short time for retransmission purpose
            except FileNotFoundError as e:
                log.error("W#%d: cannot open file %s" % (self.index, self.filename))
                self.send(TftpErrorPacket(TftpErrCode.FileNotFound, e.strerror))
                return True  # terminated
            except OSError as e:
                log.error("Failed to open file %s:" % self.filename, e)
                self.send(TftpErrorPacket(TftpErrCode.AccessViolation, e.strerror))
                return True  # terminated
        else:  # WRITE
            pkt = TftpDataPacket.from_bytes(data)
            if not pkt:
                return
            log.info("W#%d << %s:%d: %s" % (self.index, self.peer[0], self.peer[1], str(pkt)))
            if pkt.block == self.block:
                log.info("W#%d: retransmit ack" % self.index)
                return self.send(TftpAckPacket(pkt.block), False)  # retransmit ack
            elif pkt.block != ((self.total_block + 1) % 0x10000):
                log.debug("W#%d: ignore block %d(not %d)"
                          % (self.index, pkt.block, (self.total_block + 1) % 0x10000))
                return
            if self.finished:
                log.info("W#%d: finishing session, ignored." % self.index)
                return
            self.total_block += 1
            self.block = self.total_block % 0x10000
            try:
                with open(self.filename, "wb" if self.total_block == 1 else "ab") as f:
                    f.write(pkt.data)
                    self.send(TftpAckPacket(pkt.block))
                    self.server.update_callback(
                        self.peer, (self.total_block-1) * self.req.block_size + len(pkt.data))
                    if len(pkt.data) < self.req.block_size:
                        self.finished = True
                        self.server.stop_callback(self.peer, True, "")
                        # instead of terminate it immediately,
                        # we wait a short time for retransmission purpose
            except OSError as e:
                log.error("Failed to open file %s:" % self.filename, e)
                self.send(TftpErrorPacket(TftpErrCode.AccessViolation, e.strerror))
                return True  # terminated
