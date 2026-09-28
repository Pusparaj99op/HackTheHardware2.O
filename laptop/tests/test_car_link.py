import asyncio
import socket

from visionpilot.car_link import CarLink
from visionpilot.models import DriveCommand
from visionpilot.protocol import CarState


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def test_link_ok_follows_telemetry_age():
    clock = FakeClock()
    link = CarLink(cmd_port=4210, telem_port=0, telemetry_timeout_s=0.5, clock=clock)
    assert not link.link_ok()
    link.datagram_received(b"T,3,0,7400,0", ("192.168.137.50", 4210))
    assert link.link_ok()
    assert link.car_ip == "192.168.137.50"
    assert link.telemetry.state is CarState.OK
    clock.now += 0.6
    assert not link.link_ok()


def test_malformed_telemetry_ignored():
    link = CarLink(cmd_port=4210, telem_port=0, clock=FakeClock())
    link.datagram_received(b"garbage", ("10.0.0.2", 1))
    assert link.telemetry is None
    assert link.car_ip is None


def test_fixed_car_ip_is_not_overridden():
    link = CarLink(cmd_port=4210, telem_port=0, car_ip="192.168.137.9", clock=FakeClock())
    link.datagram_received(b"T,0,0,0,0", ("192.168.137.77", 4210))
    assert link.car_ip == "192.168.137.9"


def test_roundtrip_over_localhost_udp():
    async def scenario():
        car = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        car.bind(("127.0.0.1", 0))
        car.setblocking(False)
        link = CarLink(cmd_port=car.getsockname()[1], telem_port=0, bind_host="127.0.0.1")
        await link.start()
        try:
            car.sendto(b"T,0,0,7400,1", ("127.0.0.1", link.local_port))
            for _ in range(100):
                if link.telemetry is not None:
                    break
                await asyncio.sleep(0.01)
            assert link.car_ip == "127.0.0.1"
            link.send_drive(DriveCommand(throttle=30, steer=-10))
            link.send_kill()
            loop = asyncio.get_running_loop()
            first = await asyncio.wait_for(loop.sock_recv(car, 64), 1)
            second = await asyncio.wait_for(loop.sock_recv(car, 64), 1)
            assert first == b"D,1,30,-10"
            assert second == b"K"
        finally:
            link.close()
            car.close()

    asyncio.run(scenario())


def test_send_without_known_car_is_a_noop():
    link = CarLink(cmd_port=4210, telem_port=0, clock=FakeClock())
    link.send_drive(DriveCommand(10, 0))  # no transport, no ip: must not raise
    link.send_clear()
