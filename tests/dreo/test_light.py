"""Tests for Dreo Light platform."""

import pytest
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch
import math # For rounding in scaling checks

from custom_components.dreo.basedevice import DreoBaseDeviceHA
from custom_components.dreo.light import (
    DreoLightHA,
    DreoLightEntityDescription,
    # async_setup_entry, # Not testing this directly here anymore, focus on class
)
from homeassistant.components.light import (
    ColorMode,
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN
)
from homeassistant.core import HomeAssistant
# from homeassistant.config_entries import ConfigEntry # Not used in these class unit tests
from custom_components.dreo.const import DOMAIN, PYDREO_MANAGER
from homeassistant.util.percentage import percentage_to_ranged_value


# Pytest fixtures
@pytest.fixture
def mock_hass():
    """Mock HomeAssistant instance."""
    hass = MagicMock(spec=HomeAssistant)
    async def async_add_executor_job_side_effect(target, *args):
        # Simulate executor job by directly calling the target.
        # If target is a bound method of a mock, it should just work.
        # If target is a free function or something, ensure it's callable.
        return target(*args)
    hass.async_add_executor_job = MagicMock(side_effect=async_add_executor_job_side_effect)
    return hass

@pytest.fixture
def mock_pydreo_manager():
    """Mock PyDreo manager."""
    manager = MagicMock()
    return manager

@pytest.fixture
def mock_pydreo_device_fixture_factory():
    """Factory fixture for a mock PyDreo device, allowing getattr mocking."""
    def _factory(sn="XXXYYYZZZ123", name="Test Device", initial_attrs=None, mock_getattr_map=None):
        device = MagicMock()
        device.serial_number = sn
        device.name = name

        if initial_attrs:
            for attr_name, value in initial_attrs.items():
                setattr(device, attr_name, value)
                # If it's a common on/off attribute, mock its PropertyMock for direct is_on checks if needed
                if attr_name in ["light_on", "ledpotkepton"] and not isinstance(getattr(type(device), attr_name, None), PropertyMock):
                    setattr(type(device), attr_name, PropertyMock(return_value=value))


        # Mock methods used by DreoLightHA
        # For on/off via pydreo_light_attr (setattr will be called on the device mock)
        # For brightness/colortemp via _send_command
        device._send_command = MagicMock()

        device.is_online = True
        device.is_connected = True

        # Setup custom getattr behavior
        if mock_getattr_map:
            original_getattr = device.__getattr__ # Store original if any

            def custom_getattr(item):
                if item in mock_getattr_map:
                    return mock_getattr_map[item]
                # Fallback to MagicMock's default behavior or original if it existed
                if hasattr(original_getattr, '__call__'):
                    return original_getattr(item)
                return MagicMock() # Default for unspecified attributes

            device.__getattr__ = custom_getattr
            # Ensure `hasattr` works correctly with this custom getattr
            device.hasattr = lambda item: item in mock_getattr_map or (hasattr(original_getattr, '__call__') and hasattr(device, item))


        return device
    return _factory_factory


# Define various entity descriptions for testing different light types
@pytest.fixture
def desc_onoff_only():
    return DreoLightEntityDescription(key="onoff_light", name="On-Off Light", pydreo_light_attr="light_on")

@pytest.fixture
def desc_brightness_only():
    return DreoLightEntityDescription(
        key="dim_light", name="Dimmable Light", pydreo_light_attr="light_on",
        pydreo_brightness_cmd="brightness",
        pydreo_brightness_range=(1, 100) # Device uses 1-100 for brightness
    )

@pytest.fixture
def desc_colortemp_only():
    return DreoLightEntityDescription(
        key="cct_light", name="CCT Light", pydreo_light_attr="light_on",
        pydreo_colortemp_cmd="colortemp",
        pydreo_colortemp_range=(0, 100), # Device uses 0-100 for CCT percentage
        ha_min_color_temp_kelvin=2700,
        ha_max_color_temp_kelvin=6500
    )

@pytest.fixture
def desc_brightness_colortemp():
    # This is the one used in product code for ceiling fan light
    return DreoLightEntityDescription(
        key="full_light", name="Full Light", pydreo_light_attr="light_on",
        pydreo_brightness_cmd="brightness",
        pydreo_brightness_range=(1, 100),
        pydreo_colortemp_cmd="colortemp",
        pydreo_colortemp_range=(0, 100),
        ha_min_color_temp_kelvin=2700,
        ha_max_color_temp_kelvin=6500
    )


