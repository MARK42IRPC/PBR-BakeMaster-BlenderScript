import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
import zlib


MODULE_PATH = Path(__file__).parents[1] / "core" / "png_writer.py"
SPEC = importlib.util.spec_from_file_location("png_writer", MODULE_PATH)
png_writer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(png_writer)


class PngWriterTest(unittest.TestCase):
    def test_writes_blender_rows_top_down_for_8_bit_png(self):
        rows = self._write_and_decode("8")

        self.assertEqual(rows[0], bytes([0, 0, 255, 255] * 2))
        self.assertEqual(rows[1], bytes([255, 0, 0, 255] * 2))

    def test_writes_blender_rows_top_down_for_16_bit_png(self):
        rows = self._write_and_decode("16")
        top_row = struct.unpack(">8H", rows[0])
        bottom_row = struct.unpack(">8H", rows[1])

        self.assertEqual(top_row, (0, 0, 65535, 65535) * 2)
        self.assertEqual(bottom_row, (65535, 0, 0, 65535) * 2)

    def _write_and_decode(self, depth):
        # Blender stores the bottom red row before the top blue row.
        pixels = [
            1.0, 0.0, 0.0, 1.0,
            1.0, 0.0, 0.0, 1.0,
            0.0, 0.0, 1.0, 1.0,
            0.0, 0.0, 1.0, 1.0,
        ]
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "orientation.png"
            png_writer.write_png_direct(pixels, 2, 2, output_path, depth)
            png = output_path.read_bytes()

        idat = bytearray()
        offset = 8
        while offset < len(png):
            length = struct.unpack(">I", png[offset:offset + 4])[0]
            chunk_type = png[offset + 4:offset + 8]
            data_start = offset + 8
            data_end = data_start + length
            if chunk_type == b"IDAT":
                idat.extend(png[data_start:data_end])
            offset = data_end + 4

        raw = zlib.decompress(bytes(idat))
        row_size = 2 * 4 * (2 if depth == "16" else 1)
        rows = []
        offset = 0
        for _ in range(2):
            self.assertEqual(raw[offset], 0)
            rows.append(raw[offset + 1:offset + 1 + row_size])
            offset += row_size + 1
        return rows


if __name__ == "__main__":
    unittest.main()
