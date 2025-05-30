import unittest
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

from homeassistant.core import HomeAssistant, State
from homeassistant.components.light import (
    ColorMode,
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ATTR_RGB_COLOR,
    LightEntityFeature, # Ensure LightEntityFeature is explicitly imported
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
    supports_rgb: bool = False,
    min_kelvin: int | None = 2700,
    max_kelvin: int | None = 6500,
    device_color_temp_range_min: int | None = 0,
    device_color_temp_range_max: int | None = 100,
    initial_light_on=False,
    initial_brightness=50,
    initial_color_temp_device_value=50,
    initial_rgb_color=(255, 128, 0)
):
    mock_device = MagicMock(spec=PyDreoCeilingFan)
    mock_device.name = name
    mock_device.model = model
    mock_device.device_id = device_id
    mock_device.type = device_type

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
        if hasattr(mock_device, 'brightness'): del mock_device.brightness
    if supports_color_temp:
        mock_device.color_temp = initial_color_temp_device_value
    else:
        if hasattr(mock_device, 'color_temp'): del mock_device.color_temp
    if supports_rgb:
        mock_device.rgb_color = initial_rgb_color
    else:
        if hasattr(mock_device, 'rgb_color'): del mock_device.rgb_color

    mock_device.async_set_light_on = AsyncMock()
    mock_device.async_set_brightness = AsyncMock()
    mock_device.async_set_color_temp = AsyncMock()
    mock_device.async_set_rgb_color = AsyncMock()

    return mock_device