class TestDreoLightHAInitialization:
    """Test initialization of DreoLightHA."""

    def test_init_attributes_none(self, mock_hass, mock_pydreo_manager, mock_pydreo_device_fixture_factory, desc_onoff_only):
        device = mock_pydreo_device_fixture_factory(initial_attrs={"light_on": False})
        light = DreoLightHA(mock_hass, mock_pydreo_manager, desc_onoff_only, device)
        assert light._attr_brightness is None
        assert light._attr_color_temp_kelvin is None

    def test_init_color_modes_and_kelvin_attrs(self, mock_hass, mock_pydreo_manager, mock_pydreo_device_fixture_factory,
                                               desc_onoff_only, desc_brightness_only, desc_colortemp_only, desc_brightness_colortemp):
        device = mock_pydreo_device_fixture_factory(initial_attrs={"light_on": False})

        # On/Off only
        light_onoff = DreoLightHA(mock_hass, mock_pydreo_manager, desc_onoff_only, device)
        assert light_onoff.supported_color_modes == {ColorMode.ONOFF}
        assert light_onoff.color_mode == ColorMode.ONOFF

        # Brightness only
        light_bright = DreoLightHA(mock_hass, mock_pydreo_manager, desc_brightness_only, device)
        assert light_bright.supported_color_modes == {ColorMode.ONOFF, ColorMode.BRIGHTNESS}
        assert light_bright.color_mode == ColorMode.BRIGHTNESS

        # Color Temp only
        light_ct = DreoLightHA(mock_hass, mock_pydreo_manager, desc_colortemp_only, device)
        assert light_ct.supported_color_modes == {ColorMode.ONOFF, ColorMode.COLOR_TEMP}
        assert light_ct.color_mode == ColorMode.COLOR_TEMP
        assert light_ct.min_color_temp_kelvin == desc_colortemp_only.ha_min_color_temp_kelvin
        assert light_ct.max_color_temp_kelvin == desc_colortemp_only.ha_max_color_temp_kelvin

        # Brightness and Color Temp
        light_full = DreoLightHA(mock_hass, mock_pydreo_manager, desc_brightness_colortemp, device)
        assert light_full.supported_color_modes == {ColorMode.ONOFF, ColorMode.BRIGHTNESS, ColorMode.COLOR_TEMP}
        assert light_full.color_mode == ColorMode.COLOR_TEMP # Prioritized


