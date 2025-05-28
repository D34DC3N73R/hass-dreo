import unittest
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

from homeassistant.core import HomeAssistant, State
from homeassistant.components.light import (
    ColorMode,
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ATTR_RGB_COLOR, 
)
from homeassistant.const import STATE_ON, STATE_OFF, Platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry, SOURCE_USER
from homeassistant.setup import async_setup_component
from homeassistant.util.color import color_hs_to_RGB, color_RGB_to_hs

from custom_components.dreo.const import DOMAIN, PYDREO_MANAGER
from custom_components.dreo.light import DreoLightHA, async_setup_entry
from custom_components.dreo.pydreo import PyDreoCeilingFan, DreoDeviceType 

# Helper to create a mock PyDreoCeilingFan
def create_mock_ceiling_fan(
    name="Test DR-HCF Fan",
    model="DR-HCF001S", 
    device_id="test_device_id_hcf001s",
    device_type=DreoDeviceType.CEILING_FAN,
    supports_brightness: bool = True,
    supports_color_temp: bool = True,
    supports_rgb: bool = False,  # Defaulting to False as per typical DR-HCF003S
    min_kelvin: int | None = 2700, # Default based on DR-HCF003S assumption
    max_kelvin: int | None = 6500, # Default based on DR-HCF003S assumption
    device_color_temp_range_min: int | None = 0, # Default device native range min
    device_color_temp_range_max: int | None = 100, # Default device native range max
    initial_light_on=False,
    initial_brightness=50, 
    initial_color_temp_device_value=50, # Device native scale
    initial_rgb_color=(255, 128, 0) 
):
    mock_device = MagicMock(spec=PyDreoCeilingFan)
    mock_device.name = name
    mock_device.model = model
    mock_device.device_id = device_id
    mock_device.type = device_type

    # Assign capability attributes
    mock_device.supports_brightness = supports_brightness
    mock_device.supports_color_temp = supports_color_temp
    mock_device.supports_rgb = supports_rgb
    mock_device.min_kelvin = min_kelvin
    mock_device.max_kelvin = max_kelvin
    mock_device.device_color_temp_range_min = device_color_temp_range_min
    mock_device.device_color_temp_range_max = device_color_temp_range_max
    
    mock_device.light_on = initial_light_on
    
    if supports_brightness:
        mock_device.brightness = initial_brightness
    else:
        if hasattr(mock_device, 'brightness'):
             del mock_device.brightness

    if supports_color_temp:
        # This is the device's native value, not Kelvin
        mock_device.color_temp = initial_color_temp_device_value 
    else:
        if hasattr(mock_device, 'color_temp'):
            del mock_device.color_temp

    if supports_rgb:
        mock_device.rgb_color = initial_rgb_color
    else:
        if hasattr(mock_device, 'rgb_color'):
            del mock_device.rgb_color
            
    return mock_device


