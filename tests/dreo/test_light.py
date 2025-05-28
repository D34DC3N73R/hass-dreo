import unittest
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

from homeassistant.core import HomeAssistant, State
from homeassistant.components.light import (
    ColorMode,
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ATTR_RGB_COLOR, # For verifying device state if needed
)
from homeassistant.const import STATE_ON, STATE_OFF, Platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry, SOURCE_USER
from homeassistant.setup import async_setup_component
from homeassistant.util.color import color_hs_to_RGB, color_RGB_to_hs

from custom_components.dreo.const import DOMAIN, PYDREO_MANAGER
from custom_components.dreo.light import DreoLightHA, async_setup_entry
# Assuming PyDreoCeilingFan is available at this path via __init__.py in pydreo
from custom_components.dreo.pydreo import PyDreoCeilingFan, DreoDeviceType 

# Helper to create a mock PyDreoCeilingFan
def create_mock_ceiling_fan(
    name="Test DR-HCF Fan",
    model="DR-HCF001S", # Example DR-HCF model
    unique_id="test_unique_id_hcf001s",
    device_type=DreoDeviceType.CEILING_FAN,
    supports_brightness=True,
    supports_color_temp=True,
    supports_rgb=True,
    initial_light_on=False,
    initial_brightness=50, # Device scale 1-100
    initial_color_temp=3000, # Kelvin
    initial_rgb_color=(255, 128, 0) # Orange
):
    mock_device = MagicMock(spec=PyDreoCeilingFan)
    mock_device.name = name
    mock_device.model = model
    mock_device.unique_id = unique_id
    mock_device.type = device_type # Used in __init__.py logic

    # Use PropertyMock for attributes that are read and have setters
    # This allows us to check if the setter was called via the property
    
    # _light_on = initial_light_on
    # def get_light_on(): return _light_on
    # def set_light_on(val): nonlocal _light_on; _light_on = val; mock_device._send_command.return_value = True # Simulate command
    # type(mock_device).light_on = PropertyMock(side_effect=set_light_on, return_value=_light_on)
    # For MagicMock, direct attribute assignment will work for simple cases.
    # If explicit setter behavior needs to be mocked (like _send_command call),
    # then PropertyMock with custom fget/fset is more robust.
    # For now, let's keep it simpler and rely on MagicMock's default behavior
    # and direct assertions on the mock's attributes.
    
    mock_device.light_on = initial_light_on
    
    if supports_brightness:
        mock_device.brightness = initial_brightness
    else:
        # Make sure hasattr returns False if not supported
        del mock_device.brightness 
        # Re-attach as a non-existent attribute for hasattr check if needed by specific tests
        # Or, rely on spec=PyDreoCeilingFan and if it's not in spec, hasattr will be false.
        # For explicit "None" state vs "not supported", we might need more.
        # The current DreoLightHA uses hasattr(self.pydreo_device, 'brightness')
        # So, if the attribute is missing from the mock, hasattr will be False.
        pass


    if supports_color_temp:
        mock_device.color_temp = initial_color_temp
    else:
        del mock_device.color_temp

    if supports_rgb:
        mock_device.rgb_color = initial_rgb_color
    else:
        del mock_device.rgb_color

    # Mock methods that might be called by the entity
    # In DreoLightHA, setters on pydreo_device are used directly.
    # Example: self.pydreo_device.light_on = True
    # MagicMock will automatically create these attributes on first access if not part of spec,
    # or allow assignment. We can then assert their values.

    # If PyDreoCeilingFan methods like _send_command were called by DreoLightHA,
    # we'd mock them here:
    # mock_device._send_command = AsyncMock(return_value=True)
    
    return mock_device