class TestDreoLight(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.hass = MagicMock(spec=HomeAssistant)
        self.hass.data = {DOMAIN: {}}

        self.config_entry = ConfigEntry(
            version=1, domain=DOMAIN, title="Dreo Test",
            data={"username": "testuser", "password": "testpassword"},
            source=SOURCE_USER, options={"auto_reconnect": True}
        )
        self.config_entry.entry_id = "mock_entry_id"

        self.mock_pydreo_manager = MagicMock()
        self.hass.data[DOMAIN][PYDREO_MANAGER] = self.mock_pydreo_manager

        self.patcher_async_write_ha_state = patch.object(DreoLightHA, 'async_write_ha_state', new_callable=AsyncMock)
        self.mock_async_write_ha_state = self.patcher_async_write_ha_state.start()

    async def asyncTearDown(self):
        self.patcher_async_write_ha_state.stop()

    async def test_light_creation_dr_hcf(self):
        mock_drhcf_fan = create_mock_ceiling_fan(
            model="DR-HCF003S", supports_brightness=True,
            supports_color_temp=True, supports_rgb=False
        )
        self.mock_pydreo_manager.devices = [mock_drhcf_fan]
        mock_add_entities = AsyncMock(spec=AddEntitiesCallback)

        await async_setup_entry(self.hass, self.config_entry, mock_add_entities)

        mock_add_entities.assert_called_once()
        added_entities = mock_add_entities.call_args[0][0]
        self.assertEqual(len(added_entities), 1)
        light_entity = added_entities[0]

        self.assertIsInstance(light_entity, DreoLightHA)
        self.assertEqual(light_entity.unique_id, f"{mock_drhcf_fan.device_id}-light")

    async def test_light_not_created_for_non_dr_hcf_model(self):
        mock_non_drhcf_fan = create_mock_ceiling_fan(
            model="DR-CFXXX", device_id="test_device_id_cfxxx",
            supports_brightness=False, supports_color_temp=False, supports_rgb=False
        )
        self.mock_pydreo_manager.devices = [mock_non_drhcf_fan]
        mock_add_entities = AsyncMock(spec=AddEntitiesCallback)
        await async_setup_entry(self.hass, self.config_entry, mock_add_entities)
        mock_add_entities.assert_not_called()

    async def test_basic_on_off(self):
        mock_fan = create_mock_ceiling_fan(
            initial_light_on=False, supports_brightness=False,
            supports_color_temp=False, supports_rgb=False
        )
        light_entity = DreoLightHA(mock_fan)

        mock_fan.light_on = False
        self.assertFalse(light_entity.is_on)

        await light_entity.async_turn_on()
        mock_fan.async_set_light_on.assert_awaited_once_with(True)

        mock_fan.light_on = True
        self.assertTrue(light_entity.is_on)

        mock_fan.async_set_light_on.reset_mock()
        await light_entity.async_turn_off()
        mock_fan.async_set_light_on.assert_awaited_once_with(False)

        mock_fan.light_on = False
        self.assertFalse(light_entity.is_on)

    async def test_brightness_control(self):
        mock_fan = create_mock_ceiling_fan(
            supports_brightness=True, initial_brightness=50,
            supports_color_temp=False, supports_rgb=False
        )
        light_entity = DreoLightHA(mock_fan)

        self.assertEqual(light_entity.supported_color_modes, {ColorMode.BRIGHTNESS})
        mock_fan.brightness = 50
        self.assertEqual(light_entity.brightness, 128)

        mock_fan.light_on = False
        await light_entity.async_turn_on(**{ATTR_BRIGHTNESS: 255})
        mock_fan.async_set_light_on.assert_awaited_once_with(True)
        mock_fan.async_set_brightness.assert_awaited_once_with(100)

        mock_fan.brightness = 100; mock_fan.light_on = True
        self.assertEqual(light_entity.brightness, 255)

        mock_fan.async_set_brightness.reset_mock()
        await light_entity.async_turn_on(**{ATTR_BRIGHTNESS: 128})
        mock_fan.async_set_brightness.assert_awaited_once_with(51)

        mock_fan.async_set_brightness.reset_mock()
        await light_entity.async_turn_on(**{ATTR_BRIGHTNESS: 1})
        mock_fan.async_set_brightness.assert_awaited_once_with(1)

    async def test_color_temperature_control(self):
        mock_fan = create_mock_ceiling_fan(
            supports_brightness=True, supports_color_temp=True, supports_rgb=False,
            min_kelvin=2700, max_kelvin=6500,
            device_color_temp_range_min=0, device_color_temp_range_max=100,
            initial_color_temp_device_value=50
        )
        light_entity = DreoLightHA(mock_fan)

        self.assertEqual(light_entity.supported_color_modes, {ColorMode.BRIGHTNESS, ColorMode.COLOR_TEMP})
        self.assertEqual(light_entity.min_color_temp_kelvin, 2700)
        self.assertEqual(light_entity.max_color_temp_kelvin, 6500)

        mock_fan.color_temp = 50
        self.assertEqual(light_entity.color_temp, 4600)

        await light_entity.async_turn_on(**{ATTR_COLOR_TEMP_KELVIN: 2700})
        mock_fan.async_set_color_temp.assert_awaited_once_with(0)
        mock_fan.async_set_color_temp.reset_mock()

        await light_entity.async_turn_on(**{ATTR_COLOR_TEMP_KELVIN: 6500})
        mock_fan.async_set_color_temp.assert_awaited_once_with(100)
        mock_fan.async_set_color_temp.reset_mock()

        await light_entity.async_turn_on(**{ATTR_COLOR_TEMP_KELVIN: 4600})
        mock_fan.async_set_color_temp.assert_awaited_once_with(50)

    async def test_hs_rgb_color_control(self):
        mock_fan = create_mock_ceiling_fan(
            supports_brightness=True, supports_color_temp=False, supports_rgb=True,
            initial_rgb_color=(255, 0, 0)
        )
        light_entity = DreoLightHA(mock_fan)
        self.assertEqual(light_entity.supported_color_modes, {ColorMode.BRIGHTNESS, ColorMode.HS})

        mock_fan.rgb_color = (255,0,0)
        hs_red = color_RGB_to_hs(255,0,0)
        self.assertAlmostEqual(light_entity.hs_color[0], hs_red[0], places=1)

        hs_blue = (240.0, 100.0); rgb_blue = color_hs_to_RGB(*hs_blue)
        await light_entity.async_turn_on(**{ATTR_HS_COLOR: hs_blue})
        mock_fan.async_set_rgb_color.assert_awaited_once_with(rgb_blue)

    async def test_color_mode_property(self):
        mock_fan = create_mock_ceiling_fan(initial_light_on=False, initial_color_temp_device_value=0)
        light_entity = DreoLightHA(mock_fan)

        mock_fan.light_on = False
        self.assertEqual(light_entity.color_mode, ColorMode.ONOFF)

        mock_fan.light_on = True
        mock_fan.brightness = None; mock_fan.color_temp = None; mock_fan.rgb_color = None
        self.assertEqual(light_entity.color_mode, ColorMode.ONOFF)

        mock_fan.brightness = 60
        self.assertEqual(light_entity.color_mode, ColorMode.BRIGHTNESS)

        mock_fan.color_temp = 0
        self.assertEqual(light_entity.color_mode, ColorMode.COLOR_TEMP)

        mock_fan.rgb_color = (100, 100, 255)
        self.assertEqual(light_entity.color_mode, ColorMode.HS)

    async def test_supported_color_modes_property(self):
        light_on_off = DreoLightHA(create_mock_ceiling_fan(supports_brightness=False, supports_color_temp=False, supports_rgb=False))
        self.assertEqual(light_on_off.supported_color_modes, {ColorMode.ONOFF})

        light_brightness = DreoLightHA(create_mock_ceiling_fan(supports_brightness=True, supports_color_temp=False, supports_rgb=False))
        self.assertEqual(light_brightness.supported_color_modes, {ColorMode.BRIGHTNESS})

        light_ct_implies_bright = DreoLightHA(create_mock_ceiling_fan(supports_brightness=True, supports_color_temp=True, supports_rgb=False))
        self.assertEqual(light_ct_implies_bright.supported_color_modes, {ColorMode.BRIGHTNESS, ColorMode.COLOR_TEMP})

        light_ct_no_explicit_bright = DreoLightHA(create_mock_ceiling_fan(supports_brightness=False, supports_color_temp=True, supports_rgb=False))
        self.assertEqual(light_ct_no_explicit_bright.supported_color_modes, {ColorMode.BRIGHTNESS, ColorMode.COLOR_TEMP})

        light_hs_implies_bright = DreoLightHA(create_mock_ceiling_fan(supports_brightness=True, supports_color_temp=False, supports_rgb=True))
        self.assertEqual(light_hs_implies_bright.supported_color_modes, {ColorMode.BRIGHTNESS, ColorMode.HS})

        light_hs_no_explicit_bright = DreoLightHA(create_mock_ceiling_fan(supports_brightness=False, supports_color_temp=False, supports_rgb=True))
        self.assertEqual(light_hs_no_explicit_bright.supported_color_modes, {ColorMode.BRIGHTNESS, ColorMode.HS})

        light_all = DreoLightHA(create_mock_ceiling_fan(supports_brightness=True, supports_color_temp=True, supports_rgb=True))
        self.assertEqual(light_all.supported_color_modes, {ColorMode.BRIGHTNESS, ColorMode.COLOR_TEMP, ColorMode.HS})

    async def test_supported_features_initialization(self):
        """Test _attr_supported_features is correctly set in __init__."""
        # Case 1: Only On/Off
        mock_on_off = create_mock_ceiling_fan(supports_brightness=False, supports_color_temp=False, supports_rgb=False)
        light_on_off = DreoLightHA(mock_on_off)
        self.assertEqual(light_on_off.supported_features, LightEntityFeature(0))

        # Case 2: Brightness only
        mock_brightness = create_mock_ceiling_fan(supports_brightness=True, supports_color_temp=False, supports_rgb=False)
        light_brightness = DreoLightHA(mock_brightness)
        self.assertEqual(light_brightness.supported_features, LightEntityFeature.BRIGHTNESS)

        # Case 3: Color Temp enabled (implies Brightness feature)
        mock_ct = create_mock_ceiling_fan(supports_brightness=False, supports_color_temp=True, supports_rgb=False)
        light_ct = DreoLightHA(mock_ct)
        self.assertEqual(light_ct.supported_features, LightEntityFeature.BRIGHTNESS)

        # Case 4: HS (RGB) enabled (implies Brightness feature)
        mock_hs = create_mock_ceiling_fan(supports_brightness=False, supports_color_temp=False, supports_rgb=True)
        light_hs = DreoLightHA(mock_hs)
        self.assertEqual(light_hs.supported_features, LightEntityFeature.BRIGHTNESS)

        # Case 5: All features imply brightness
        mock_all = create_mock_ceiling_fan(supports_brightness=True, supports_color_temp=True, supports_rgb=True)
        light_all = DreoLightHA(mock_all)
        self.assertEqual(light_all.supported_features, LightEntityFeature.BRIGHTNESS)

        # Case 6: Brightness and Color Temp (explicit brightness true)
        mock_bright_ct = create_mock_ceiling_fan(supports_brightness=True, supports_color_temp=True, supports_rgb=False)
        light_bright_ct = DreoLightHA(mock_bright_ct)
        self.assertEqual(light_bright_ct.supported_features, LightEntityFeature.BRIGHTNESS)


    async def test_turn_on_with_multiple_params(self):
        mock_fan = create_mock_ceiling_fan(
            supports_brightness=True, supports_color_temp=True, supports_rgb=True,
            min_kelvin=2700, max_kelvin=6500,
            device_color_temp_range_min=0, device_color_temp_range_max=100
        )
        light_entity = DreoLightHA(mock_fan)

        hs_green = (120.0, 100.0); rgb_green = color_hs_to_RGB(*hs_green)
        ha_brightness_val = 150; device_brightness_val = 59

        mock_fan.light_on = False
        await light_entity.async_turn_on(**{ATTR_HS_COLOR: hs_green, ATTR_BRIGHTNESS: ha_brightness_val})
        mock_fan.async_set_light_on.assert_awaited_once_with(True)
        mock_fan.async_set_rgb_color.assert_awaited_once_with(rgb_green)
        mock_fan.async_set_brightness.assert_awaited_once_with(device_brightness_val)

        mock_fan.async_set_light_on.reset_mock()
        mock_fan.async_set_rgb_color.reset_mock()
        mock_fan.async_set_brightness.reset_mock()
        mock_fan.async_set_color_temp.reset_mock()

        kelvin_val = 4600; device_kelvin_val = 50
        ha_brightness_val_2 = 200; device_brightness_val_2 = 79

        mock_fan.light_on = True
        await light_entity.async_turn_on(**{ATTR_COLOR_TEMP_KELVIN: kelvin_val, ATTR_BRIGHTNESS: ha_brightness_val_2})
        mock_fan.async_set_light_on.assert_not_called()
        mock_fan.async_set_color_temp.assert_awaited_once_with(device_kelvin_val)
        mock_fan.async_set_brightness.assert_awaited_once_with(device_brightness_val_2)
        mock_fan.async_set_rgb_color.assert_not_called()


if __name__ == '__main__':
    unittest.main()
