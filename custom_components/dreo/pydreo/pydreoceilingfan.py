"""Dreo API for controling fans."""

import logging
from typing import TYPE_CHECKING, Dict

from .constant import (
    LOGGER_NAME,
    FANON_KEY,
    LIGHTON_KEY,
    WINDLEVEL_KEY,
    SPEED_RANGE,
    BRIGHTNESS_KEY, # Now officially defined in constant.py
    COLOR_TEMP_KEY, # Now officially defined in constant.py
    RGB_COLOR_KEY,   # Now officially defined in constant.py
)

from .pydreofanbase import PyDreoFanBase
from .models import DreoDeviceDetails

_LOGGER = logging.getLogger(LOGGER_NAME)

if TYPE_CHECKING:
    from pydreo import PyDreo


class PyDreoCeilingFan(PyDreoFanBase):
    """Base class for Dreo Fan API Calls."""

    def __init__(self, device_definition: DreoDeviceDetails, details: Dict[str, list], dreo: "PyDreo"):
        """Initialize air devices."""
        super().__init__(device_definition, details, dreo)
        
        self._speed_range = None
        if (device_definition.device_ranges is not None):
            self._speed_range = device_definition.device_ranges[SPEED_RANGE]
        if (self._speed_range is None):
            self._speed_range = self.parse_speed_range(details)
        self._preset_modes = device_definition.preset_modes
        if (self._preset_modes is None):
            self._preset_modes = self.parse_preset_modes(details)

        self._fan_speed = None
        self._light_on = None
        self._brightness = None
        self._color_temp = None
        self._rgb_color = None

        self._wind_type = None
        self._wind_mode = None

        self._device_definition = device_definition

        # Initialize light capability attributes
        self.supports_brightness: bool = False
        self.supports_color_temp: bool = False
        self.supports_rgb: bool = False  # Assume False unless explicitly found
        self.min_kelvin: int | None = None
        self.max_kelvin: int | None = None
        self.device_color_temp_range_min: int | None = None
        self.device_color_temp_range_max: int | None = None

        # Parse controlsConf for light capabilities
        controls_conf = details.get("controlsConf", {})
        if isinstance(controls_conf, dict): # Ensure controls_conf is a dictionary
            control_items = controls_conf.get("control", [])
            if isinstance(control_items, list): # Ensure control_items is a list
                for item in control_items:
                    if isinstance(item, dict) and item.get("type") == "CFLight": # Ensure item is a dictionary
                        cflight_items = item.get("items", [])
                        if isinstance(cflight_items, list): # Ensure cflight_items is a list
                            for inner_item in cflight_items:
                                if isinstance(inner_item, dict): # Ensure inner_item is a dictionary
                                    inner_item_type = inner_item.get("type")
                                    if inner_item_type == "light":
                                        self.supports_brightness = True
                                    elif inner_item_type == "color":
                                        self.supports_color_temp = True
                                        self.device_color_temp_range_min = inner_item.get("minValue", 0)
                                        self.device_color_temp_range_max = inner_item.get("maxValue", 100)
                                        # Fixed Kelvin range mapping for DR-HCF003S (0-100)
                                        # This might need to be model-specific if other models differ.
                                        self.min_kelvin = 2700
                                        self.max_kelvin = 6500
                                    elif inner_item_type == "rgb": # Placeholder for actual RGB key
                                        self.supports_rgb = True
                        break # Found CFLight, no need to check other top-level control items

        _LOGGER.debug(
            f"{self.name}: Light capabilities: Brightness={self.supports_brightness}, "
            f"ColorTemp={self.supports_color_temp} (DeviceRange: {self.device_color_temp_range_min}-"
            f"{self.device_color_temp_range_max}, Kelvin: {self.min_kelvin}-{self.max_kelvin}), "
            f"RGB={self.supports_rgb}"
        )

    def parse_preset_modes(self, details: Dict[str, list]) -> tuple[str, int]:
        """Parse the preset modes from the details."""
        preset_modes = []
        controls_conf = details.get("controlsConf", None)
        if controls_conf is not None:
            control = controls_conf.get("control", None)
            if (control is not None):
                for control_item in control:
                    if (control_item.get("type", None) == "CFFan"):
                        for mode_item in control_item.get("items", None):
                            text = self.get_mode_string(mode_item.get("text", None))
                            value = mode_item.get("value", None)
                            preset_modes.append((text, value))

        preset_modes.sort(key=lambda tup: tup[1])  # sorts in place
        if (len(preset_modes) == 0):
            _LOGGER.debug("PyDreoFan:No preset modes detected")
            preset_modes = None
        _LOGGER.debug("PyDreoFan:Detected preset modes - %s", preset_modes)
        return preset_modes

    # Note: is_on getter is inherited from PyDreoFanBase
    # The setter for is_on in PyDreoFanBase was:
    # @is_on.setter
    # def is_on(self, value: bool): ... self._send_command(self._power_on_key, value)
    # Here, we provide an async version for the ceiling fan's specific FANON_KEY.
    async def async_set_is_on(self, value: bool): # Overrides/implements for ceiling fan
        """Set if the fan is on or off"""
        _LOGGER.debug("PyDreoCeilingFan:async_set_is_on - %s", value)
        # self._is_on = bool(value) # Optimistic update removed, rely on state updates
        await self._send_command(FANON_KEY, bool(value))

    @property
    def light_on(self):
        """Returns `True` if the device light is on, `False` otherwise."""
        return self._light_on

    async def async_set_light_on(self, value: bool):
        """Set if the light is on or off"""
        _LOGGER.debug("PyDreoCeilingFan:async_set_light_on - %s", value)
        # self._light_on = value # Optimistic update removed
        await self._send_command(LIGHTON_KEY, value)

    @property
    def oscillating(self) -> bool:
        return None
    
    @oscillating.setter
    def oscillating(self, value: bool) -> None:
        raise NotImplementedError(f"Attempting to set oscillating on a device that doesn't support ({value})")

    @property
    def brightness(self) -> int | None:
        """Return the brightness of the light."""
        return self._brightness

    @brightness.setter
    def brightness(self, value: int):
        """Set the brightness of the light."""
        _LOGGER.debug("PyDreoCeilingFan:brightness.setter - %s", value)
        # This is now an async method, the original setter logic is moved to async_set_brightness
        # The original setter also optimistically updated self._brightness, which will be removed.
        raise AttributeError("Use async_set_brightness to set the brightness.")

    async def async_set_brightness(self, value: int):
        """Set the brightness of the light asynchronously."""
        _LOGGER.debug("PyDreoCeilingFan:async_set_brightness - %s", value)
        # Add any validation if necessary, e.g., range checks if known
        await self._send_command(BRIGHTNESS_KEY, value)
        # self._brightness = value # Optimistic update removed

    @property
    def color_temp(self) -> int | None:
        """Return the color temperature of the light."""
        return self._color_temp

    @color_temp.setter
    def color_temp(self, value: int):
        """Set the color temperature of the light."""
        _LOGGER.debug("PyDreoCeilingFan:color_temp.setter - %s", value)
        # This is now an async method, the original setter logic is moved to async_set_color_temp
        # The original setter also optimistically updated self._color_temp, which will be removed.
        raise AttributeError("Use async_set_color_temp to set the color temperature.")

    async def async_set_color_temp(self, value: int):
        """Set the color temperature of the light asynchronously."""
        _LOGGER.debug("PyDreoCeilingFan:async_set_color_temp - %s", value)
        # Add any validation if necessary
        await self._send_command(COLOR_TEMP_KEY, value)
        # self._color_temp = value # Optimistic update removed

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        """Return the RGB color of the light."""
        return self._rgb_color

    async def async_set_rgb_color(self, value: tuple[int, int, int]):
        """Set the RGB color of the light asynchronously."""
        _LOGGER.debug("PyDreoCeilingFan:async_set_rgb_color - %s", value)
        # Add any validation if necessary
        await self._send_command(RGB_COLOR_KEY, value)
        # self._rgb_color = value # Optimistic update removed
    
    def update_state(self, state: dict):
        """Process the state dictionary from the REST API."""
        _LOGGER.debug("PyDreoFan:update_state")
        super().update_state(state)

        self._fan_speed = self.get_state_update_value(state, WINDLEVEL_KEY)
        if self._fan_speed is None:
            _LOGGER.error("Unable to get fan speed from state. Check debug logs for more information.")

        self._is_on = self.get_state_update_value(state, FANON_KEY)
        self._light_on = self.get_state_update_value(state, LIGHTON_KEY)
        self._brightness = self.get_state_update_value(state, BRIGHTNESS_KEY)
        self._color_temp = self.get_state_update_value(state, COLOR_TEMP_KEY)
        self._rgb_color = self.get_state_update_value(state, RGB_COLOR_KEY)


    def handle_server_update(self, message):
        """Process a websocket update"""
        _LOGGER.debug("PyDreoCeilingFan:handle_server_update")
        super().handle_server_update(message)

        val_power_on = self.get_server_update_key_value(message, FANON_KEY)
        if isinstance(val_power_on, bool):
            self._is_on = val_power_on

        val_light_on = self.get_server_update_key_value(message, LIGHTON_KEY)
        if isinstance(val_light_on, bool):
            self._light_on = val_light_on

        val_brightness = self.get_server_update_key_value(message, BRIGHTNESS_KEY)
        if isinstance(val_brightness, int):
            self._brightness = val_brightness

        val_color_temp = self.get_server_update_key_value(message, COLOR_TEMP_KEY)
        if isinstance(val_color_temp, int):
            self._color_temp = val_color_temp

        val_rgb_color = self.get_server_update_key_value(message, RGB_COLOR_KEY)
        if isinstance(val_rgb_color, (list, tuple)) and len(val_rgb_color) == 3:
            # Ensure it's stored as a tuple
            self._rgb_color = tuple(val_rgb_color)
