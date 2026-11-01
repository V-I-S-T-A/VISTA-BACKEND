import importlib
from unittest import IsolatedAsyncioTestCase
from django.test import override_settings
from channels.testing import WebsocketCommunicator


class BrowserWebSocketOriginTests(IsolatedAsyncioTestCase):
    def application(self):
        from vista import asgi
        return importlib.reload(asgi).application

    @override_settings(ALLOWED_HOSTS=['api.example.test'], CORS_ALLOWED_ORIGINS=['https://web.example.test'])
    async def test_existing_api_origin_remains_accepted(self):
        socket = WebsocketCommunicator(self.application(), '/ws/notifications/', headers=[
            (b'origin', b'https://api.example.test'),
        ])
        self.assertTrue((await socket.connect())[0])
        await socket.disconnect()

    @override_settings(ALLOWED_HOSTS=['api.example.test'], CORS_ALLOWED_ORIGINS=['https://web.example.test'])
    async def test_frontend_origin_is_allowed_even_when_it_is_not_an_api_host(self):
        socket = WebsocketCommunicator(self.application(), '/ws/notifications/', headers=[
            (b'host', b'api.example.test'), (b'origin', b'https://web.example.test'),
        ])
        connected, _ = await socket.connect()
        self.assertTrue(connected)
        await socket.send_json_to({'token': 'invalid'})
        close = await socket.receive_output()
        self.assertEqual(close['type'], 'websocket.close')
        self.assertEqual(close['code'], 4401)
        await socket.disconnect()

    @override_settings(ALLOWED_HOSTS=['api.example.test'], CORS_ALLOWED_ORIGINS=['https://web.example.test'])
    async def test_untrusted_and_lookalike_browser_origins_are_rejected(self):
        application = self.application()
        for origin in [b'https://untrusted.example', b'https://web.example.test.evil.test', b'http://web.example.test']:
            socket = WebsocketCommunicator(application, '/ws/notifications/', headers=[(b'origin', origin)])
            self.assertFalse((await socket.connect())[0])
            await socket.disconnect()

    @override_settings(
        ALLOWED_HOSTS=['vista-backend-production-10d7.up.railway.app'],
        CORS_ALLOWED_ORIGINS=['https://vista-ustp.up.railway.app', 'https://vista-web-production-4086.up.railway.app'],
    )
    async def test_both_approved_railway_web_origins_reach_the_jwt_handshake(self):
        application = self.application()
        for origin in ['https://vista-ustp.up.railway.app', 'https://vista-web-production-4086.up.railway.app']:
            socket = WebsocketCommunicator(application, '/ws/notifications/', headers=[('origin'.encode(), origin.encode())])
            self.assertTrue((await socket.connect())[0])
            await socket.send_json_to({'token': 'invalid'})
            self.assertEqual((await socket.receive_output())['code'], 4401)
            await socket.disconnect()
