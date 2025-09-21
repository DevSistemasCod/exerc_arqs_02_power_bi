import ure as re
import ustruct as struct
import urandom as random
import ubinascii
import uhashlib
from ucollections import namedtuple
from micropython import const

# Função simples de log para debug
def log_debug(*args):
    print("[DEBUG]", *args)

# Opcodes
OP_CONT = const(0x0)
OP_TEXT = const(0x1)
OP_BYTES = const(0x2)
OP_CLOSE = const(0x8)
OP_PING = const(0x9)
OP_PONG = const(0xa)

# Close codes
CLOSE_OK = const(1000)
CLOSE_GOING_AWAY = const(1001)
CLOSE_PROTOCOL_ERROR = const(1002)
CLOSE_DATA_NOT_SUPPORTED = const(1003)
CLOSE_BAD_DATA = const(1007)
CLOSE_POLICY_VIOLATION = const(1008)
CLOSE_TOO_BIG = const(1009)
CLOSE_MISSING_EXTN = const(1010)
CLOSE_BAD_CONDITION = const(1011)

URL_RE = re.compile(r'(wss|ws)://([A-Za-z0-9-\.]+)(?:\:([0-9]+))?(/.+)?')
URI = namedtuple('URI', ('protocol', 'hostname', 'port', 'path'))

class NoDataException(Exception):
    pass

class ConnectionClosed(Exception):
    pass

def urlparse(uri):
    """Parse ws:// URLs"""
    match = URL_RE.match(uri)
    if match:
        protocol = match.group(1)
        host = match.group(2)
        port = match.group(3)
        path = match.group(4)

        if protocol == 'wss':
            if port is None:
                port = 443
        elif protocol == 'ws':
            if port is None:
                port = 80
        else:
            raise ValueError('Scheme {} is invalid'.format(protocol))

        return URI(protocol, host, int(port), path)

async def websocket_handshake(client_reader, client_writer):
    try:
        request = (await client_reader.read(1024)).decode('utf-8')
        print("Requisição recebida:", request)  # Depuração
        headers = {}
        for line in request.split("\r\n")[1:]:
            if ": " in line:
                key, value = line.split(": ", 1)
                headers[key.lower()] = value

        key = headers.get("sec-websocket-key")
        if not key:
            print("Erro: sec-websocket-key não encontrado")
            return False

        GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
        accept = ubinascii.b2a_base64(
            uhashlib.sha1((key + GUID).encode()).digest()
        ).decode().strip()

        response = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
        )
        client_writer.write(response.encode())
        await client_writer.drain()
        print("Handshake enviado com sucesso")
        return True
    except Exception as e:
        print("Erro no handshake:", e)
        return False

class Websocket:
    """Basis of the Websocket protocol for ESP32 with uasyncio streams"""

    is_client = False

    def __init__(self, reader, writer):
        self.reader = reader
        self.writer = writer
        self.open = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def settimeout(self, timeout):
        pass

    async def recv_nowait(self):
        """Recebe mensagem se houver, senão retorna None"""
        if not self.open:
            return None
        try:
            return await self.recv()
        except Exception:
            return None

    async def read_frame(self, max_size=1024):
        """Read a frame from the stream"""
        try:
            two_bytes = await self.reader.readexactly(2)
            if not two_bytes:
                raise NoDataException
        except Exception:
            raise NoDataException

        byte1, byte2 = struct.unpack('!BB', two_bytes)

        fin = bool(byte1 & 0x80)
        opcode = byte1 & 0x0f

        mask = bool(byte2 & (1 << 7))
        length = byte2 & 0x7f

        if length == 126:
            length, = struct.unpack('!H', await self.reader.readexactly(2))
        elif length == 127:
            length, = struct.unpack('!Q', await self.reader.readexactly(8))

        if max_size is not None and length > max_size:
            log_debug("Frame too big, closing")
            self.close(code=CLOSE_TOO_BIG)
            return True, OP_CLOSE, None

        if mask:
            mask_bits = await self.reader.readexactly(4)

        try:
            data = await self.reader.readexactly(length)
        except MemoryError:
            log_debug("Frame too big, closing")
            self.close(code=CLOSE_TOO_BIG)
            return True, OP_CLOSE, None
        except Exception:
            raise NoDataException

        if mask:
            data = bytes(b ^ mask_bits[i % 4] for i, b in enumerate(data))

        return fin, opcode, data

    async def write_frame(self, opcode, data=b''):
        """Write a frame to the stream"""
        fin = True
        mask = self.is_client

        length = len(data)
        byte1 = 0x80 if fin else 0
        byte1 |= opcode
        byte2 = 0x80 if mask else 0

        if length < 126:
            byte2 |= length
            self.writer.write(struct.pack('!BB', byte1, byte2))
        elif length < (1 << 16):
            byte2 |= 126
            self.writer.write(struct.pack('!BBH', byte1, byte2, length))
        elif length < (1 << 64):
            byte2 |= 127
            self.writer.write(struct.pack('!BBQ', byte1, byte2, length))
        else:
            raise ValueError()

        if mask:
            mask_bits = struct.pack('!I', random.getrandbits(32))
            self.writer.write(mask_bits)
            data = bytes(b ^ mask_bits[i % 4] for i, b in enumerate(data))

        self.writer.write(data)
        await self.writer.drain()

    async def recv(self):
        """Receive data from the websocket"""
        assert self.open

        while self.open:
            try:
                fin, opcode, data = await self.read_frame()
            except NoDataException:
                return None
            except ValueError:
                log_debug("Failed to read frame. Stream dead.")
                self._close()
                raise ConnectionClosed()

            if not fin:
                raise NotImplementedError()

            if opcode == OP_TEXT:
                return data.decode('utf-8')
            elif opcode == OP_BYTES:
                return data
            elif opcode == OP_CLOSE:
                self._close()
                return
            elif opcode == OP_PONG:
                continue
            elif opcode == OP_PING:
                log_debug("Sending PONG")
                await self.write_frame(OP_PONG, data)
                continue
            elif opcode == OP_CONT:
                raise NotImplementedError(opcode)
            else:
                raise ValueError(opcode)

    async def send(self, buf):
        """Send data to the websocket"""
        assert self.open

        if isinstance(buf, str):
            opcode = OP_TEXT
            buf = buf.encode('utf-8')
        elif isinstance(buf, bytes):
            opcode = OP_BYTES
        else:
            raise TypeError()

        await self.write_frame(opcode, buf)

    def close(self, code=CLOSE_OK, reason=''):
        """Close the websocket"""
        if not self.open:
            return

        buf = struct.pack('!H', code) + reason.encode('utf-8')
        asyncio.create_task(self.write_frame(OP_CLOSE, buf))
        self._close()

    def _close(self):
        log_debug("Connection closed")
        self.open = False
        asyncio.create_task(self._async_close_writer())

    async def _async_close_writer(self):
        try:
            self.writer.close()
            await self.writer.wait_closed()
        except Exception:
            pass
