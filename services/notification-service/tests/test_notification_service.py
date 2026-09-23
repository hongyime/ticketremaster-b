"""Tests for notification-service's HTTP API and event-publishing helpers.

Redis and Socket.IO's message queue are mocked in conftest.py at import time
(this service has no live broker in the test/CI environment), so these tests
exercise the real Flask routing, request validation, and publish_event logic
against a fake redis client.
"""
from unittest.mock import ANY


def test_health_check(client):
    response = client.get('/health')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload == {'status': 'ok', 'service': 'notification-service'}


def test_broadcast_requires_body(client):
    response = client.post('/broadcast')

    assert response.status_code == 400
    payload = response.get_json()
    assert payload['error']['code'] == 'VALIDATION_ERROR'


def test_broadcast_rejects_empty_body(client):
    response = client.post('/broadcast', json={})

    assert response.status_code == 400
    assert response.get_json()['error']['code'] == 'VALIDATION_ERROR'


def test_broadcast_rejects_unknown_event_type(client):
    response = client.post(
        '/broadcast',
        json={'type': 'not_a_real_channel', 'payload': {'foo': 'bar'}},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload['error']['code'] == 'INVALID_EVENT_TYPE'
    assert 'not_a_real_channel' in payload['error']['message']


def test_broadcast_publishes_known_event_type(client, mock_redis, app_module):
    response = client.post(
        '/broadcast',
        json={
            'type': 'seat_update',
            'payload': {'seatId': 'A1', 'status': 'held'},
            'traceId': 'trace-123',
        },
    )

    assert response.status_code == 200
    assert response.get_json() == {'message': 'Event broadcasted successfully'}

    # publish_event must have gone through the Redis channel mapping for
    # 'seat_update', not just returned 200 without side effects.
    mock_redis.publish.assert_called_once()
    published_channel, published_body = mock_redis.publish.call_args[0]
    assert published_channel == app_module.EVENT_CHANNELS['seat_update']
    assert '"seatId": "A1"' in published_body or 'A1' in published_body


def test_broadcast_accepts_all_declared_event_types(client, mock_redis):
    """Every channel in EVENT_CHANNELS should be accepted, not just one."""
    import app as notification_app

    for event_type in notification_app.EVENT_CHANNELS:
        mock_redis.reset_mock()
        response = client.post('/broadcast', json={'type': event_type, 'payload': {}})
        assert response.status_code == 200, f'{event_type} was rejected'
        mock_redis.publish.assert_called_once()


def test_stats_reports_channels_and_redis_status(client, mock_redis):
    mock_redis.ping.return_value = True

    response = client.get('/stats')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['redis_connected'] is True
    assert set(payload['channels']) == {
        'seat_update', 'ticket_update', 'transfer_update',
        'purchase_update', 'user_update', 'event_update',
    }
    assert isinstance(payload['connected_clients'], int)


def test_notify_seat_update_helper_publishes_seat_channel(mock_redis, app_module):
    app_module.notify_seat_update({'seatId': 'B2', 'status': 'sold'}, trace_id='t-1')

    mock_redis.publish.assert_called_once()
    channel, body = mock_redis.publish.call_args[0]
    assert channel == app_module.EVENT_CHANNELS['seat_update']
    assert 'B2' in body


def test_notify_ticket_update_helper_publishes_ticket_channel(mock_redis, app_module):
    app_module.notify_ticket_update({'ticketId': 'tkt-9'})

    mock_redis.publish.assert_called_once()
    channel, _body = mock_redis.publish.call_args[0]
    assert channel == app_module.EVENT_CHANNELS['ticket_update']
