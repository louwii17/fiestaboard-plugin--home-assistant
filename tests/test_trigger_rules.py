"""Tests for generic Home Assistant page trigger rules."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from plugins.home_assistant import HomeAssistantPlugin
from plugins.home_assistant.trigger_rules import MISSING, resolve_field, rule_matches
from src.plugins.base import PluginResult


def manifest():
    return {
        "id": "home_assistant",
        "name": "Home Assistant",
        "version": "1.3.0",
        "description": "Home Assistant triggers",
        "settings_schema": {},
        "variables": {},
        "supports_triggers": True,
    }


def config(rule, **overrides):
    result = {
        "base_url": "http://ha.local:8123",
        "access_token": "token",
        "trigger_rules": [rule],
    }
    result.update(overrides)
    return result


def data(state="off", **attributes):
    return PluginResult(
        available=True,
        data={
            "connected": "Yes",
            "binary_sensor.front_door": {
                "state": state,
                "friendly_name": "Front Door",
                **attributes,
            },
        },
    )


def test_condition_rule_emits_page_only_priority_trigger():
    plugin = HomeAssistantPlugin(manifest())
    plugin._config = config(
        {
            "id": "door_open",
            "name": "Door open",
            "entity_id": "binary_sensor.front_door",
            "page_id": "page-alert",
            "field": "state",
            "operator": "equals",
            "value": "ON",
            "priority": 100,
            "duration_seconds": 45,
        }
    )

    with patch.object(plugin, "get_data", return_value=data("on")), patch.object(
        plugin, "_render_trigger_page", return_value=["DOOR OPEN"]
    ):
        trigger = plugin.check_triggers()[0]

    assert trigger.trigger_id == "home_assistant:door_open"
    assert trigger.priority == 100
    assert trigger.duration_seconds == 45
    assert trigger.formatted_lines == ["DOOR OPEN"]
    assert trigger.message is None
    assert trigger.data["trigger_name"] == "Door open"
    assert trigger.data["trigger_actual"] == "on"
    assert trigger.data["trigger_expected"] == "ON"
    assert trigger.data["binary_sensor.front_door"]["friendly_name"] == "Front Door"


def test_false_condition_does_not_emit_trigger():
    plugin = HomeAssistantPlugin(manifest())
    plugin._config = config(
        {
            "id": "door_open",
            "entity_id": "binary_sensor.front_door",
            "page_id": "page-alert",
            "operator": "equals",
            "value": "on",
        }
    )

    with patch.object(plugin, "get_data", return_value=data("off")):
        assert plugin.check_triggers() == []


def test_rule_defaults_to_ambient_priority():
    plugin = HomeAssistantPlugin(manifest())
    plugin._config = config(
        {
            "id": "door_open",
            "entity_id": "binary_sensor.front_door",
            "page_id": "page-alert",
            "operator": "equals",
            "value": "on",
        }
    )

    with patch.object(plugin, "get_data", return_value=data("on")), patch.object(
        plugin, "_render_trigger_page", return_value=["DOOR OPEN"]
    ):
        trigger = plugin.check_triggers()[0]

    assert trigger.priority == 10
    assert trigger.data["trigger_rule_id"] == "door_open"
    assert trigger.data["trigger_page_id"] == "page-alert"
    assert trigger.data["trigger_priority"] == 10
    assert trigger.data["trigger_duration_seconds"] == 45


def test_changes_to_fires_once_and_exposes_previous_value():
    plugin = HomeAssistantPlugin(manifest())
    plugin._config = config(
        {
            "id": "door_opened",
            "name": "Door opened",
            "entity_id": "binary_sensor.front_door",
            "page_id": "page-alert",
            "operator": "changes_to",
            "value": "on",
            "duration_seconds": 60,
        }
    )

    with patch.object(plugin, "get_data", return_value=data("off")), patch.object(
        plugin, "_render_trigger_page", return_value=["DOOR OPENED"]
    ):
        assert plugin.check_triggers() == []
    with patch.object(plugin, "get_data", return_value=data("on")), patch.object(
        plugin, "_render_trigger_page", return_value=["DOOR OPENED"]
    ):
        trigger = plugin.check_triggers()[0]
    with patch.object(plugin, "get_data", return_value=data("on")), patch.object(
        plugin, "_render_trigger_page", return_value=["DOOR OPENED"]
    ):
        assert plugin.check_triggers() == []

    assert trigger.duration_seconds == 60
    assert trigger.data["trigger_previous"] == "off"
    assert trigger.data["trigger_actual"] == "on"


def test_nested_attribute_and_numeric_comparisons():
    entity = {"state": "ok", "forecast": {"temperature": 31.5}}
    actual = resolve_field(entity, "forecast.temperature")

    assert actual == 31.5
    assert rule_matches("greater_than", actual, "30")
    assert not rule_matches("less_than_or_equal", actual, "30")
    assert resolve_field(entity, "forecast.missing") is MISSING


def test_one_of_and_exists_operators():
    assert rule_matches("one_of", "open", "on, open, detected")
    assert rule_matches("exists", "anything")
    assert rule_matches("not_exists", MISSING)


def test_validate_config_requires_page_and_valid_rule_values():
    plugin = HomeAssistantPlugin(manifest())
    rule = {
        "id": "front_door",
        "entity_id": "binary_sensor.front_door",
        "page_id": "page-alert",
        "operator": "equals",
        "value": "on",
        "priority": 100,
        "duration_seconds": 45,
    }
    errors = plugin.validate_config(config(dict(rule, page_id="")))
    assert "Trigger rule 1 requires a FiestaBoard page" in errors

    invalid = dict(rule, operator="invalid", priority=0, duration_seconds=5)
    errors = plugin.validate_config(config(invalid))
    assert "Trigger rule 1 has an unsupported operator" in errors
    assert "Trigger rule 1 priority must be between 1 and 100" in errors
    assert "Trigger rule 1 duration must be between 10 and 900 seconds" in errors

    errors = plugin.validate_config(config(rule, trigger_rules={}))
    assert "Trigger rules must be a list" in errors


def test_validate_config_requires_stable_unique_rule_ids():
    plugin = HomeAssistantPlugin(manifest())
    base_rule = {
        "entity_id": "binary_sensor.front_door",
        "page_id": "page-alert",
        "operator": "equals",
        "value": "on",
    }

    errors = plugin.validate_config(config(dict(base_rule, id="Door Open")))
    assert "Trigger rule 1 requires a stable lowercase rule ID" in errors

    duplicate = dict(base_rule, id="door_open")
    errors = plugin.validate_config(config(duplicate, trigger_rules=[duplicate, dict(duplicate)]))
    assert "Trigger rule IDs must be unique: door_open" in errors

    errors = plugin.validate_config(config(dict(base_rule, id="door_open", group_id="Manual Lock")))
    assert "Trigger rule 1 group ID must be a stable lowercase identifier" in errors


def test_mqtt_trigger_check_bypasses_plugin_result_cache():
    plugin = HomeAssistantPlugin(manifest())
    plugin._config = config(
        {
            "id": "door_open",
            "entity_id": "binary_sensor.front_door",
            "page_id": "page-alert",
            "operator": "equals",
            "value": "on",
        },
        mqtt_statestream=True,
    )

    with patch.object(plugin, "_ensure_mqtt_listener", return_value=True), patch.object(
        plugin, "_build_result_from_mqtt", return_value=data("on")
    ) as mqtt_result, patch.object(plugin, "get_data", side_effect=AssertionError("cache used")), patch.object(
        plugin, "_render_trigger_page", return_value=["DOOR OPEN"]
    ):
        trigger = plugin.check_triggers()[0]

    mqtt_result.assert_called_once_with()
    assert trigger.trigger_id == "home_assistant:door_open"


def test_render_failure_does_not_activate_empty_trigger():
    plugin = HomeAssistantPlugin(manifest())
    plugin._config = config(
        {
            "id": "door_open",
            "entity_id": "binary_sensor.front_door",
            "page_id": "missing-page",
            "operator": "equals",
            "value": "on",
        }
    )

    with patch.object(plugin, "get_data", return_value=data("on")), patch.object(
        plugin, "_render_trigger_page", return_value=None
    ):
        assert plugin.check_triggers() == []


def test_selected_page_is_rendered_with_home_assistant_and_plugin_context():
    plugin = HomeAssistantPlugin(manifest())
    page = SimpleNamespace(type="composite")
    rendered = SimpleNamespace(available=True, formatted="NOW PLAYING\nSONG TITLE")
    page_service = MagicMock()
    page_service.get_page.return_value = page
    page_service.render_page.return_value = rendered
    registry = MagicMock()
    registry.build_template_context.return_value = {
        "weather": {"temperature": "21"},
        "home_assistant": {"stale": True},
    }
    trigger_data = {"trigger_name": "Now playing"}

    with patch("src.pages.service.get_page_service", return_value=page_service), patch(
        "src.plugins.get_plugin_registry", return_value=registry
    ):
        lines = plugin._render_trigger_page("page-now-playing", trigger_data)

    assert lines == ["NOW PLAYING", "SONG TITLE"]
    page_service.get_page.assert_called_once_with("page-now-playing")
    page_service.render_page.assert_called_once_with(
        page,
        context={
            "weather": {"temperature": "21"},
            "home_assistant": trigger_data,
        },
    )


def test_rules_render_their_own_pages_and_keep_stable_ids_when_reordered():
    plugin = HomeAssistantPlugin(manifest())
    low = {
        "id": "ambient_door",
        "entity_id": "binary_sensor.front_door",
        "page_id": "page-ambient",
        "operator": "equals",
        "value": "on",
        "priority": 10,
    }
    high = {
        "id": "urgent_door",
        "entity_id": "binary_sensor.front_door",
        "page_id": "page-urgent",
        "operator": "equals",
        "value": "on",
        "priority": 80,
    }
    plugin._config = config(low, trigger_rules=[high, low])

    with patch.object(plugin, "get_data", return_value=data("on")), patch.object(
        plugin,
        "_render_trigger_page",
        side_effect=lambda page_id, trigger_data: [page_id, trigger_data["trigger_rule_id"]],
    ):
        triggers = plugin.check_triggers()

    assert [(trigger.trigger_id, trigger.priority, trigger.formatted_lines) for trigger in triggers] == [
        ("home_assistant:urgent_door", 80, ["page-urgent", "urgent_door"]),
        ("home_assistant:ambient_door", 10, ["page-ambient", "ambient_door"]),
    ]


def test_mutually_exclusive_rules_can_share_a_replacement_group():
    plugin = HomeAssistantPlugin(manifest())
    message = {
        "id": "lock_message",
        "group_id": "manual_lock",
        "entity_id": "binary_sensor.front_door",
        "page_id": "page-message",
        "operator": "equals",
        "value": "on",
        "priority": 100,
    }
    plugin._config = config(message)

    with patch.object(plugin, "get_data", return_value=data("on")), patch.object(
        plugin, "_render_trigger_page", return_value=["LOCKED MESSAGE"]
    ):
        trigger = plugin.check_triggers()[0]

    assert trigger.trigger_id == "home_assistant:manual_lock"
    assert trigger.data["trigger_rule_id"] == "lock_message"
    assert trigger.data["trigger_group_id"] == "manual_lock"
