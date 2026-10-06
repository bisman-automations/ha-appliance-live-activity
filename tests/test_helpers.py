"""Unit tests for pure helpers and GE discovery."""
from custom_components.appliance_live_activity.const import (
    DEFAULT_IDLE_STATES,
    STATUS_COMPLETE,
    STATUS_IDLE,
    STATUS_PAUSED,
    STATUS_RUNNING,
)
from custom_components.appliance_live_activity.ge import discover_from_entity_ids
from custom_components.appliance_live_activity.helpers import (
    classify_state,
    color_to_hex,
    hex_to_rgb,
    meaningful,
    to_minutes,
)


def _classify(state, **kw):
    args = dict(
        active=["Run", "Cycle Active"],
        paused=["Pause"],
        complete=["End Of Cycle", "Done"],
        idle=DEFAULT_IDLE_STATES,
    )
    args.update(kw)
    return classify_state(state, **args)


def test_classify():
    assert _classify("Off") == STATUS_IDLE
    assert _classify("unavailable") == STATUS_IDLE
    assert _classify("Cycle Active") == STATUS_RUNNING
    assert _classify("cycle active") == STATUS_RUNNING
    assert _classify("Paused") == STATUS_PAUSED
    assert _classify("End Of Cycle") == STATUS_COMPLETE
    assert _classify("Bake") == STATUS_RUNNING  # unknown -> running
    assert _classify("Bake", unknown_is_running=False) == STATUS_IDLE
    assert _classify("Run", done_signal=True) == STATUS_COMPLETE
    assert _classify("Delay Run") == STATUS_IDLE


def test_to_minutes():
    assert to_minutes("4.5", "h") == 270
    assert to_minutes("61.8", "min") == 61.8
    assert to_minutes("120", "s") == 2
    assert to_minutes("1:30:00", None) == 90
    assert to_minutes("unknown", "min") == 0
    assert to_minutes(None, "min") == 0


def test_meaningful():
    assert meaningful("---") == ""
    assert meaningful("N/A") == ""
    assert meaningful("Rinse") == "Rinse"


# Entity ids exactly as exposed by ha_gehome on a real install
WASHER = [
    "binary_sensor.laundry_room_washer_cycle_complete",
    "binary_sensor.laundry_room_washer_door",
    "binary_sensor.laundry_room_washer_door_lock",
    "binary_sensor.laundry_room_washer_end_of_cycle",
    "binary_sensor.laundry_room_washer_prewash",
    "binary_sensor.laundry_room_washer_remote_status",
    "button.laundry_room_washer_start_cycle",
    "sensor.laundry_room_washer_cycle",
    "sensor.laundry_room_washer_delay_time_remaining",
    "sensor.laundry_room_washer_rinse_option",
    "sensor.laundry_room_washer_soil_level",
    "sensor.laundry_room_washer_state",
    "sensor.laundry_room_washer_sub_cycle",
    "sensor.laundry_room_washer_time_remaining",
]
DRYER = [
    "binary_sensor.laundry_room_dryer_door",
    "binary_sensor.laundry_room_dryer_end_of_cycle",
    "sensor.laundry_room_dryer_cycle",
    "sensor.laundry_room_dryer_delay_time_remaining",
    "sensor.laundry_room_dryer_dryness_new_level",
    "sensor.laundry_room_dryer_state",
    "sensor.laundry_room_dryer_sub_cycle",
    "sensor.laundry_room_dryer_time_remaining",
]
DISHWASHER = [
    "binary_sensor.kitchen_dishwasher_door",
    "binary_sensor.kitchen_dishwasher_is_clean",
    "sensor.kitchen_dishwasher_cycle_state",
    "sensor.kitchen_dishwasher_dishwasher_cycle_name",
    "sensor.kitchen_dishwasher_operating_mode",
    "sensor.kitchen_dishwasher_time_remaining",
    "sensor.kitchen_dishwasher_user_setting_delay_hours",
]
OVEN = [
    "binary_sensor.kitchen_oven_cooktop_status",
    "sensor.kitchen_oven_cook_mode",
    "sensor.kitchen_oven_cook_time_remaining",
    "sensor.kitchen_oven_current_state",
    "sensor.kitchen_oven_delay_time_remaining",
    "sensor.kitchen_oven_display_temperature",
    "sensor.kitchen_oven_elapsed_cook_time",
]
FRIDGE = [
    "binary_sensor.kitchen_refrigerator_door",
    "binary_sensor.kitchen_refrigerator_freezer_door",
    "binary_sensor.kitchen_refrigerator_fridge_left_door",
    "sensor.kitchen_refrigerator_doors",
    "sensor.kitchen_refrigerator_water_filter_status",
]


def test_discover_washer():
    d = discover_from_entity_ids(WASHER)
    assert d.appliance_type == "washer"
    assert d.state_entity == "sensor.laundry_room_washer_state"
    assert d.phase_entity == "sensor.laundry_room_washer_sub_cycle"
    assert d.cycle_entity == "sensor.laundry_room_washer_cycle"
    assert d.remaining_entity == "sensor.laundry_room_washer_time_remaining"
    assert d.done_entity == "binary_sensor.laundry_room_washer_end_of_cycle"
    assert d.door_entity == "binary_sensor.laundry_room_washer_door"


def test_discover_dryer():
    d = discover_from_entity_ids(DRYER)
    assert d.appliance_type == "dryer"
    assert d.remaining_entity == "sensor.laundry_room_dryer_time_remaining"


def test_discover_dishwasher():
    d = discover_from_entity_ids(DISHWASHER)
    assert d.appliance_type == "dishwasher"
    assert d.state_entity == "sensor.kitchen_dishwasher_operating_mode"
    assert d.cycle_entity == "sensor.kitchen_dishwasher_dishwasher_cycle_name"
    assert d.remaining_entity == "sensor.kitchen_dishwasher_time_remaining"
    assert d.done_entity is None


def test_discover_oven():
    d = discover_from_entity_ids(OVEN)
    assert d.appliance_type == "oven"
    assert d.state_entity == "sensor.kitchen_oven_current_state"
    assert d.phase_entity == "sensor.kitchen_oven_cook_mode"
    assert d.remaining_entity == "sensor.kitchen_oven_cook_time_remaining"
    assert d.temperature_entity == "sensor.kitchen_oven_display_temperature"


def test_discover_fridge():
    d = discover_from_entity_ids(FRIDGE)
    assert d.appliance_type == "refrigerator"
    assert d.state_entity == "binary_sensor.kitchen_refrigerator_door"


def test_colors():
    assert hex_to_rgb("#00BCD4") == [0, 188, 212]
    assert hex_to_rgb("fff") == [255, 255, 255]
    assert color_to_hex([0, 188, 212]) == "#00BCD4"
    assert color_to_hex("#4CAF50") == "#4CAF50"  # older entries stored hex
    assert color_to_hex(None, "#F44336") == "#F44336"
