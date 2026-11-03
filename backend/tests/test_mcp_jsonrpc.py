"""JSON-RPC 2.0 messages (research §1)."""

from agent_lab.mcp import jsonrpc


def test_builders() -> None:
    assert jsonrpc.request(1, "tools/list", {"cursor": "x"}) == {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {"cursor": "x"},
    }
    assert jsonrpc.notification("notifications/initialized") == {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
    }
    assert jsonrpc.result(2, {"a": 1}) == {"jsonrpc": "2.0", "id": 2, "result": {"a": 1}}
    assert jsonrpc.error(3, -32601, "no", {"x": 1}) == {
        "jsonrpc": "2.0",
        "id": 3,
        "error": {"code": -32601, "message": "no", "data": {"x": 1}},
    }
    assert "data" not in jsonrpc.error(3, -32601, "no")["error"]


def test_kinds() -> None:
    req = jsonrpc.request(1, "m")
    note = jsonrpc.notification("m")
    res = jsonrpc.result(1, {})
    assert jsonrpc.is_request(req) and not jsonrpc.is_request(note)
    assert jsonrpc.is_notification(note) and not jsonrpc.is_notification(req)
    assert jsonrpc.is_response(res) and jsonrpc.is_response(jsonrpc.error(1, -1, "x"))
    assert not jsonrpc.is_response(req)
    invalid: list[object] = [
        {"id": 1, "method": "m"},
        {"jsonrpc": "1.0", "id": 1, "result": {}},
        [1],
    ]
    for message in invalid:
        assert not (
            jsonrpc.is_request(message)
            or jsonrpc.is_notification(message)
            or jsonrpc.is_response(message)
        )
