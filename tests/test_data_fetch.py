from unittest import mock
import requests
import data_fetch

class FakeResp:
    def __init__(self, data):
        self._data = data
    def raise_for_status(self):
        pass
    def json(self):
        return self._data

def test_osrm_table_success():
    resp = FakeResp({"distances": [[0, 1], [1, 0]]})
    with mock.patch('data_fetch.session.get', return_value=resp):
        result = data_fetch.osrm_table([(0,0), (1,1)])
        assert result == [[0,1],[1,0]]

def test_osrm_table_fallback():
    def side_effect(url, params=None, timeout=None):
        if 'sources' in params:
            idx = params['sources']
            return FakeResp({"distances": [[idx*10, idx*10 + 1]]})
        raise requests.RequestException('fail')
    with mock.patch('data_fetch.session.get', side_effect=side_effect):
        result = data_fetch.osrm_table([(0,0), (1,1)])
        assert result == [[0,1],[10,11]]