class TestDreoLightHAPropertyGetters:
    """Test property getters for brightness and color_temp_kelvin."""

    # Brightness Getter Tests
    def test_brightness_getter_device_has_value(self, mock_hass, mock_pydreo_manager, mock_pydreo_device_fixture_factory, desc_brightness_only):
        # Device brightness is 50 (in range 1-100)
        # Expected HA: ( (50-1)/(100-1) ) * 100 = (49/99)*100 = 49.49% -> round(0.4949 * 255) = round(126.2) = 126
        device_val = 50
        expected_ha_val = round(((device_val - 1) / (100 - 1)) * 255)

        device = mock_pydreo_device_fixture_factory(
            initial_attrs={"light_on": True}, # So that pydreo_light_attr check passes
            mock_getattr_map={desc_brightness_only.pydreo_brightness_cmd: device_val}
        )
        light = DreoLightHA(mock_hass, mock_pydreo_manager, desc_brightness_only, device)
        assert light.brightness == expected_ha_val

    def test_brightness_getter_device_returns_none(self, mock_hass, mock_pydreo_manager, mock_pydreo_device_fixture_factory, desc_brightness_only):
        device = mock_pydreo_device_fixture_factory(
            initial_attrs={"light_on": True},
            mock_getattr_map={desc_brightness_only.pydreo_brightness_cmd: None} # Device returns None
        )
        light = DreoLightHA(mock_hass, mock_pydreo_manager, desc_brightness_only, device)
        light._attr_brightness = 128 # Simulate HA's internal state
        assert light.brightness == 128 # Should fallback to _attr_brightness

    def test_brightness_getter_mode_not_supported(self, mock_hass, mock_pydreo_manager, mock_pydreo_device_fixture_factory, desc_onoff_only):
        device = mock_pydreo_device_fixture_factory()
        light = DreoLightHA(mock_hass, mock_pydreo_manager, desc_onoff_only, device)
        assert light.brightness is None

    # Color Temp Kelvin Getter Tests
    def test_colortemp_getter_device_has_value(self, mock_hass, mock_pydreo_manager, mock_pydreo_device_fixture_factory, desc_colortemp_only):
        # Device CCT is 50 (in range 0-100 for CCT percentage)
        # HA Kelvin range: 2700-6500. Expected HA: 2700 + ( (50-0)/(100-0) * (6500-2700) ) = 2700 + (0.5 * 3800) = 2700 + 1900 = 4600
        device_val_pct = 50
        expected_ha_kelvin = round(2700 + ((device_val_pct - 0) / (100 - 0)) * (6500 - 2700))

        device = mock_pydreo_device_fixture_factory(
            initial_attrs={"light_on": True},
            mock_getattr_map={desc_colortemp_only.pydreo_colortemp_cmd: device_val_pct}
        )
        light = DreoLightHA(mock_hass, mock_pydreo_manager, desc_colortemp_only, device)
        assert light.color_temp_kelvin == expected_ha_kelvin

    def test_colortemp_getter_device_returns_none(self, mock_hass, mock_pydreo_manager, mock_pydreo_device_fixture_factory, desc_colortemp_only):
        device = mock_pydreo_device_fixture_factory(
            initial_attrs={"light_on": True},
            mock_getattr_map={desc_colortemp_only.pydreo_colortemp_cmd: None} # Device returns None
        )
        light = DreoLightHA(mock_hass, mock_pydreo_manager, desc_colortemp_only, device)
        light._attr_color_temp_kelvin = 3000 # Simulate HA's internal state
        assert light.color_temp_kelvin == 3000 # Should fallback to _attr_color_temp_kelvin

    def test_colortemp_getter_mode_not_supported(self, mock_hass, mock_pydreo_manager, mock_pydreo_device_fixture_factory, desc_onoff_only):
        device = mock_pydreo_device_fixture_factory()
        light = DreoLightHA(mock_hass, mock_pydreo_manager, desc_onoff_only, device)
        assert light.color_temp_kelvin is None


class TestDreoLightHAAsyncTurnOn:
    """Test async_turn_on method for DreoLightHA."""

    @pytest.mark.asyncio
    async def test_turn_on_brightness(self, mock_hass, mock_pydreo_manager, mock_pydreo_device_fixture_factory, desc_brightness_only):
        device = mock_pydreo_device_fixture_factory(initial_attrs={"light_on": False})
        light = DreoLightHA(mock_hass, mock_pydreo_manager, desc_brightness_only, device)
        light.async_write_ha_state = MagicMock()

        ha_brightness_val = 128 # (0-255)
        # Expected device brightness: (128/255 * 100) = 50.196%
        # percentage_to_ranged_value((1,100), 50.196) = (50.196/100 * (100-1)) + 1 = 0.50196 * 99 + 1 = 50.69 -> round to 51
        expected_device_val = round(percentage_to_ranged_value(desc_brightness_only.pydreo_brightness_range, (ha_brightness_val / 255.0) * 100))

        await light.async_turn_on(**{ATTR_BRIGHTNESS: ha_brightness_val})

        # Check on/off call (setattr)
        mock_hass.async_add_executor_job.assert_any_call(setattr, device, desc_brightness_only.pydreo_light_attr, True)
        # Check brightness call (_send_command)
        device._send_command.assert_called_with(desc_brightness_only.pydreo_brightness_cmd, expected_device_val)
        assert light._attr_brightness == ha_brightness_val
        light.async_write_ha_state.assert_called_once() # Called due to brightness change

    @pytest.mark.asyncio
    async def test_turn_on_color_temp(self, mock_hass, mock_pydreo_manager, mock_pydreo_device_fixture_factory, desc_colortemp_only):
        device = mock_pydreo_device_fixture_factory(initial_attrs={"light_on": False})
        light = DreoLightHA(mock_hass, mock_pydreo_manager, desc_colortemp_only, device)
        light.async_write_ha_state = MagicMock()

        ha_kelvin_val = 3000 # (e.g., 2700-6500)
        # Expected device CCT percentage for desc_colortemp_only (range 0-100 for 2700K-6500K):
        # ( (3000-2700) / (6500-2700) ) * (100-0) + 0 = (300/3800)*100 = 7.89... -> round to 8
        expected_device_val = round(((ha_kelvin_val - 2700) / (6500 - 2700)) * (100 - 0) + 0)

        await light.async_turn_on(**{ATTR_COLOR_TEMP_KELVIN: ha_kelvin_val})

        mock_hass.async_add_executor_job.assert_any_call(setattr, device, desc_colortemp_only.pydreo_light_attr, True)
        device._send_command.assert_called_with(desc_colortemp_only.pydreo_colortemp_cmd, expected_device_val)
        assert light._attr_color_temp_kelvin == ha_kelvin_val
        light.async_write_ha_state.assert_called_once() # Called due to color_temp change


