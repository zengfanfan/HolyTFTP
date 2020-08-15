import os
from struct import pack, unpack
from ..log import log
from ..config import cfg

SUPPORTED_OPTIONS = ["blksize", "tsize", "timeout"]
DEFAULT_BLOCK_SIZE = 512
TFTP_TIMEOUT = 5


class TftpOpCode:
    ReadRequest = 1
    WriteRequest = 2
    Data = 3
    Acknowledgment = 4
    Error = 5
    OptionAcknowledgment = 6

    # aliases
    RRQ = ReadRequest
    WRQ = WriteRequest
    ACK = Acknowledgment
    OACK = OptionAcknowledgment

    @classmethod
    def str(cls, code):
        if code == cls.ReadRequest:
            return "ReadRequest"
        if code == cls.WriteRequest:
            return "WriteRequest"
        if code == cls.Data:
            return "Data"
        if code == cls.Acknowledgment:
            return "ACK"
        if code == cls.Error:
            return "Error"
        if code == cls.OptionAcknowledgment:
            return "OACK"
        return "Unknown<%d>" % code


class TftpErrCode:
    Undefined = 0
    FileNotFound = 1
    AccessViolation = 2
    DiskFull = 3  # Disk full or allocation exceeded
    IllegalOperation = 4
    UnknownTID = 5
    FileExists = 6
    NoSuchUser = 7
    OptionError = 8

    @classmethod
    def str(cls, code):
        if code == cls.Undefined:
            return "Undefined"
        if code == cls.FileNotFound:
            return "FileNotFound"
        if code == cls.AccessViolation:
            return "AccessViolation"
        if code == cls.DiskFull:
            return "DiskFull"
        if code == cls.IllegalOperation:
            return "IllegalOperation"
        if code == cls.UnknownTID:
            return "UnknownTID"
        if code == cls.FileExists:
            return "FileExists"
        if code == cls.NoSuchUser:
            return "NoSuchUser"
        return "Unknown<%d>" % code


class TftpReqPacket(object):
    """
     2 bytes     string    1 byte     string   1 byte
     ------------------------------------------------
    | Opcode |  Filename  |   0  |    Mode    |   0  |
     ------------------------------------------------
    """

    def __init__(self, raw):
        self.raw = raw
        self.code = 0
        self.filename = None
        self.mode = None
        self.options = {}
        self.accepted_options = {}
        self.block_size = DEFAULT_BLOCK_SIZE
        self.timeout = 0
        self.tsize = 0  # transfer size

    def __str__(self):
        s = "<%s>" % TftpOpCode.str(self.code)
        s += " M=" + str(self.mode)
        s += " F=" + str(self.filename)
        if self.options:
            s += " OPN=%d" % len(self.options)
        return s

    def parse(self):
        if len(self.raw) < 6:
            log.debug("data too short:", len(self.raw))
            return False

        self.code, = unpack("!H", self.raw[:2])
        if self.code not in [TftpOpCode.ReadRequest, TftpOpCode.WriteRequest]:
            log.debug("Illegal Operation", self.code)
            return TftpErrCode.IllegalOperation, "Illegal Operation"

        opname = None
        for s in self.raw[2:-1].decode().split("\0"):
            if self.filename is None:
                self.filename = s
            elif self.mode is None:
                self.mode = s
            elif opname is None:
                opname = s
            else:
                self.options[opname] = s
                if opname in SUPPORTED_OPTIONS:
                    self.accepted_options[opname] = s
                opname = None

        if not self.filename:
            log.debug("Illegal Filename", self.filename)
            return TftpErrCode.AccessViolation, "Illegal Filename"
        if self.mode.lower() not in ["netascii", "octet"]:
            log.debug("Illegal Mode", self.mode)
            return TftpErrCode.Undefined, "Unsupported Mode " + self.mode

        for opt in self.accepted_options:
            opt_lower = opt.lower()
            value = self.accepted_options[opt]
            if opt_lower == "blksize" and value.isdigit():
                self.block_size = int(value)
                if self.block_size < 8 or self.block_size > 65464:
                    self.block_size = DEFAULT_BLOCK_SIZE
                    self.accepted_options[opt] = str(self.block_size)
            elif opt_lower == "timeout" and value.isdigit():
                self.timeout = int(value)
                if not 1 <= self.timeout <= 255:
                    self.timeout = TFTP_TIMEOUT
                else:
                    self.accepted_options[opt] = str(self.timeout)
            elif opt_lower == "tsize" and value.isdigit():
                if self.code == TftpOpCode.ReadRequest:
                    try:
                        path = cfg.get_real_path(self.filename)
                        self.tsize = os.path.getsize(path)
                    except OSError:
                        self.tsize = 0
                else:
                    self.tsize = int(value)
                self.accepted_options[opt] = str(self.tsize)

        return True


