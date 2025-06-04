"""Tests for Dreo Ceiling Fans"""
# pylint: disable=used-before-assignment
import logging
from unittest.mock import patch
import pytest
from  .imports import * # pylint: disable=W0401,W0614
from .testbase import TestBase # PATCH_SEND_COMMAND might not be needed if we mock device._send_command
from custom_components.dreo.pydreo.constant import BRIGHTNESS_KEY, COLORTEMP_KEY # Import new keys

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class TestPyDreoCeilingFan(TestBase):
    """Test PyDreoFan class."""
  
    def test_HCF001S(self):  # pylint: disable=invalid-name
        """Load fan and test sending commands."""

        self.get_devices_file_name = "get_devices_HCF001S.json"
        self.pydreo_manager.load_devices()
        assert len(self.pydreo_manager.devices) == 1
        fan : PyDreoCeilingFan = self.pydreo_manager.devices[0]
        assert fan.speed_range == (1, 12)
        assert fan.preset_modes == ['normal', 'natural', 'sleep', 'reverse']
        assert fan.is_feature_supported('poweron') is False
        assert fan.is_feature_supported('light_on') is True

        with patch(PATCH_SEND_COMMAND) as mock_send_command:
            fan.is_on = True
            mock_send_command.assert_called_once_with(fan, {FANON_KEY: True})

        with patch(PATCH_SEND_COMMAND) as mock_send_command:
            fan.light_on = True
            mock_send_command.assert_called_once_with(fan, {LIGHTON_KEY: True})

        with patch(PATCH_SEND_COMMAND) as mock_send_command:
            fan.preset_mode = 'normal'
            mock_send_command.assert_called_once_with(fan, {MODE_KEY: 1})

        with pytest.raises(ValueError):
            fan.preset_mode = 'not_a_mode'

        with patch(PATCH_SEND_COMMAND) as mock_send_command:
            fan.fan_speed = 3
            mock_send_command.assert_called_once_with(fan, {WINDLEVEL_KEY: 3})

        with pytest.raises(ValueError):
            fan.fan_speed = 13

    def test_HCF001S_init_brightness_colortemp(self):
        """Test initialization of brightness and colortemp attributes."""
        self.get_devices_file_name = "get_devices_HCF001S.json"
        self.pydreo_manager.load_devices()
        assert len(self.pydreo_manager.devices) == 1
        fan: PyDreoCeilingFan = self.pydreo_manager.devices[0]

        assert fan._brightness is None
        assert fan._colortemp is None

    def test_HCF001S_update_state_brightness_colortemp(self):
        """Test update_state with brightness and colortemp."""
        self.get_devices_file_name = "get_devices_HCF001S.json"
        self.pydreo_manager.load_devices()
        fan: PyDreoCeilingFan = self.pydreo_manager.devices[0]

        # Structure based on PyDreoBaseDevice.get_state_update_value:
        # it expects `state.get(STATE_KEY, {}).get(key, {}).get("state")`
        # So, the dict passed to update_state should be the full device state dict.
        # Let's assume the device state JSON has 'reported' which contains these keys directly.
        # The actual `update_state` in PyDreoFanBase calls super().update_state(state)
        # and PyDreoBaseDevice.update_state sets self.state = state.
        # Then get_state_update_value uses self.state.get(STATE_KEY, {}).get(key, {}).get("state")
        # For testing, we can mock self.state or pass a compatible dict.
        # The actual values for BRIGHTNESS_KEY and COLORTEMP_KEY are expected to be simple integers.
        # The get_state_update_value method expects the value to be nested if it's a complex state,
        # but for simple values like integers, it might be direct.
        # Let's check PyDreoBaseDevice.get_state_update_value:
        # `val = reported_state.get(key)`
        # `if isinstance(val, dict): return val.get("state") else return val`
        # So, if the key holds a direct value, it should be fine.
        # The provided state to update_state is the full API response for the device.
        # Let's simulate a state dictionary that `get_state_update_value` can parse.
        # This means the actual values for brightness/colortemp should be directly under the key
        # within the 'reported' section of the state.

        # Based on existing fan.update_state, it calls get_state_update_value on `state` directly.
        # And get_state_update_value then looks for `state.get(STATE_KEY, {}).get(key)`
        # So, the input `state` to `fan.update_state` should be the full device state dict.
        # For PyDreoCeilingFan, `update_state` calls super and then does its own `get_state_update_value`.
        # The `get_state_update_value` in `PyDreoBaseDevice` does:
        #   `reported_state = state.get(STATE_KEY, {})`
        #   `val = reported_state.get(key)`
        #   `if isinstance(val, dict): return val.get("state")`
        #   `return val`
        # So, if BRIGHTNESS_KEY holds an int directly in reported_state, it's returned.

        # Sample state reflecting what the device might report after API call
        sample_device_state = {
            STATE_KEY: { # "state"
                FANON_KEY: True,
                LIGHTON_KEY: True,
                WINDLEVEL_KEY: 5,
                BRIGHTNESS_KEY: 50, # Direct value under the key
                COLORTEMP_KEY: 75   # Direct value under the key
            }
        }
        fan.update_state(sample_device_state)
        assert fan._brightness == 50
        assert fan._colortemp == 75

    def test_HCF001S_handle_server_update_brightness_colortemp(self):
        """Test handle_server_update with brightness and colortemp."""
        self.get_devices_file_name = "get_devices_HCF001S.json"
        self.pydreo_manager.load_devices()
        fan: PyDreoCeilingFan = self.pydreo_manager.devices[0]

        # Test with valid integer values
        message_valid = {"reported": {BRIGHTNESS_KEY: 60, COLORTEMP_KEY: 80, LIGHTON_KEY: False}}
        fan.handle_server_update(message_valid)
        assert fan._brightness == 60
        assert fan._colortemp == 80
        assert fan._light_on is False # Check other keys are also processed

        # Test with missing keys - values should remain unchanged
        message_missing_keys = {"reported": {LIGHTON_KEY: True}}
        fan.handle_server_update(message_missing_keys)
        assert fan._brightness == 60 # Should remain from previous update
        assert fan._colortemp == 80  # Should remain from previous update
        assert fan._light_on is True

        # Test with non-integer values - values should remain unchanged due to isinstance check
        message_invalid_type = {"reported": {BRIGHTNESS_KEY: " seventy ", COLORTEMP_KEY: [90]}}
        fan.handle_server_update(message_invalid_type)
        assert fan._brightness == 60 # Should remain (still 60)
        assert fan._colortemp == 80  # Should remain (still 80)

    def test_HCF001S_brightness_property(self):
        """Test brightness property getter and setter."""
        self.get_devices_file_name = "get_devices_HCF001S.json"
        self.pydreo_manager.load_devices()
        fan: PyDreoCeilingFan = self.pydreo_manager.devices[0]

        # Test getter
        fan._brightness = 40
        assert fan.brightness == 40

        # Test setter
        with patch.object(fan, '_send_command') as mock_send_dev_command:
            fan.brightness = 70
            mock_send_dev_command.assert_called_once_with(BRIGHTNESS_KEY, 70)
            # The actual _brightness attribute is updated optimistically by the setter in product code,
            # but here we only test that _send_command is called.
            # The actual update to _brightness would come via update_state or handle_server_update.

    def test_HCF001S_colortemp_property(self):
        """Test colortemp property getter and setter."""
        self.get_devices_file_name = "get_devices_HCF001S.json"
        self.pydreo_manager.load_devices()
        fan: PyDreoCeilingFan = self.pydreo_manager.devices[0]

        # Test getter
        fan._colortemp = 30
        assert fan.colortemp == 30

        # Test setter
        with patch.object(fan, '_send_command') as mock_send_dev_command:
            fan.colortemp = 90
            mock_send_dev_command.assert_called_once_with(COLORTEMP_KEY, 90)
            # Similar to brightness, _colortemp update is via state updates.