class TestDreoLightHAHandleCoordinatorUpdate:
    """Test _handle_coordinator_update for DreoLightHA."""

    @pytest.mark.asyncio # Though _handle_coordinator_update itself is not async
    def test_update_brightness_from_device(self, mock_hass, mock_pydreo_manager, mock_pydreo_device_fixture_factory, desc_brightness_only):
        # Device brightness is 75 (range 1-100)
        # Expected HA: ( (75-1)/(100-1) ) * 255 = (74/99)*255 = 190.15 -> round to 190
        device_b_val = 75
        expected_ha_b_val = round(((device_b_val - 1) / (99)) * 255)

        device = mock_pydreo_device_fixture_factory(
            initial_attrs={"light_on": True}, # Assume light is on
            mock_getattr_map={
                desc_brightness_only.pydreo_light_attr: True, # For _get_pydreo_state
                desc_brightness_only.pydreo_brightness_cmd: device_b_val
            }
        )
        light = DreoLightHA(mock_hass, mock_pydreo_manager, desc_brightness_only, device)
        light._attr_brightness = 100 # Different initial HA brightness
        light.async_write_ha_state = MagicMock()

        light._handle_coordinator_update()

        assert light._attr_brightness == expected_ha_b_val
        light.async_write_ha_state.assert_called_once()

    @pytest.mark.asyncio
    def test_update_colortemp_from_device(self, mock_hass, mock_pydreo_manager, mock_pydreo_device_fixture_factory, desc_colortemp_only):
        # Device CCT is 25 (range 0-100 for CCT percentage for 2700K-6500K)
        # Expected HA: 2700 + ( (25-0)/(100-0) * (6500-2700) ) = 2700 + (0.25 * 3800) = 2700 + 950 = 3650
        device_ct_pct = 25
        expected_ha_ct_kelvin = round(2700 + (device_ct_pct / 100) * (6500 - 2700))

        device = mock_pydreo_device_fixture_factory(
            initial_attrs={"light_on": True},
            mock_getattr_map={
                desc_colortemp_only.pydreo_light_attr: True, # For _get_pydreo_state
                desc_colortemp_only.pydreo_colortemp_cmd: device_ct_pct
            }
        )
        light = DreoLightHA(mock_hass, mock_pydreo_manager, desc_colortemp_only, device)
        light._attr_color_temp_kelvin = 3000 # Different initial HA color temp
        light.async_write_ha_state = MagicMock()

        light._handle_coordinator_update()

        assert light._attr_color_temp_kelvin == expected_ha_ct_kelvin
        light.async_write_ha_state.assert_called_once()

    @pytest.mark.asyncio
    def test_update_no_change(self, mock_hass, mock_pydreo_manager, mock_pydreo_device_fixture_factory, desc_brightness_colortemp):
        # Initial HA states
        initial_ha_brightness = 128
        initial_ha_colortemp = 4000

        # Device states that will scale to the same HA states
        # HA 128 -> device 51 (for 1-100 range)
        # HA 4000K -> device 50% (for 0-100% CCT, 2700-6500K Kelvin)
        device_b_val = 51
        device_ct_pct = 50

        device = mock_pydreo_device_fixture_factory(
            initial_attrs={"light_on": True}, # Light is on, no change there
            mock_getattr_map={
                desc_brightness_colortemp.pydreo_light_attr: True,
                desc_brightness_colortemp.pydreo_brightness_cmd: device_b_val,
                desc_brightness_colortemp.pydreo_colortemp_cmd: device_ct_pct
            }
        )
        light = DreoLightHA(mock_hass, mock_pydreo_manager, desc_brightness_colortemp, device)
        light._attr_is_on = True # Matches device state
        light._attr_brightness = initial_ha_brightness
        light._attr_color_temp_kelvin = initial_ha_colortemp
        light.async_write_ha_state = MagicMock()

        light._handle_coordinator_update()

        light.async_write_ha_state.assert_not_called() # No change in any attribute
```