class TestDreoLight(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        """Set up things to be run when tests are started."""
        self.hass = MagicMock(spec=HomeAssistant)
        self.hass.data = {DOMAIN: {}}
        
        # Mock config entry
        self.config_entry = ConfigEntry(
            version=1,
            domain=DOMAIN,
            title="Dreo Test",
            data={"username": "testuser", "password": "testpassword"},
            source=SOURCE_USER,
            options={"auto_reconnect": True}
        )
        self.config_entry.entry_id = "mock_entry_id"

        # Mock pydreo_manager
        self.mock_pydreo_manager = MagicMock()
        self.hass.data[DOMAIN][PYDREO_MANAGER] = self.mock_pydreo_manager
        
        # This is needed for the light platform to be set up via async_setup_component
        # and for hass.config_entries.async_forward_entry_setups to be callable
        # In a real HA setup, this would be part of the component loader.
        # For unit tests, we often mock what async_setup_entry needs directly.
        # However, the test_light_creation_dr_hcf in prompt uses async_setup_entry from light.py
        
        # Let's ensure necessary HA components for light are set up if we were doing full integration test
        # For unit testing DreoLightHA directly, this might not be needed.
        # await async_setup_component(self.hass, "light", {}) 


    async def test_light_creation_dr_hcf(self):
        """Test light entity is created for DR-HCF models."""
        mock_drhcf_fan = create_mock_ceiling_fan(model="DR-HCF001S")
        self.mock_pydreo_manager.devices = [mock_drhcf_fan]
        
        mock_add_entities = AsyncMock(spec=AddEntitiesCallback)
        
        await async_setup_entry(self.hass, self.config_entry, mock_add_entities)
        
        self.assertEqual(mock_add_entities.call_count, 1)
        added_entities = mock_add_entities.call_args[0][0]
        self.assertEqual(len(added_entities), 1)
        light_entity = added_entities[0]
        
        self.assertIsInstance(light_entity, DreoLightHA)
        self.assertEqual(light_entity.unique_id, f"{mock_drhcf_fan.unique_id}-light")
        self.assertEqual(light_entity.name, f"{mock_drhcf_fan.name} Light")
        self.assertEqual(light_entity.device_info["model"], mock_drhcf_fan.model)

    async def test_light_not_created_for_non_dr_hcf_model(self):
        """Test light entity is NOT created for non-DR-HCF fan models."""
        mock_non_drhcf_fan = create_mock_ceiling_fan(model="DR-CFXXX") # Non-DR-HCF
        self.mock_pydreo_manager.devices = [mock_non_drhcf_fan]
        
        mock_add_entities = AsyncMock(spec=AddEntitiesCallback)
        
        await async_setup_entry(self.hass, self.config_entry, mock_add_entities)
        
        mock_add_entities.assert_not_called()

    async def test_basic_on_off(self):
        """Test basic on/off functionality."""
        mock_fan = create_mock_ceiling_fan(initial_light_on=False)
        light_entity = DreoLightHA(mock_fan)
        light_entity.hass = self.hass # For async_write_ha_state

        self.assertFalse(light_entity.is_on)
        
        # Turn on
        await light_entity.async_turn_on()
        self.assertTrue(mock_fan.light_on) # Direct attribute check
        self.assertTrue(light_entity.is_on)
        
        # Turn off
        await light_entity.async_turn_off()
        self.assertFalse(mock_fan.light_on)
        self.assertFalse(light_entity.is_on)

    async def test_brightness_control(self):
        """Test brightness control."""
        mock_fan = create_mock_ceiling_fan(
            supports_brightness=True, 
            initial_brightness=50, # Device 1-100
            supports_color_temp=False, 
            supports_rgb=False
        )
        light_entity = DreoLightHA(mock_fan)
        light_entity.hass = self.hass

        self.assertIn(ColorMode.BRIGHTNESS, light_entity.supported_color_modes)
        self.assertNotIn(ColorMode.COLOR_TEMP, light_entity.supported_color_modes)
        self.assertNotIn(ColorMode.HS, light_entity.supported_color_modes)
        
        # Test brightness property (50/100 * 255 = 127.5 -> round to 128, or 127 depending on exact scaling)
        # DreoLightHA scaling: round((self.pydreo_device.brightness / DEVICE_BRIGHTNESS_MAX) * HA_BRIGHTNESS_MAX)
        # = round((50 / 100) * 255) = round(127.5) = 128
        self.assertEqual(light_entity.brightness, 128) 

        # Test turning on with brightness
        await light_entity.async_turn_on(**{ATTR_BRIGHTNESS: 255})
        self.assertTrue(mock_fan.light_on)
        self.assertEqual(mock_fan.brightness, 100) # Device scale 1-100

        await light_entity.async_turn_on(**{ATTR_BRIGHTNESS: 128}) # HA 128 -> Device 50
        # Scaling: round((128 / 255) * 99) + 1 = round(0.5019 * 99) + 1 = round(49.69) + 1 = 50 + 1 = 51
        # Let's trace DreoLightHA:
        # device_brightness = round((ha_brightness / HA_BRIGHTNESS_MAX) * (DEVICE_BRIGHTNESS_MAX - DEVICE_BRIGHTNESS_MIN)) + DEVICE_BRIGHTNESS_MIN
        # device_brightness = round((128 / 255) * (100 - 1)) + 1 = round(0.50196 * 99) + 1 = round(49.694) + 1 = 50 + 1 = 51
        self.assertEqual(mock_fan.brightness, 51) 

        await light_entity.async_turn_on(**{ATTR_BRIGHTNESS: 1}) # HA 1 -> Device 1
        # device_brightness = round((1 / 255) * 99) + 1 = round(0.388) + 1 = 0 + 1 = 1
        self.assertEqual(mock_fan.brightness, 1)

    async def test_color_temperature_control(self):
        """Test color temperature control."""
        mock_fan = create_mock_ceiling_fan(
            supports_brightness=True, # Typically lights with CT also have brightness
            supports_color_temp=True, 
            initial_color_temp=3000,
            supports_rgb=False
        )
        light_entity = DreoLightHA(mock_fan)
        light_entity.hass = self.hass

        self.assertIn(ColorMode.COLOR_TEMP, light_entity.supported_color_modes)
        self.assertNotIn(ColorMode.HS, light_entity.supported_color_modes)

        self.assertEqual(light_entity.color_temp, 3000)

        await light_entity.async_turn_on(**{ATTR_COLOR_TEMP_KELVIN: 3500})
        self.assertTrue(mock_fan.light_on)
        self.assertEqual(mock_fan.color_temp, 3500)
        # Setting color temp might reset rgb_color if that was the previous mode
        # self.assertIsNone(mock_fan.rgb_color) # If pydreo device clears it

    async def test_hs_rgb_color_control(self):
        """Test HS/RGB color control."""
        mock_fan = create_mock_ceiling_fan(
            supports_brightness=True,
            supports_color_temp=True, # Some RGB lights also support CT
            supports_rgb=True,
            initial_rgb_color=(255, 0, 0) # Red
        )
        light_entity = DreoLightHA(mock_fan)
        light_entity.hass = self.hass

        self.assertIn(ColorMode.HS, light_entity.supported_color_modes)
        
        # Test hs_color property (Red: (255,0,0) -> HS (0.0, 100.0))
        hs_red = color_RGB_to_hs(255,0,0)
        self.assertAlmostEqual(light_entity.hs_color[0], hs_red[0], places=1)
        self.assertAlmostEqual(light_entity.hs_color[1], hs_red[1], places=1)

        # Test turning on with HS color (Blue: HS(240.0, 100.0) -> RGB (0,0,255))
        hs_blue = (240.0, 100.0)
        rgb_blue = color_hs_to_RGB(*hs_blue) # (0,0,255)
        await light_entity.async_turn_on(**{ATTR_HS_COLOR: hs_blue})
        self.assertTrue(mock_fan.light_on)
        self.assertEqual(mock_fan.rgb_color, rgb_blue)
        # Setting rgb might reset color_temp if that was the previous mode
        # self.assertIsNone(mock_fan.color_temp) # If pydreo device clears it

    async def test_color_mode_property(self):
        """Test the color_mode property reflects device state."""
        mock_fan = create_mock_ceiling_fan(
            supports_brightness=True,
            supports_color_temp=True,
            supports_rgb=True,
            initial_light_on=False
        )
        light_entity = DreoLightHA(mock_fan)
        light_entity.hass = self.hass
        
        # Off
        self.assertEqual(light_entity.color_mode, ColorMode.ONOFF)

        # On, no specific color/brightness state set on device yet (assuming defaults or None)
        mock_fan.light_on = True
        mock_fan.brightness = None # Explicitly None for this test phase
        mock_fan.color_temp = None
        mock_fan.rgb_color = None
        self.assertEqual(light_entity.color_mode, ColorMode.ONOFF) # Or BRIGHTNESS if brightness has a default value

        # On + Brightness
        mock_fan.brightness = 60
        self.assertEqual(light_entity.color_mode, ColorMode.BRIGHTNESS)

        # On + Color Temp (should take precedence over brightness for mode reporting)
        mock_fan.color_temp = 4000
        self.assertEqual(light_entity.color_mode, ColorMode.COLOR_TEMP)
        
        # On + RGB (should take precedence over color_temp and brightness)
        mock_fan.rgb_color = (100, 100, 255)
        self.assertEqual(light_entity.color_mode, ColorMode.HS)

        # Back to only brightness after RGB was set (e.g. user changed brightness)
        # Device mock needs to reflect that setting brightness might clear color modes
        mock_fan.rgb_color = None
        mock_fan.color_temp = None
        mock_fan.brightness = 70
        self.assertEqual(light_entity.color_mode, ColorMode.BRIGHTNESS)

    async def test_supported_color_modes_property(self):
        """Test supported_color_modes for various device capabilities."""
        # 1. Only On/Off (no brightness, ct, hs attributes on mock)
        mock_on_off = create_mock_ceiling_fan(supports_brightness=False, supports_color_temp=False, supports_rgb=False)
        light_on_off = DreoLightHA(mock_on_off)
        self.assertEqual(light_on_off.supported_color_modes, {ColorMode.ONOFF})

        # 2. On/Off + Brightness
        mock_brightness = create_mock_ceiling_fan(supports_brightness=True, supports_color_temp=False, supports_rgb=False)
        light_brightness = DreoLightHA(mock_brightness)
        self.assertEqual(light_brightness.supported_color_modes, {ColorMode.ONOFF, ColorMode.BRIGHTNESS})

        # 3. On/Off + Brightness + Color Temp
        mock_ct = create_mock_ceiling_fan(supports_brightness=True, supports_color_temp=True, supports_rgb=False)
        light_ct = DreoLightHA(mock_ct)
        self.assertEqual(light_ct.supported_color_modes, {ColorMode.ONOFF, ColorMode.BRIGHTNESS, ColorMode.COLOR_TEMP})

        # 4. On/Off + Brightness + HS (RGB)
        mock_hs = create_mock_ceiling_fan(supports_brightness=True, supports_color_temp=False, supports_rgb=True)
        light_hs = DreoLightHA(mock_hs)
        self.assertEqual(light_hs.supported_color_modes, {ColorMode.ONOFF, ColorMode.BRIGHTNESS, ColorMode.HS})
        
        # 5. All supported
        mock_all = create_mock_ceiling_fan(supports_brightness=True, supports_color_temp=True, supports_rgb=True)
        light_all = DreoLightHA(mock_all)
        self.assertEqual(light_all.supported_color_modes, {ColorMode.ONOFF, ColorMode.BRIGHTNESS, ColorMode.COLOR_TEMP, ColorMode.HS})

    async def test_turn_on_with_multiple_params(self):
        """Test turning on with multiple parameters like brightness and color."""
        mock_fan = create_mock_ceiling_fan(
            supports_brightness=True,
            supports_color_temp=True,
            supports_rgb=True 
        )
        light_entity = DreoLightHA(mock_fan)
        light_entity.hass = self.hass

        # Turn on with HS color and Brightness
        hs_green = (120.0, 100.0) # Green
        rgb_green = color_hs_to_RGB(*hs_green)
        ha_brightness_val = 150 
        device_brightness_val = round((ha_brightness_val / 255) * 99) + 1 # 59

        await light_entity.async_turn_on(**{
            ATTR_HS_COLOR: hs_green,
            ATTR_BRIGHTNESS: ha_brightness_val
        })
        self.assertTrue(mock_fan.light_on)
        self.assertEqual(mock_fan.rgb_color, rgb_green)
        self.assertEqual(mock_fan.brightness, device_brightness_val)
        # self.assertIsNone(mock_fan.color_temp) # Assuming setting HS/RGB clears CT on device

        # Turn on with Color Temp and Brightness (HS should not be set)
        mock_fan.rgb_color = None # Reset for clarity
        kelvin_val = 4500
        ha_brightness_val_2 = 200
        device_brightness_val_2 = round((ha_brightness_val_2 / 255) * 99) + 1 # 79

        await light_entity.async_turn_on(**{
            ATTR_COLOR_TEMP_KELVIN: kelvin_val,
            ATTR_BRIGHTNESS: ha_brightness_val_2
        })
        self.assertTrue(mock_fan.light_on)
        self.assertEqual(mock_fan.color_temp, kelvin_val)
        self.assertEqual(mock_fan.brightness, device_brightness_val_2)
        self.assertIsNone(mock_fan.rgb_color) # Ensure HS/RGB was not set

# This allows running the tests from the command line
if __name__ == '__main__':
    unittest.main()
