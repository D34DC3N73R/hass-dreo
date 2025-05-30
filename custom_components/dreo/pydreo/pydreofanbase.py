"""Dreo API for controling fans."""
import logging
from typing import TYPE_CHECKING, Dict

from .constant import (
    LOGGER_NAME,
    POWERON_KEY,
    FANON_KEY,
    WINDLEVEL_KEY,
    TEMPERATURE_KEY,
    LEDALWAYSON_KEY,
    VOICEON_KEY,
    WINDTYPE_KEY,
    WIND_MODE_KEY,
    LIGHTSENSORON_KEY,
    MUTEON_KEY,
    PM25_KEY,
    TemperatureUnit,
    SPEED_RANGE,
    DreoDeviceSetting,
    PREFERENCE_TYPE_TEMPERATURE_CALIBRATION
)
 
from .pydreobasedevice import PyDreoBaseDevice
from .models import DreoDeviceDetails
from .helpers import Helpers

_LOGGER = logging.getLogger(LOGGER_NAME)

if TYPE_CHECKING:
    from pydreo import PyDreo


class PyDreoFanBase(PyDreoBaseDevice):
    """Base class for Dreo Fan API Calls."""

    def __init__(self, device_definition: DreoDeviceDetails, details: Dict[str, list], dreo: "PyDreo"):
        """Initialize air devices."""
        super().__init__(device_definition, details, dreo)
        
        self._speed_range = None
        # Check if the device has a speed range defined in the device definition
        # If not, parse the speed range from the details
        if device_definition.device_ranges is not None and SPEED_RANGE in device_definition.device_ranges:
            self._speed_range = device_definition.device_ranges[SPEED_RANGE]
        if (self._speed_range is None):
            self._speed_range = self.parse_speed_range(details)
        self._preset_modes = device_definition.preset_modes
        if (self._preset_modes is None):
            self._preset_modes = self.parse_preset_modes(details)

        # Check to see if temperature calibration is supported.
        self._temperature_offset = None
        if self.is_preference_supported(PREFERENCE_TYPE_TEMPERATURE_CALIBRATION, details):
            self._temperature_offset = int(self.get_setting(dreo, DreoDeviceSetting.FAN_TEMP_OFFSET, 0))

        self._is_on = False
        self._power_on_key = None
        self._fan_speed = None

        self._wind_type = None
        self._wind_mode = None

        self._temperature = None
        self._led_always_on = None
        self._voice_on = None
        self._light_sensor_on = None
        self._mute_on = None
        self._pm25 = None

    def parse_speed_range(self, details: Dict[str, list]) -> tuple[int, int]:
        """Parse the speed range from the details."""
        # There are a bunch of different places this could be, so we're going to look in
        # multiple places.
        speed_range : tuple[int, int] = None
        controls_conf = details.get("controlsConf", None)
        if controls_conf is not None:
            extra_configs = controls_conf.get("extraConfigs")
            if (extra_configs is not None):
                _LOGGER.debug("PyDreoFan:Detected extraConfigs")
                for extra_config_item in extra_configs:
                    if extra_config_item.get("key", None) == "control":
                        _LOGGER.debug("PyDreoFan:Detected extraConfigs/control")
                        speed_range = self.parse_speed_range_from_control_node(extra_config_item.get("value", None))
                        if (speed_range is not None):
                            _LOGGER.debug("PyDreoFan:Detected speed range from extraConfig - %s", speed_range)
                            return speed_range

            control_node = controls_conf.get("control", None)
            if (control_node is not None):
                speed_range = self.parse_speed_range_from_control_node(control_node)
                _LOGGER.debug("PyDreoFan:Detected speed range from controlsConf - %s", speed_range)
                return speed_range
        return None

    def parse_speed_range_from_control_node(self, control_node) -> tuple[int, int]:
        """Parse the speed range from a control node"""
        for control_item in control_node:
            if control_item.get("type", None) == "Speed":
                speed_low = control_item.get("items", None)[0].get("value", None)
                speed_high = control_item.get("items", None)[1].get("value", None)
                speed_range = (speed_low, speed_high)
                return speed_range
        return None
    
    def parse_preset_modes(self, details: Dict[str, list]) -> tuple[str, int]:
        """Parse the preset modes from the details."""
        raise NotImplementedError
    
    @property
    def speed_range(self):
        """Get the speed range"""
        return self._speed_range

    @property
    def preset_modes(self) -> list[str]:
        """Get the list of preset modes"""
        if self._preset_modes is None:
            return None
        return Helpers.get_name_list(self._preset_modes)
    
    @property
    def is_on(self):
        """Returns `True` if the device is on, `False` otherwise."""
        return self._is_on

    async def async_set_is_on(self, value: bool):
        """Set if the fan is on or off"""
        _LOGGER.debug("PyDreoFanBase:async_set_is_on - %s", value)
        # Retain direct update of self._is_on as per subtask instruction for this specific setter.
        self._is_on = bool(value)
        await self._send_command(self._power_on_key, bool(value))

    @property
    def fan_speed(self):
        """Return the current fan speed"""
        return self._fan_speed

    async def async_set_fan_speed(self, fan_speed: int):
        """Set the fan speed."""
        if self._speed_range is None:
            _LOGGER.error("Cannot set fan speed, speed range not available.")
            raise ValueError("Speed range not available for this device.")
        if fan_speed < self._speed_range[0] or fan_speed > self._speed_range[1]:
            _LOGGER.error("Fan speed %s is not in the acceptable range: %s",
                          fan_speed,
                          self._speed_range)
            raise ValueError(f"fan_speed must be between {self._speed_range[0]} and {self._speed_range[1]}")
        await self._send_command(WINDLEVEL_KEY, fan_speed)

    @property
    def preset_mode(self):
        """Return the current preset mode."""
        """There seems to be a bug in HA fan entity where it does call into preset_mode even if the
        preset_mode is not supported.  So we need to check if the preset mode is supported before
        returning the value."""
        if self._preset_modes is None:
            return None
        
        mode = self._wind_mode
        if mode is None:
            mode = self._wind_type
        if mode is None:
            return None
        
        str_value : str = Helpers.name_from_value(self._preset_modes, mode)
        if (str_value is None):
            return None
        
        return str_value    

    async def async_set_preset_mode(self, value: str) -> None:
        key: str = None
        # Determine which key to use based on device state
        # This logic was part of the original setter.
        if self._wind_type is not None and WINDTYPE_KEY in self._feature_key_names: # Check if feature is mapped
            key = self._feature_key_names[WINDTYPE_KEY]
        elif self._wind_mode is not None and WIND_MODE_KEY in self._feature_key_names: # Check if feature is mapped
            key = self._feature_key_names[WIND_MODE_KEY]
        elif self._wind_type is not None: # Fallback if not in feature_key_names but state exists
             key = WINDTYPE_KEY
        elif self._wind_mode is not None: # Fallback if not in feature_key_names but state exists
             key = WIND_MODE_KEY
        else:
            # If preset modes are defined, but no way to set them (no wind_type or wind_mode state)
            if self._preset_modes:
                 _LOGGER.warning(f"Device {self.name} has preset_modes but no active wind_type or wind_mode state to determine command key.")
                 # Attempt a default or raise error. For now, let's try WINDTYPE_KEY if presets exist.
                 # This part might need device-specific logic or better capability detection.
                 key = WINDTYPE_KEY # Defaulting, might need adjustment
            else:
                raise NotImplementedError("Attempting to set preset_mode on a device that doesn't support or has no way to determine command key.")

        numeric_value = Helpers.value_from_name(self._preset_modes, value)
        if numeric_value is not None:
            await self._send_command(key, numeric_value)
        else:
            raise ValueError(f"Preset mode {value} is not in the acceptable list: {self.preset_modes}")

    @property
    def temperature(self):
        """Get the temperature"""
        temp = self._temperature
        if (self.temperature_offset is not None):
            temp += self.temperature_offset
        return temp

    @property
    def temperature_units(self) -> TemperatureUnit:
        """Get the temperature units."""
        # I'm not sure how the API returns in other regions, so I'm just auto-detecting
        # based on some reasonable range.

        # Going to return Celsius as the default.  None of this matters if there is no
        # temperature returned anyway
        if self._temperature is not None:
            if self._temperature > 50:
                return TemperatureUnit.FAHRENHEIT

        return TemperatureUnit.CELSIUS

    @property
    def temperature_offset(self) -> bool:
        """Get the temperature calibration value"""
        return self._temperature_offset
    
    @temperature_offset.setter
    def temperature_offset(self, value: int) -> None:
        """Set the temperature calibration value"""
        _LOGGER.debug("PyDreoFan:temperature_calibration.setter")
        if (self.temperature_offset is not None):
            self._set_setting(DreoDeviceSetting.FAN_TEMP_OFFSET, value)
        else:
            raise NotImplementedError(
                f"PyDreoFanBase: Attempting to set temperature calibration on a device that doesn't support ({value})"
            )
                                  
    @property
    def oscillating(self) -> bool:
        """Returns None if oscillation if either horizontal or vertical oscillation is on."""
        raise NotImplementedError
    
    @oscillating.setter
    def oscillating(self, value: bool) -> None:
        """Enable or disable oscillation"""
        _LOGGER.debug("PyDreoFan:oscillating.setter")
        raise NotImplementedError(f"PyDreoFanBase: Attempting to set oscillating on a device that doesn't support ({value})")

    @property
    def display_auto_off(self) -> bool:
        """Is the display always on?"""
        if self._led_always_on is not None:
            return not self._led_always_on

        return None

    async def async_set_display_auto_off(self, value: bool) -> None:
        """Set if the display is always on"""
        _LOGGER.debug("PyDreoFanBase:async_set_display_auto_off")

        if self._led_always_on is not None: # Check based on existence of the state attribute
            await self._send_command(LEDALWAYSON_KEY, not value)
        else:
            raise NotImplementedError("PyDreoFanBase: Attempting to set display always on on a device that doesn't support.")

    @property
    def adaptive_brightness(self) -> bool:
        """Is the display always on?"""
        if (self._light_sensor_on is not None):
            return self._light_sensor_on
        else:
            return None

    async def async_set_adaptive_brightness(self, value: bool) -> None:
        """Set if adaptive brightness is on"""
        _LOGGER.debug("PyDreoFanBase:async_set_adaptive_brightness")

        if self._light_sensor_on is not None: # Check based on existence of the state attribute
            await self._send_command(LIGHTSENSORON_KEY, value)
        else:
            raise NotImplementedError("PyDreoFanBase: Attempting to set adaptive brightness on a device that doesn't support.")

    @property
    def panel_sound(self) -> bool:
        """Is the panel sound on"""
        if self._voice_on is not None:
            return self._voice_on
        if self._mute_on is not None:
            return not self._mute_on
        return None

    async def async_set_panel_sound(self, value: bool) -> None:
        """Set the panel sound"""
        _LOGGER.debug("PyDreoFanBase:async_set_panel_sound")

        if self._voice_on is not None: # Check based on existence of the state attribute
            await self._send_command(VOICEON_KEY, value)
        elif self._mute_on is not None: # Check based on existence of the state attribute
            await self._send_command(MUTEON_KEY, not value)
        else:
            raise NotImplementedError("PyDreoFanBase: Attempting to set panel_sound on a device that doesn't support.")

    @property
    def pm25(self) -> int:
        """Get the PM2.5 value"""
        if self._pm25 is not None:
            return self._pm25
        return None

    async def async_set_pm25(self, value: int) -> None: # PM2.5 is unlikely to be settable, but following pattern
        """Set the PM2.5 value (Theoretical, likely read-only)."""
        _LOGGER.debug("PyDreoFanBase:async_set_pm25")

        if self._pm25 is not None: # Check based on existence of the state attribute
            # This is likely a read-only sensor, sending a command might not be supported by device.
            # Forcing the pattern application as per subtask.
            await self._send_command(PM25_KEY, value)
        else:
            raise NotImplementedError("PyDreoFanBase: Attempting to set pm25 on a device that doesn't support or is read-only.")


    def update_state(self, state: dict):
        """Process the state dictionary from the REST API."""
        _LOGGER.debug("PyDreoFanBase:update_state")
        super().update_state(state)

        power_on = self.get_state_update_value(state, POWERON_KEY)
        if power_on is not None:
            self._is_on = power_on
            self._power_on_key = POWERON_KEY
        else:
            # If power_on is not in the state, we need to check if the fan is on or off.
            fan_on = self.get_state_update_value(state, FANON_KEY)
            if fan_on is not None:
                self._is_on = fan_on
                self._power_on_key = FANON_KEY
            else:
                _LOGGER.error("Unable to get power on state from state. Check debug logs for more information.")
                self._power_on_key = None
                
        self._fan_speed = self.get_state_update_value(state, WINDLEVEL_KEY)
        if self._fan_speed is None:
            _LOGGER.error("Unable to get fan speed from state. Check debug logs for more information.")

        self._temperature = self.get_state_update_value(state, TEMPERATURE_KEY)
        self._led_always_on = self.get_state_update_value(state, LEDALWAYSON_KEY)
        self._voice_on = self.get_state_update_value(state, VOICEON_KEY)
        self._wind_type = self.get_state_update_value(state, WINDTYPE_KEY)
        self._wind_mode = self.get_state_update_value(state, WIND_MODE_KEY)
        self._light_sensor_on = self.get_state_update_value(state, LIGHTSENSORON_KEY)
        self._mute_on = self.get_state_update_value(state, MUTEON_KEY)
        self._pm25 = self.get_state_update_value(state, PM25_KEY)

    def handle_server_update(self, message):
        """Process a websocket update"""
        _LOGGER.debug("PyDreoFanBase:handle_server_update")
        super().handle_server_update(message)

        val_poweron = self.get_server_update_key_value(message, self._power_on_key)
        if isinstance(val_poweron, bool):
            self._is_on = val_poweron  # Ensure poweron state is updated
            _LOGGER.debug("PyDreoFanBase:handle_server_update - %s is %s", self._power_on_key, self._is_on)

        val_wind_level = self.get_server_update_key_value(message, WINDLEVEL_KEY)
        if isinstance(val_wind_level, int):
            self._fan_speed = val_wind_level

        val_temperature = self.get_server_update_key_value(message, TEMPERATURE_KEY)
        if isinstance(val_temperature, int):
            self._temperature = val_temperature

        val_display_always_on = self.get_server_update_key_value(message, LEDALWAYSON_KEY)
        if isinstance(val_display_always_on, bool):
            self._led_always_on = val_display_always_on

        val_panel_sound = self.get_server_update_key_value(message, VOICEON_KEY)
        if isinstance(val_panel_sound, bool):
            self._voice_on = val_panel_sound

        val_wind_mode = self.get_server_update_key_value(message, WIND_MODE_KEY)
        if isinstance(val_wind_mode, int):
            self._wind_mode = val_wind_mode

        val_wind_type = self.get_server_update_key_value(message, WINDTYPE_KEY)
        if isinstance(val_wind_type, int):
            self._wind_type = val_wind_type

        val_light_sensor = self.get_server_update_key_value(message, LIGHTSENSORON_KEY)
        if isinstance(val_light_sensor, bool):
            self._light_sensor_on = val_light_sensor

        val_mute = self.get_server_update_key_value(message, MUTEON_KEY)
        if isinstance(val_mute, bool):
            self._mute_on = val_mute

        val_pm25 = self.get_server_update_key_value(message, PM25_KEY)
        if isinstance(val_pm25, int):
            self._pm25 = val_pm25