class TestDreoLight(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        """Set up things to be run when tests are started."""
        self.hass = MagicMock(spec=HomeAssistant)
        self.hass.data = {DOMAIN: {}}
        
        self.config_entry = ConfigEntry(
            version=1,
            domain=DOMAIN,
            title="Dreo Test",
            data={"username": "testuser", "password": "testpassword"},
            source=SOURCE_USER,
            options={"auto_reconnect": True}
        )
        self.config_entry.entry_id = "mock_entry_id"

        self.mock_pydreo_manager = MagicMock()
        self.hass.data[DOMAIN][PYDREO_MANAGER] = self.mock_pydreo_manager
        
        # Patch async_write_ha_state for all DreoLightHA instances created in tests
        self.patcher_async_write_ha_state = patch.object(DreoLightHA, 'async_write_ha_state', new_callable=AsyncMock)
        self.mock_async_write_ha_state = self.patcher_async_write_ha_state.start()

    async def asyncTearDown(self):
        """Tear down test fixtures."""
        self.patcher_async_write_ha_state.stop()

    async def test_light_creation_dr_hcf(self):
        """Test light entity is created for DR-HCF models."""
        mock_drhcf_fan = create_mock_ceiling_fan(
            model="DR-HCF003S", 
            supports_brightness=True, 
            supports_color_temp=True, 
            supports_rgb=False # Typical for DR-HCF003S
        )
        self.mock_pydreo_manager.devices = [mock_drhcf_fan]
        
        mock_add_entities = AsyncMock(spec=AddEntitiesCallback)
        
        await async_setup_entry(self.hass, self.config_entry, mock_add_entities)
        
        self.assertEqual(mock_add_entities.call_count, 1)
        added_entities = mock_add_entities.call_args[0][0]
        self.assertEqual(len(added_entities), 1)
        light_entity = added_entities[0]
        
        self.assertIsInstance(light_entity, DreoLightHA)
        self.assertEqual(light_entity.unique_id, f"{mock_drhcf_fan.device_id}-light")
        self.assertEqual(light_entity.name, f"{mock_drhcf_fan.name} Light")
        self.assertEqual(light_entity.device_info["model"], mock_drhcf_fan.model)

    async def test_light_not_created_for_non_dr_hcf_model(self):
        """Test light entity is NOT created for non-DR-HCF fan models."""
        mock_non_drhcf_fan = create_mock_ceiling_fan(
            model="DR-CFXXX", 
            device_id="test_device_id_cfxxx",
            supports_brightness=False, 
            supports_color_temp=False,
            supports_rgb=False
        )
        self.mock_pydreo_manager.devices = [mock_non_drhcf_fan]
        
        mock_add_entities = AsyncMock(spec=AddEntitiesCallback)
        await async_setup_entry(self.hass, self.config_entry, mock_add_entities)
        mock_add_entities.assert_not_called()

    async def test_basic_on_off(self):
        """Test basic on/off functionality for an ONOFF light."""
        mock_fan = create_mock_ceiling_fan(
            initial_light_on=False,
            supports_brightness=False, 
            supports_color_temp=False,
            supports_rgb=False
        )
        light_entity = DreoLightHA(mock_fan)

        self.assertFalse(light_entity.is_on)
        self.assertEqual(light_entity.supported_color_modes, {ColorMode.ONOFF})
        
        await light_entity.async_turn_on()
        self.assertTrue(mock_fan.light_on)
        self.assertTrue(light_entity.is_on)
        
        await light_entity.async_turn_off()
        self.assertFalse(mock_fan.light_on)
        self.assertFalse(light_entity.is_on)

    async def test_brightness_control(self):
        """Test brightness control for a brightness-only light."""
        mock_fan = create_mock_ceiling_fan(
            supports_brightness=True,
            initial_brightness=50, 
            supports_color_temp=False,
            supports_rgb=False
        )
        light_entity = DreoLightHA(mock_fan)

        self.assertEqual(light_entity.supported_color_modes, {ColorMode.BRIGHTNESS})
        self.assertEqual(light_entity.brightness, 128) # 50/100 * 255

        await light_entity.async_turn_on(**{ATTR_BRIGHTNESS: 255})
        self.assertTrue(mock_fan.light_on)
        self.assertEqual(mock_fan.brightness, 100)

        await light_entity.async_turn_on(**{ATTR_BRIGHTNESS: 128})
        self.assertEqual(mock_fan.brightness, 51) 

        await light_entity.async_turn_on(**{ATTR_BRIGHTNESS: 1})
        self.assertEqual(mock_fan.brightness, 1)

    async def test_color_temperature_control(self):
        """Test color temperature control with Kelvin mapping."""
        mock_fan = create_mock_ceiling_fan(
            supports_brightness=True, 
            supports_color_temp=True,
            supports_rgb=False,
            min_kelvin=2700, max_kelvin=6500,
            device_color_temp_range_min=0, device_color_temp_range_max=100,
            initial_color_temp_device_value=50 # Mid-point device native value
        )
        light_entity = DreoLightHA(mock_fan)

        self.assertEqual(light_entity.supported_color_modes, {ColorMode.BRIGHTNESS, ColorMode.COLOR_TEMP})
        self.assertEqual(light_entity.min_color_temp_kelvin, 2700)
        self.assertEqual(light_entity.max_color_temp_kelvin, 6500)
        
        # Test device to Kelvin mapping (initial value 50 -> mid Kelvin 4600)
        self.assertEqual(light_entity.color_temp, 4600)

        # Test Kelvin to device mapping
        await light_entity.async_turn_on(**{ATTR_COLOR_TEMP_KELVIN: 2700})
        self.assertEqual(mock_fan.color_temp, 0)
        await light_entity.async_turn_on(**{ATTR_COLOR_TEMP_KELVIN: 6500})
        self.assertEqual(mock_fan.color_temp, 100)
        await light_entity.async_turn_on(**{ATTR_COLOR_TEMP_KELVIN: 4600})
        self.assertEqual(mock_fan.color_temp, 50)
        
        # Test clamping
        await light_entity.async_turn_on(**{ATTR_COLOR_TEMP_KELVIN: 2000})
        self.assertEqual(mock_fan.color_temp, 0)
        await light_entity.async_turn_on(**{ATTR_COLOR_TEMP_KELVIN: 7000})
        self.assertEqual(mock_fan.color_temp, 100)
        
        # Test mapping back after direct device set
        mock_fan.color_temp = 25 
        self.assertEqual(light_entity.color_temp, 3650) # 2700 + (6500-2700)*0.25

    async def test_hs_rgb_color_control(self):
        """Test HS/RGB color control for an HS-only light."""
        mock_fan = create_mock_ceiling_fan(
            supports_brightness=True, 
            supports_color_temp=False, 
            supports_rgb=True,
            initial_rgb_color=(255, 0, 0) # Red
        )
        light_entity = DreoLightHA(mock_fan)

        self.assertEqual(light_entity.supported_color_modes, {ColorMode.BRIGHTNESS, ColorMode.HS})
        
        hs_red = color_RGB_to_hs(255,0,0)
        self.assertAlmostEqual(light_entity.hs_color[0], hs_red[0], places=1)
        self.assertAlmostEqual(light_entity.hs_color[1], hs_red[1], places=1)

        hs_blue = (240.0, 100.0)
        rgb_blue = color_hs_to_RGB(*hs_blue)
        await light_entity.async_turn_on(**{ATTR_HS_COLOR: hs_blue})
        self.assertTrue(mock_fan.light_on)
        self.assertEqual(mock_fan.rgb_color, rgb_blue)

    async def test_color_mode_property(self):
        """Test the color_mode property reflects device state."""
        mock_fan = create_mock_ceiling_fan( # All features supported for this test
            initial_light_on=False,
            initial_color_temp_device_value=0 # Device native value
        )
        light_entity = DreoLightHA(mock_fan)
        
        self.assertEqual(light_entity.color_mode, ColorMode.ONOFF) # Off

        mock_fan.light_on = True
        mock_fan.brightness = None; mock_fan.color_temp = None; mock_fan.rgb_color = None
        self.assertEqual(light_entity.color_mode, ColorMode.ONOFF) # On, no specific mode

        mock_fan.brightness = 60
        self.assertEqual(light_entity.color_mode, ColorMode.BRIGHTNESS)

        mock_fan.color_temp = 0 # Device native value
        self.assertEqual(light_entity.color_mode, ColorMode.COLOR_TEMP)
        
        mock_fan.rgb_color = (100, 100, 255)
        self.assertEqual(light_entity.color_mode, ColorMode.HS)

        mock_fan.rgb_color = None; mock_fan.color_temp = None; mock_fan.brightness = 70
        self.assertEqual(light_entity.color_mode, ColorMode.BRIGHTNESS)

    async def test_supported_color_modes_property(self):
        """Test supported_color_modes for various device capabilities."""
        # 1. Only On/Off
        light_on_off = DreoLightHA(create_mock_ceiling_fan(supports_brightness=False, supports_color_temp=False, supports_rgb=False))
        self.assertEqual(light_on_off.supported_color_modes, {ColorMode.ONOFF})

        # 2. Brightness only
        light_brightness = DreoLightHA(create_mock_ceiling_fan(supports_brightness=True, supports_color_temp=False, supports_rgb=False))
        self.assertEqual(light_brightness.supported_color_modes, {ColorMode.BRIGHTNESS})

        # 3. Color Temp only (DreoLightHA does not implicitly add BRIGHTNESS if device doesn't say it supports it)
        light_ct_only = DreoLightHA(create_mock_ceiling_fan(supports_brightness=False, supports_color_temp=True, supports_rgb=False))
        self.assertEqual(light_ct_only.supported_color_modes, {ColorMode.COLOR_TEMP})

        # 4. HS (RGB) only
        light_hs_only = DreoLightHA(create_mock_ceiling_fan(supports_brightness=False, supports_color_temp=False, supports_rgb=True))
        self.assertEqual(light_hs_only.supported_color_modes, {ColorMode.HS})
        
        # 5. Brightness and Color Temp
        light_bright_ct = DreoLightHA(create_mock_ceiling_fan(supports_brightness=True, supports_color_temp=True, supports_rgb=False))
        self.assertEqual(light_bright_ct.supported_color_modes, {ColorMode.BRIGHTNESS, ColorMode.COLOR_TEMP})
        
        # 6. All supported
        light_all = DreoLightHA(create_mock_ceiling_fan(supports_brightness=True, supports_color_temp=True, supports_rgb=True))
        self.assertEqual(light_all.supported_color_modes, {ColorMode.BRIGHTNESS, ColorMode.COLOR_TEMP, ColorMode.HS})

    async def test_turn_on_with_multiple_params(self):
        """Test turning on with multiple parameters like brightness and color."""
        mock_fan = create_mock_ceiling_fan(
            supports_brightness=True, supports_color_temp=True, supports_rgb=True,
            min_kelvin=2700, max_kelvin=6500,
            device_color_temp_range_min=0, device_color_temp_range_max=100
        )
        light_entity = DreoLightHA(mock_fan)

        # HS color and Brightness
        hs_green = (120.0, 100.0); rgb_green = color_hs_to_RGB(*hs_green)
        ha_brightness_val = 150; device_brightness_val = round((150 / 255) * 99) + 1 # 59
        await light_entity.async_turn_on(**{ATTR_HS_COLOR: hs_green, ATTR_BRIGHTNESS: ha_brightness_val})
        self.assertTrue(mock_fan.light_on)
        self.assertEqual(mock_fan.rgb_color, rgb_green)
        self.assertEqual(mock_fan.brightness, device_brightness_val)
        # Assuming setting HS might clear CT on device (or pydreo layer handles it)
        # If pydreo device.rgb_color setter clears .color_temp, then:
        # mock_fan.color_temp = None 

        # Color Temp and Brightness
        mock_fan.rgb_color = None # Reset for this part of the test
        kelvin_val = 4600; device_kelvin_val = 50 # Midpoint
        ha_brightness_val_2 = 200; device_brightness_val_2 = round((200 / 255) * 99) + 1 # 79
        await light_entity.async_turn_on(**{ATTR_COLOR_TEMP_KELVIN: kelvin_val, ATTR_BRIGHTNESS: ha_brightness_val_2})
        self.assertTrue(mock_fan.light_on)
        self.assertEqual(mock_fan.color_temp, device_kelvin_val)
        self.assertEqual(mock_fan.brightness, device_brightness_val_2)
        self.assertIsNone(mock_fan.rgb_color)

# This allows running the tests from the command line
if __name__ == '__main__':
    unittest.main()
