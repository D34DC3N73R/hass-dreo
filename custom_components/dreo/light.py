"""Support for Dreo lights."""
from __future__ import annotations

import logging
from typing import Any, cast

from .haimports import *  # pylint: disable=W0401,W0614

# Explicitly import constants and utilities for clarity and robustness
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN, # Prefer Kelvin for Dreo devices if available
    ATTR_HS_COLOR,
    ATTR_RGB_COLOR, # HS is preferred by HA frontend, but RGB might be used by device
    ColorMode,
    LightEntity, # Already imported via wildcard, but good for explicitness
)
from homeassistant.util.color import color_RGB_to_hs, color_hs_to_RGB

from .dreobasedevice import DreoBaseDeviceHA
from .pydreo import PyDreoCeilingFan
from .const import DOMAIN, PYDREO_MANAGER

_LOGGER = logging.getLogger(__name__)

# Define scales for brightness conversion (HA: 0-255, Device: 1-100)
DEVICE_BRIGHTNESS_MIN = 1
DEVICE_BRIGHTNESS_MAX = 100
HA_BRIGHTNESS_MIN = 1 # HA uses 0 for off, but for "on" state, min is 1 for scaling
HA_BRIGHTNESS_MAX = 255

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Dreo light platform."""
    _LOGGER.info("Setting up Dreo Light platform.")
    
    pydreo_manager = hass.data[DOMAIN][PYDREO_MANAGER]
    devices = pydreo_manager.devices
    
    light_entities = []
    for device in devices:
        # Assuming DR-HCF models are ceiling fans and have a 'light_on' attribute
        # We'll refine the model check later in __init__.py and switch.py modifications
        if isinstance(device, PyDreoCeilingFan) and device.model.startswith("DR-HCF"):
            light_entities.append(DreoLightHA(device))

    if light_entities:
        async_add_entities(light_entities)
        _LOGGER.info(f"Added {len(light_entities)} Dreo light entities.")
    else:
        _LOGGER.info("No Dreo light entities to add.")


class DreoLightHA(DreoBaseDeviceHA, LightEntity):
    """Representation of a Dreo Light."""

    def __init__(self, pydreo_device: PyDreoCeilingFan) -> None:
        """Initialize the Dreo light device."""
        super().__init__(pydreo_device)
        self.pydreo_device: PyDreoCeilingFan = pydreo_device # For type hinting
        self._attr_name = f"{self.pydreo_device.name} Light"
        self._attr_unique_id = f"{self.pydreo_device.device_id}-light" # Changed from unique_id to device_id
        _LOGGER.info(f"Initializing DreoLightHA: {self._attr_name} (Unique ID: {self._attr_unique_id})")


    @property
    def is_on(self) -> bool | None:
        """Return true if light is on."""
        return self.pydreo_device.light_on

    @property
    def brightness(self) -> int | None:
        """Return the current brightness."""
        if self.pydreo_device.brightness is None:
            return None
        # Scale device's 1-100 to HA's 0-255
        # Ensure that even the minimum device brightness (1) maps to a non-zero HA brightness
        scaled_brightness = round((self.pydreo_device.brightness / DEVICE_BRIGHTNESS_MAX) * HA_BRIGHTNESS_MAX)
        return max(HA_BRIGHTNESS_MIN if self.pydreo_device.brightness > 0 else 0, min(scaled_brightness, HA_BRIGHTNESS_MAX))


    @property
    def color_temp(self) -> int | None:
        """Return the color temperature in Kelvin."""
        # Assuming self.pydreo_device.color_temp is already in Kelvin
        return self.pydreo_device.color_temp

    @property
    def hs_color(self) -> tuple[float, float] | None:
        """Return the hs color value."""
        if self.pydreo_device.rgb_color is None:
            return None
        # Convert device's RGB to HA's HS
        return color_RGB_to_hs(*self.pydreo_device.rgb_color)

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        """Flag supported color modes."""
        modes = {ColorMode.ONOFF}
        # Assuming device capabilities are somewhat dynamic or need checking.
        # For now, let's assume if the properties exist on PyDreoCeilingFan, they are supported.
        # A more robust way would be to check device.is_feature_supported() if that exists for these.
        if hasattr(self.pydreo_device, 'brightness'):
            modes.add(ColorMode.BRIGHTNESS)
        if hasattr(self.pydreo_device, 'color_temp'):
            modes.add(ColorMode.COLOR_TEMP)
        if hasattr(self.pydreo_device, 'rgb_color'):
            modes.add(ColorMode.HS) # HS is preferred for RGB by HA
        
        # If only BRIGHTNESS is supported (and not COLOR_TEMP or HS), 
        # some lights default to BRIGHTNESS mode when ON, others to ONOFF.
        # If it has BRIGHTNESS but not COLOR_TEMP or HS, it's BRIGHTNESS mode.
        # If it has COLOR_TEMP or HS, those are more specific.
        # This logic is primarily for `color_mode` property.
        # For `supported_color_modes`, listing all potentially available modes is fine.

        _LOGGER.debug(f"Device {self.name} supported_color_modes: {modes}")
        return modes

    @property
    def color_mode(self) -> ColorMode | str | None:
        """Return the current color mode."""
        # This needs to be determined based on the current state of the light
        if not self.is_on:
            return ColorMode.ONOFF # Or None, HA seems to handle this

        # Check most specific modes first
        if self.pydreo_device.rgb_color is not None and ColorMode.HS in self.supported_color_modes:
            return ColorMode.HS
        if self.pydreo_device.color_temp is not None and ColorMode.COLOR_TEMP in self.supported_color_modes:
            return ColorMode.COLOR_TEMP
        if self.pydreo_device.brightness is not None and ColorMode.BRIGHTNESS in self.supported_color_modes:
            # If only brightness is supported beyond on/off, then it's BRIGHTNESS mode.
            # If HS or COLOR_TEMP are also supported but not active, it might still be BRIGHTNESS.
             if ColorMode.HS not in self.supported_color_modes and ColorMode.COLOR_TEMP not in self.supported_color_modes:
                return ColorMode.BRIGHTNESS
             # If HS/ColorTemp are supported but not set, and brightness is set, it implies BRIGHTNESS mode.
             # This can happen if a light was in HS/ColorTemp mode, then just brightness was adjusted.
             # However, many lights would then report as ColorMode.WHITE or similar.
             # For now, if brightness value exists, and no color state, assume BRIGHTNESS.
             # This might need refinement based on actual device behavior.
             if self.pydreo_device.rgb_color is None and self.pydreo_device.color_temp is None:
                 return ColorMode.BRIGHTNESS


        return ColorMode.ONOFF # Default if no other mode is active or determined

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        _LOGGER.debug(f"Turning on light: {self.name} with kwargs: {kwargs}")

        # Always ensure the light is physically on
        if not self.pydreo_device.light_on:
            self.pydreo_device.light_on = True
            # Potentially add a small delay here if needed for the device to register 'on'
            # await asyncio.sleep(0.1) 

        # Color setting takes precedence
        if ATTR_HS_COLOR in kwargs and ColorMode.HS in self.supported_color_modes:
            hs_color = kwargs[ATTR_HS_COLOR]
            rgb_color = color_hs_to_RGB(*hs_color)
            _LOGGER.debug(f"Setting HS color for {self.name} to {hs_color} -> RGB {rgb_color}")
            self.pydreo_device.rgb_color = cast(tuple[int,int,int], rgb_color)
            # Setting RGB might clear color_temp on some devices, let pydreo handle it or explicitly clear:
            # if self.pydreo_device.color_temp is not None: self.pydreo_device.color_temp = None

        elif ATTR_COLOR_TEMP_KELVIN in kwargs and ColorMode.COLOR_TEMP in self.supported_color_modes:
            color_temp_kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
            _LOGGER.debug(f"Setting color temp for {self.name} to {color_temp_kelvin}K")
            self.pydreo_device.color_temp = color_temp_kelvin
            # Setting color_temp might clear rgb_color on some devices
            # if self.pydreo_device.rgb_color is not None: self.pydreo_device.rgb_color = None
        
        # Brightness can be set in conjunction with color or independently
        if ATTR_BRIGHTNESS in kwargs and ColorMode.BRIGHTNESS in self.supported_color_modes:
            ha_brightness = kwargs[ATTR_BRIGHTNESS]
            # Scale HA's 0-255 to device's 1-100
            device_brightness = round((ha_brightness / HA_BRIGHTNESS_MAX) * (DEVICE_BRIGHTNESS_MAX - DEVICE_BRIGHTNESS_MIN)) + DEVICE_BRIGHTNESS_MIN
            device_brightness = max(DEVICE_BRIGHTNESS_MIN, min(device_brightness, DEVICE_BRIGHTNESS_MAX))
            
            _LOGGER.debug(f"Setting brightness for {self.name} to {ha_brightness} (HA) -> {device_brightness} (Device)")
            self.pydreo_device.brightness = device_brightness
        elif not kwargs and not self.pydreo_device.brightness and ColorMode.BRIGHTNESS in self.supported_color_modes:
            # If turned on without specific brightness, and brightness isn't set,
            # ensure a default brightness if applicable (e.g. 100%)
            # This depends on device behavior; some restore last brightness.
            # For now, we'll assume the device handles its default brightness on simple 'on'.
            pass


        # After making changes, request HA to update the state
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        _LOGGER.debug(f"Turning off light: {self.name}")
        self.pydreo_device.light_on = False
        self.async_write_ha_state()
