from visionpilot.protocol import (
    CarState,
    Telemetry,
    bumper_names,
    decode_telemetry,
    encode_clear,
    encode_drive,
    encode_kill,
)


def test_encode_drive_formats_rounded_integers():
    assert encode_drive(7, 40.4, -25.6) == b"D,7,40,-26"


def test_encode_drive_clamps_to_plus_minus_100():
    assert encode_drive(1, 250, -300) == b"D,1,100,-100"


def test_encode_drive_wraps_sequence_to_32_bits():
    assert encode_drive(2**32 + 5, 0, 0) == b"D,5,0,0"


def test_kill_and_clear_packets():
    assert encode_kill() == b"K"
    assert encode_clear() == b"C"


def test_decode_valid_telemetry():
    telem = decode_telemetry(b"T,42,5,7812,2")
    assert telem == Telemetry(seq=42, bumper_mask=5, battery_mv=7812, state=CarState.BUMPER_LOCK)


def test_decode_rejects_garbage():
    assert decode_telemetry(b"hello") is None
    assert decode_telemetry(b"T,1,2") is None
    assert decode_telemetry(b"T,a,b,c,d") is None
    assert decode_telemetry(b"\xff\xfe") is None


def test_decode_rejects_unknown_state():
    assert decode_telemetry(b"T,1,0,0,9") is None


def test_bumper_names_from_mask():
    assert bumper_names(0) == ()
    assert bumper_names(1) == ("left",)
    assert bumper_names(0b110) == ("center", "right")
