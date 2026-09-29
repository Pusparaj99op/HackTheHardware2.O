import pytest

from visionpilot.config import load_settings


def test_defaults():
    settings = load_settings({})
    assert settings.net.port == 8443
    assert settings.net.car_ip == "192.168.4.1"  # ESP32 access-point mode
    assert settings.net.discovery_port == 4212
    assert settings.control.override_hold_s == 1.0
    assert settings.net.tls is True
    assert settings.control.speed_cap == 40
    assert settings.follow.stop_distance_m == 0.8


def test_env_overrides():
    settings = load_settings(
        {
            "VP_CAR_IP": "192.168.137.20",
            "VP_PORT": "9000",
            "VP_SPEED_CAP": "25",
            "VP_NO_TLS": "1",
            "VP_SPEED_PER_PCT": "0.02",
            "VP_HEADING_SIGN": "-1",
            "VP_VFOV": "50",
            "VP_YOLO_MODEL": "yolo11s.pt",
        }
    )
    assert settings.net.car_ip == "192.168.137.20"
    assert settings.net.port == 9000
    assert settings.net.tls is False
    assert settings.control.speed_cap == 25
    assert settings.odometry.speed_per_pct == 0.02
    assert settings.odometry.heading_sign == -1
    assert settings.follow.vfov_deg == 50
    assert settings.vision.yolo_model == "yolo11s.pt"


def test_bad_number_fails_fast_with_clear_message():
    with pytest.raises(ValueError, match="VP_SPEED_CAP"):
        load_settings({"VP_SPEED_CAP": "fast"})
