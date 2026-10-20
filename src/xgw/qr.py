"""QR-код для ссылки: карточка «Tailscale» показывает ссылку входа и квадратом, чтобы её
можно было открыть телефоном. Внешних библиотек нет — код небольшой: байтовый режим,
уровень коррекции M, версии 1–10 (до 213 байт), маска — с наименьшим штрафом.

Алгоритм — по стандарту ISO/IEC 18004 в изложении Project Nayuki («QR Code generator
library»); тест сверяет результат с его эталонными матрицами.
"""

from __future__ import annotations

# Уровень M, версии 1–10: байтов коррекции в блоке и число блоков.
_ECC_PER_BLOCK = (0, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26)
_BLOCKS = (0, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5)
_FORMAT_M = 0  # биты уровня M в поле формата
MAX_VERSION = 10


class TooLong(ValueError):
    """Текст не помещается в QR-код версии MAX_VERSION."""


def _raw_modules(version: int) -> int:
    result = (16 * version + 128) * version + 64
    if version >= 2:
        count = version // 7 + 2
        result -= (25 * count - 10) * count - 55
        if version >= 7:
            result -= 36
    return result


def _data_codewords(version: int) -> int:
    return _raw_modules(version) // 8 - _ECC_PER_BLOCK[version] * _BLOCKS[version]


def _multiply(x: int, y: int) -> int:
    """Умножение в GF(2^8) по модулю x^8 + x^4 + x^3 + x^2 + 1."""
    z = 0
    for i in range(7, -1, -1):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _divisor(degree: int) -> list[int]:
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(len(result)):
            result[j] = _multiply(result[j], root)
            if j + 1 < len(result):
                result[j] ^= result[j + 1]
        root = _multiply(root, 0x02)
    return result


def _remainder(data: list[int], divisor: list[int]) -> list[int]:
    result = [0] * len(divisor)
    for byte in data:
        factor = byte ^ result.pop(0)
        result.append(0)
        for i, coefficient in enumerate(divisor):
            result[i] ^= _multiply(coefficient, factor)
    return result


def _codewords(data: bytes) -> tuple[int, list[int]]:
    """Версия и байты для размещения: данные с заполнением, коррекция, чередование блоков."""
    for version in range(1, MAX_VERSION + 1):
        count_bits = 8 if version < 10 else 16
        capacity = _data_codewords(version) * 8
        if 4 + count_bits + 8 * len(data) <= capacity:
            break
    else:
        raise TooLong(f"для QR-кода текст длиннее {_data_codewords(MAX_VERSION) - 3} байт")
    bits: list[int] = []

    def put(value: int, length: int) -> None:
        bits.extend((value >> i) & 1 for i in range(length - 1, -1, -1))

    put(0x4, 4)  # байтовый режим
    put(len(data), count_bits)
    for byte in data:
        put(byte, 8)
    put(0, min(4, capacity - len(bits)))
    put(0, -len(bits) % 8)
    pad = 0xEC
    while len(bits) < capacity:
        put(pad, 8)
        pad ^= 0xEC ^ 0x11
    words = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]

    blocks_count, ecc_len = _BLOCKS[version], _ECC_PER_BLOCK[version]
    raw = _raw_modules(version) // 8
    short_count = blocks_count - raw % blocks_count
    short_len = raw // blocks_count
    divisor = _divisor(ecc_len)
    blocks: list[list[int]] = []
    start = 0
    for i in range(blocks_count):
        size = short_len - ecc_len + (0 if i < short_count else 1)
        block = words[start:start + size]
        start += size
        ecc = _remainder(block, divisor)
        if i < short_count:
            block.append(0)
        blocks.append(block + ecc)
    result = []
    for i in range(len(blocks[0])):
        for j, block in enumerate(blocks):
            if i != short_len - ecc_len or j >= short_count:
                result.append(block[i])
    return version, result


