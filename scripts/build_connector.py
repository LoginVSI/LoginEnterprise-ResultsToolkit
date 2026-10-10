"""Package independently authored M source; loading/runtime acceptance is separate."""

import argparse
import struct
import zlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def icon(size: int) -> bytes:
    def chunk(kind: bytes, content: bytes) -> bytes:
        return (
            struct.pack(">I", len(content))
            + kind
            + content
            + struct.pack(">I", zlib.crc32(kind + content))
        )

    pixels = b"".join(
        b"\x00"
        + b"".join(
            bytes((37, 99, 235))
            if size // 4 <= x < size // 2
            or (size // 2 <= y < size * 3 // 4 and size // 4 <= x < size * 3 // 4)
            else bytes((23, 32, 51))
            for x in range(size)
        )
        for y in range(size)
    )
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(pixels))
        + chunk(b"IEND", b"")
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("artifacts/ResultsToolkit.mez"))
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(args.out, "w", ZIP_DEFLATED) as archive:
        archive.write(
            Path(__file__).resolve().parents[1] / "adapters/powerbi/ResultsToolkit.pq",
            "ResultsToolkit.pq",
        )
        archive.writestr("icon16.png", icon(16))
        archive.writestr("icon32.png", icon(32))
    print(
        "Packaged M extension. Desktop loading, credential enrollment and refresh are unverified."
    )


if __name__ == "__main__":
    main()
