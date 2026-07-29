import struct
import zlib


def write_png_direct(pixels_float, width, height, filepath, depth_str):
    """Write Blender's bottom-up RGBA float buffer directly to a PNG file."""
    bit_depth = 16 if depth_str == '16' else 8
    max_val = 65535 if bit_depth == 16 else 255

    raw_rows = bytearray()
    for png_y in range(height):
        raw_rows.append(0)  # PNG filter: None
        blender_y = height - 1 - png_y
        row_start = blender_y * width * 4
        for x in range(width):
            pixel_start = row_start + x * 4
            for channel in range(4):
                value = int(round(max(0.0, min(1.0, pixels_float[pixel_start + channel])) * max_val))
                if bit_depth == 16:
                    raw_rows.extend(struct.pack('>H', value))
                else:
                    raw_rows.append(value)

    ihdr = struct.pack('>IIBBBBB', width, height, bit_depth, 6, 0, 0, 0)
    png = b'\x89PNG\r\n\x1a\n' + _png_chunk(b'IHDR', ihdr)
    png += _png_chunk(b'IDAT', zlib.compress(bytes(raw_rows)))
    png += _png_chunk(b'IEND', b'')

    with open(filepath, 'wb') as file:
        file.write(png)


def _png_chunk(chunk_type, data):
    chunk = chunk_type + data
    checksum = zlib.crc32(chunk) & 0xffffffff
    return struct.pack('>I', len(data)) + chunk + struct.pack('>I', checksum)
