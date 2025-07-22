import pytest
from unittest import mock

pytest.importorskip("aiohttp")
import async_fetch


class FakeResp:
    def __init__(self, data):
        self._data = data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    def raise_for_status(self):
        pass

    async def json(self):
        return self._data


@pytest.mark.asyncio
async def test_osrm_table_async_success():
    resp = FakeResp({"distances": [[0, 1], [1, 0]]})

    class FakeSession:
        async def get(self, *args, **kwargs):
            return resp

    with mock.patch("async_fetch.get_session", return_value=FakeSession()):
        result = await async_fetch.osrm_table_async([(0, 0), (1, 1)])
        assert result == [[0, 1], [1, 0]]


@pytest.mark.asyncio
async def test_osrm_table_async_fallback():
    async def fake_get(url, params=None, timeout=None):
        if params and "sources" in params:
            idx = params["sources"]
            return FakeResp({"distances": [[idx * 10, idx * 10 + 1]]})
        raise aiohttp.ClientError("fail")

    class FakeSession:
        async def get(self, url, params=None, timeout=None):
            return await fake_get(url, params=params, timeout=timeout)

    with mock.patch("async_fetch.get_session", return_value=FakeSession()):
        result = await async_fetch.osrm_table_async([(0, 0), (1, 1)])
        assert result == [[0, 1], [10, 11]]