class TftpDataPacket(object):
    """
     2 bytes     2 bytes      n bytes
     ----------------------------------
    | Opcode |   Block #  |   Data     |
     ----------------------------------
    """
    def __init__(self, block, data):
        self.code = TftpOpCode.Data
        self.block = block
        self.data = data
        if type(self.data) is not bytes:
            self.data = str(self.data).encode()

    def __str__(self):
        s = "<%s>" % TftpOpCode.str(self.code)
        s += " N=%d" % self.block
        s += " L=%d" % len(self.data)
        return s

    @classmethod
    def from_bytes(cls, raw):
        if len(raw) < 4:
            log.error("data too short:", len(raw))
            return None
        code, block = unpack("!HH", raw[:4])
        if code != TftpOpCode.Data:
            log.error("invalid code %d" % code)
            return None
        return cls(block, raw[4:])

    def __bytes__(self):
        s = pack("!HH", self.code, self.block)
        return s + self.data


class TftpAckPacket(object):
    """
     2 bytes     2 bytes
     ---------------------
    | Opcode |   Block #  |
     ---------------------
    """
    def __init__(self, block):
        self.code = TftpOpCode.ACK
        self.options = {}
        self.block = block

    def __str__(self):
        s = "<%s>" % TftpOpCode.str(self.code)
        s += " N=%d" % self.block
        if self.options:
            s += " OPN=%d" % len(self.options)
        return s

    @classmethod
    def from_previous_packet(cls, pkt):
        if type(pkt) is TftpReqPacket:
            block = 0
        elif type(pkt) is TftpDataPacket:
            block = pkt.block
        else:
            log.error("type of previous packet is invalid:", type(pkt))
            return None
        p = cls(block)
        if pkt.accepted_options:
            p.options = pkt.accepted_options
            p.code = TftpOpCode.OACK
        return p

    @classmethod
    def from_bytes(cls, raw):
        if type(raw) is not bytes or len(raw) < 4:
            log.error("data too short:", len(raw))
            return None
        code, block = unpack("!HH", raw[:4])
        if code not in [TftpOpCode.ACK, TftpOpCode.OACK]:
            log.error("code is not ack:", code)
            return None

        p = cls(block)
        p.parse_options(raw[4:-1])
        return p

    def parse_options(self, opt_raw):
        opname = None
        for s in opt_raw.decode().split("\0"):
            if opname is None:
                opname = s
            else:
                if opname in SUPPORTED_OPTIONS:
                    self.options[opname] = s
                opname = None

        if self.options:
            self.code = TftpOpCode.OACK

    def __bytes__(self):
        if self.code == TftpOpCode.ACK:
            s = pack("!HH", self.code, self.block)
        else:  # OACK
            s = pack("!H", self.code)
        for opt in self.options:
            s += (opt + "\0").encode()
            s += (self.options[opt] + "\0").encode()
        return s


class TftpErrorPacket(object):
    """
     2 bytes     2 bytes      string    1 byte
     -----------------------------------------
    | Opcode |  ErrorCode |   ErrMsg   |   0  |
     -----------------------------------------
    """
    def __init__(self, code, msg=""):
        self.code = TftpOpCode.Error
        self.errcode = code
        self.msg = msg or TftpErrCode.str(code)

    def __str__(self):
        s = "<%s>" % TftpOpCode.str(self.code)
        s += " E=%d/%s" % (self.errcode, TftpErrCode.str(self.errcode))
        s += " M='%s'" % self.msg
        return s

    @classmethod
    def from_bytes(cls, raw):
        if len(raw) < 4:
            log.error("data too short:", len(raw))
            return None
        code, errcode = unpack("!HH", raw[:4])
        if code != TftpOpCode.Error:
            log.error("code is not error:", code)
            return None
        msg = raw[4:-1].decode()
        return cls(errcode, msg)

    def __bytes__(self):
        s = pack("!HH", self.code, self.errcode)
        return s + (self.msg + "\0").encode()
