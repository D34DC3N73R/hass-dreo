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
    def min_color_temp_kelvin(self) -> int | None:
        """Return the minimum Kelvin value for color temperature."""
        return self.pydreo_device.min_kelvin

    @property
    def max_color_temp_kelvin(self) -> int | None:
        """Return the maximum Kelvin value for color temperature."""
        return self.pydreo_device.max_kelvin

    def _kelvin_to_device_range(self, kelvin_value: int) -> int | None:
        """Convert Kelvin to device's native color temperature range."""
        if not all([
            self.pydreo_device.min_kelvin is not None,
            self.pydreo_device.max_kelvin is not None,
            self.pydreo_device.device_color_temp_range_min is not None,
            self.pydreo_device.device_color_temp_range_max is not None,
        ]):
            _LOGGER.debug(f"{self.name}: Color temp range attributes not fully defined on pydreo_device.")
            return None
        
        # Avoid division by zero if Kelvin range is invalid (min == max)
        if self.pydreo_device.min_kelvin == self.pydreo_device.max_kelvin:
            if kelvin_value == self.pydreo_device.min_kelvin: # If single value, it must match
                 # Return the middle of the device range, or min, if single point mapping
                return (self.pydreo_device.device_color_temp_range_min + self.pydreo_device.device_color_temp_range_max) // 2
            _LOGGER.debug(f"{self.name}: Kelvin range is zero (min_kelvin == max_kelvin). Cannot map.")
            return None


        k_min = self.pydreo_device.min_kelvin
        k_max = self.pydreo_device.max_kelvin
        d_min = self.pydreo_device.device_color_temp_range_min
        d_max = self.pydreo_device.device_color_temp_range_max

        clamped_k = max(k_min, min(kelvin_value, k_max))
        percentage = (clamped_k - k_min) / (k_max - k_min)
        device_value = d_min + percentage * (d_max - d_min)
        
        return round(max(d_min, min(device_value, d_max)))

    def _device_range_to_kelvin(self, device_value: int) -> int | None:
        """Convert device's native color temperature value to Kelvin."""
        if not all([
            self.pydreo_device.min_kelvin is not None,
            self.pydreo_device.max_kelvin is not None,
            self.pydreo_device.device_color_temp_range_min is not None,
            self.pydreo_device.device_color_temp_range_max is not None,
        ]):
            _LOGGER.debug(f"{self.name}: Color temp range attributes not fully defined on pydreo_device for reverse mapping.")
            return None

        # Avoid division by zero if device range is invalid (min == max)
        if self.pydreo_device.device_color_temp_range_min == self.pydreo_device.device_color_temp_range_max:
            if device_value == self.pydreo_device.device_color_temp_range_min: # If single value, it must match
                # Return the middle of the Kelvin range, or min, if single point mapping
                return (self.pydreo_device.min_kelvin + self.pydreo_device.max_kelvin) // 2
            _LOGGER.debug(f"{self.name}: Device color temp range is zero. Cannot map to Kelvin.")
            return None

        k_min = self.pydreo_device.min_kelvin
        k_max = self.pydreo_device.max_kelvin
        d_min = self.pydreo_device.device_color_temp_range_min
        d_max = self.pydreo_device.device_color_temp_range_max

        clamped_d = max(d_min, min(device_value, d_max))
        percentage = (clamped_d - d_min) / (d_max - d_min)
        kelvin_value = k_min + percentage * (k_max - k_min)
        
        return round(max(k_min, min(kelvin_value, k_max)))

    @property
    def color_temp(self) -> int | None:
        """Return the color temperature in Kelvin."""
        device_native_value = self.pydreo_device.color_temp
        if device_native_value is None or not self.pydreo_device.supports_color_temp:
            return None
        
        kelvin_value = self._device_range_to_kelvin(device_native_value)
        if kelvin_value is None:
            _LOGGER.warning(
                f"{self.name}: Could not map device color temp value '{device_native_value}' to Kelvin. "
                f"Device range: {self.pydreo_device.device_color_temp_range_min}-"
                f"{self.pydreo_device.device_color_temp_range_max}, "
                f"Kelvin range: {self.pydreo_device.min_kelvin}-{self.pydreo_device.max_kelvin}"
            )
        return kelvin_value
        
    @property
    def hs_color(self) -> tuple[float, float] | None:
        """Return the hs color value."""
        if self.pydreo_device.rgb_color is None:
            return None
        # Convert device's RGB to HA's HS
        return color_RGB_to_hs(*self.pydreo_device.rgb_color)

    @property
    def supported_color_modes(self) -> set[ColorMode] | None:
        modes = set()
        # Check device capabilities from self.pydreo_device
        # These boolean flags (supports_brightness, supports_color_temp, supports_rgb)
        # are assumed to be correctly set on self.pydreo_device by PyDreoCeilingFan.

        if self.pydreo_device.supports_rgb:
            modes.add(ColorMode.HS)
            # Per HA docs, HS implies BRIGHTNESS
            modes.add(ColorMode.BRIGHTNESS)
        
        if self.pydreo_device.supports_color_temp:
            modes.add(ColorMode.COLOR_TEMP)
            # Per HA docs, COLOR_TEMP implies BRIGHTNESS
            modes.add(ColorMode.BRIGHTNESS)
        
        # If brightness is supported independently (e.g., a dimmable white light)
        # and not already added due to HS or ColorTemp having added it.
        # This also covers the case where only brightness is supported.
        if self.pydreo_device.supports_brightness:
            modes.add(ColorMode.BRIGHTNESS)
            
        # If, after all checks, no modes for HS, COLOR_TEMP, or BRIGHTNESS are added,
        # then it's an ONOFF-only light.
        if not modes:
            # This case implies self.pydreo_device.supports_brightness, 
            # self.pydreo_device.supports_color_temp, and 
            # self.pydreo_device.supports_rgb are all False.
            # Such a light would only support on/off.
            return {ColorMode.ONOFF}
        
        # _LOGGER.debug is already present in the file from a previous change.
        # You can keep or remove the _LOGGER.debug line for the final version as preferred.
        # For this subtask, ensure the core logic above is implemented.
        # Example: _LOGGER.debug(f"Device {self.name} calculated supported_color_modes: {modes}")
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
        if not self.pydreo_device.light_on: # Check current state before sending command
            await self.pydreo_device.async_set_light_on(True)
            # Potentially add a small delay here if needed for the device to register 'on'
            # await asyncio.sleep(0.1) # Typically not needed if commands are awaited

        # Color setting takes precedence
        if ATTR_HS_COLOR in kwargs and ColorMode.HS in self.supported_color_modes:
            hs_color = kwargs[ATTR_HS_COLOR]
            rgb_color = color_hs_to_RGB(*hs_color)
            _LOGGER.debug(f"Setting HS color for {self.name} to {hs_color} -> RGB {rgb_color}")
            await self.pydreo_device.async_set_rgb_color(cast(tuple[int,int,int], rgb_color))
            # Assuming pydreo_device.async_set_rgb_color handles clearing color_temp if necessary

        elif ATTR_COLOR_TEMP_KELVIN in kwargs and ColorMode.COLOR_TEMP in self.supported_color_modes:
            kelvin_value = kwargs[ATTR_COLOR_TEMP_KELVIN]
            device_value = self._kelvin_to_device_range(kelvin_value)
            if device_value is not None:
                _LOGGER.debug(f"Setting color temp for {self.name} to {kelvin_value}K -> Device value {device_value}")
                await self.pydreo_device.async_set_color_temp(device_value)
                # Assuming pydreo_device.async_set_color_temp handles clearing rgb_color if necessary
            else:
                _LOGGER.warning(f"Could not map Kelvin value {kelvin_value} to device range for {self.name}")
        
        # Brightness can be set in conjunction with color or independently
        if ATTR_BRIGHTNESS in kwargs and ColorMode.BRIGHTNESS in self.supported_color_modes:
            ha_brightness = kwargs[ATTR_BRIGHTNESS]
            # Scale HA's 0-255 to device's 1-100
            device_brightness = round((ha_brightness / HA_BRIGHTNESS_MAX) * (DEVICE_BRIGHTNESS_MAX - DEVICE_BRIGHTNESS_MIN)) + DEVICE_BRIGHTNESS_MIN
            device_brightness = max(DEVICE_BRIGHTNESS_MIN, min(device_brightness, DEVICE_BRIGHTNESS_MAX))
            
            _LOGGER.debug(f"Setting brightness for {self.name} to {ha_brightness} (HA) -> {device_brightness} (Device)")
            await self.pydreo_device.async_set_brightness(device_brightness)
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
        await self.pydreo_device.async_set_light_on(False)
        self.async_write_ha_state()