class _Matrix:
    def __init__(self, version: int) -> None:
        self.version = version
        self.size = version * 4 + 17
        self.dark = [[False] * self.size for _ in range(self.size)]
        self.fixed = [[False] * self.size for _ in range(self.size)]

    def set(self, x: int, y: int, dark: bool) -> None:
        self.dark[y][x] = dark
        self.fixed[y][x] = True

    def function_patterns(self) -> None:
        size = self.size
        for i in range(size):
            self.set(6, i, i % 2 == 0)
            self.set(i, 6, i % 2 == 0)
        for x, y in ((3, 3), (size - 4, 3), (3, size - 4)):
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    if 0 <= x + dx < size and 0 <= y + dy < size:
                        self.set(x + dx, y + dy, max(abs(dx), abs(dy)) not in (2, 4))
        positions = self._alignment()
        last = len(positions) - 1
        for i, x in enumerate(positions):
            for j, y in enumerate(positions):
                if (i, j) in ((0, 0), (0, last), (last, 0)):
                    continue  # углы с поисковыми узорами
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self.set(x + dx, y + dy, max(abs(dx), abs(dy)) != 1)
        self.format_bits(0)
        self.version_bits()

    def _alignment(self) -> list[int]:
        if self.version == 1:
            return []
        count = self.version // 7 + 2
        step = (self.version * 8 + count * 3 + 5) // (count * 4 - 4) * 2
        result = [6]
        position = self.size - 7
        while len(result) < count:
            result.insert(1, position)
            position -= step
        return result

    def format_bits(self, mask: int) -> None:
        data = _FORMAT_M << 3 | mask
        rem = data
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits = (data << 10 | rem) ^ 0x5412
        bit = [(bits >> i) & 1 == 1 for i in range(15)]
        size = self.size
        for i in range(6):
            self.set(8, i, bit[i])
        self.set(8, 7, bit[6])
        self.set(8, 8, bit[7])
        self.set(7, 8, bit[8])
        for i in range(9, 15):
            self.set(14 - i, 8, bit[i])
        for i in range(8):
            self.set(size - 1 - i, 8, bit[i])
        for i in range(8, 15):
            self.set(8, size - 15 + i, bit[i])
        self.set(8, size - 8, True)

    def version_bits(self) -> None:
        if self.version < 7:
            return
        rem = self.version
        for _ in range(12):
            rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
        bits = self.version << 12 | rem
        for i in range(18):
            dark = (bits >> i) & 1 == 1
            a, b = self.size - 11 + i % 3, i // 3
            self.set(a, b, dark)
            self.set(b, a, dark)

    def codewords(self, data: list[int]) -> None:
        size, i = self.size, 0
        right = size - 1
        while right >= 1:
            if right == 6:
                right = 5
            upward = ((right + 1) & 2) == 0
            for vert in range(size):
                y = size - 1 - vert if upward else vert
                for j in range(2):
                    x = right - j
                    if not self.fixed[y][x] and i < len(data) * 8:
                        self.dark[y][x] = (data[i >> 3] >> (7 - (i & 7))) & 1 == 1
                        i += 1
            right -= 2

    def apply_mask(self, mask: int) -> None:
        for y in range(self.size):
            for x in range(self.size):
                if self.fixed[y][x]:
                    continue
                if mask == 0:
                    invert = (x + y) % 2 == 0
                elif mask == 1:
                    invert = y % 2 == 0
                elif mask == 2:
                    invert = x % 3 == 0
                elif mask == 3:
                    invert = (x + y) % 3 == 0
                elif mask == 4:
                    invert = (x // 3 + y // 2) % 2 == 0
                elif mask == 5:
                    invert = x * y % 2 + x * y % 3 == 0
                elif mask == 6:
                    invert = (x * y % 2 + x * y % 3) % 2 == 0
                else:
                    invert = ((x + y) % 2 + x * y % 3) % 2 == 0
                if invert:
                    self.dark[y][x] = not self.dark[y][x]

    def penalty(self) -> int:
        size, result = self.size, 0
        for line in (self.dark, [list(column) for column in zip(*self.dark, strict=True)]):
            for row in line:
                color, run, history = False, 0, [0] * 7
                for dark in row:
                    if dark == color:
                        run += 1
                        if run == 5:
                            result += 3
                        elif run > 5:
                            result += 1
                    else:
                        self._history(run, history)
                        if not color:
                            result += self._finders(history) * 40
                        color, run = dark, 1
                if color:
                    self._history(run, history)
                    run = 0
                self._history(run + size, history)
                result += self._finders(history) * 40
        for y in range(size - 1):
            for x in range(size - 1):
                color = self.dark[y][x]
                if color == self.dark[y][x + 1] == self.dark[y + 1][x] == self.dark[y + 1][x + 1]:
                    result += 3
        dark = sum(sum(row) for row in self.dark)
        total = size * size
        k = -(-abs(dark * 20 - total * 10) // total) - 1  # ceil
        return result + k * 10

    def _history(self, run: int, history: list[int]) -> None:
        if history[0] == 0:
            run += self.size  # светлая рамка вокруг кода
        history.pop()
        history.insert(0, run)

    @staticmethod
    def _finders(history: list[int]) -> int:
        n = history[1]
        core = n > 0 and history[2] == history[4] == history[5] == n and history[3] == n * 3
        return (int(core and history[0] >= n * 4 and history[6] >= n)
                + int(core and history[6] >= n * 4 and history[0] >= n))


def encode(text: str) -> list[str]:
    """Строки матрицы QR-кода: «1» — тёмный модуль. Рамку вокруг рисует страница."""
    version, data = _codewords(text.encode("utf-8"))
    matrix = _Matrix(version)
    matrix.function_patterns()
    matrix.codewords(data)
    best, score = 0, None
    for mask in range(8):
        matrix.apply_mask(mask)
        matrix.format_bits(mask)
        penalty = matrix.penalty()
        if score is None or penalty < score:
            best, score = mask, penalty
        matrix.apply_mask(mask)
    matrix.apply_mask(best)
    matrix.format_bits(best)
    return ["".join("1" if dark else "0" for dark in row) for row in matrix.dark]
