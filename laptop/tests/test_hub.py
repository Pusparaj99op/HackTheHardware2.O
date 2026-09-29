import asyncio

from visionpilot.app import Hub


class FakeSocket:
    def __init__(self, name):
        self.name = name
        self.bytes_sent = []
        self.text_sent = []

    async def send_bytes(self, data):
        self.bytes_sent.append(data)

    async def send_text(self, text):
        self.text_sent.append(text)


def test_newest_phone_is_the_active_camera():
    hub = Hub()
    chrome, app = FakeSocket("chrome"), FakeSocket("app")
    hub.add_phone(chrome)
    assert hub.is_active_camera(chrome)
    hub.add_phone(app)
    assert hub.is_active_camera(app)
    assert not hub.is_active_camera(chrome)


def test_active_camera_falls_back_when_it_disconnects():
    hub = Hub()
    first, second = FakeSocket("1"), FakeSocket("2")
    hub.add_phone(first)
    hub.add_phone(second)
    hub.remove_phone(second)
    assert hub.is_active_camera(first)
    hub.remove_phone(first)
    assert not hub.has_phones
    hub.remove_phone(first)  # double remove is harmless


def test_frames_only_go_to_dashboards_that_want_them():
    async def scenario():
        hub = Hub()
        viewer, controller = FakeSocket("viewer"), FakeSocket("controller")
        hub.add_dashboard(viewer, frames=True)
        hub.add_dashboard(controller, frames=False)
        hub.push_frame(b"jpeg")
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert viewer.bytes_sent == [b"jpeg"]
        assert controller.bytes_sent == []
        assert hub.has_dashboards

    asyncio.run(scenario())


def test_broadcast_reaches_dashboards_and_phones():
    async def scenario():
        hub = Hub()
        dash, phone = FakeSocket("dash"), FakeSocket("phone")
        hub.add_dashboard(dash, frames=False)
        hub.add_phone(phone)
        await hub.broadcast({"type": "state"})
        assert dash.text_sent and phone.text_sent
        hub.remove_dashboard(dash)
        assert not hub.has_dashboards

    asyncio.run(scenario())
