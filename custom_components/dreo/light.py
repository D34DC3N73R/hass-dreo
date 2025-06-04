"""Support for Dreo Lights (fan lights, night lights)."""

import logging
from typing import Any, Callable, List, Optional, Coroutine
from dataclasses import dataclass

from .haimports import * # pylint: disable=W0401,W0614
from homeassistant.util.percentage import percentage_to_ranged_value # For scaling
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    # ATTR_COLOR_TEMP, # For future use - Replaced by ATTR_COLOR_TEMP_KELVIN
    ATTR_RGB_COLOR,  # For future use
    ATTR_COLOR_TEMP_KELVIN,
    ColorMode, # New enum for color modes
    LightEntity,
    LightEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .dreobasedevice import DreoBaseDeviceHA
from .const import (
    DOMAIN,
    LOGGER,
    PYDREO_MANAGER,
)
# from pydreo.constant import REPORT_TO_HA_STATE_MAPPING_LIGHT, HA_TO_PYDREO_STATE_MAPPING_LIGHT # These do not exist

_LOGGER = logging.getLogger(LOGGER)

@dataclass
class DreoLightEntityDescription(LightEntityDescription):
    """Describe Dreo light entity."""
    # Name of the attribute on the pydreo device object that controls the light
    # e.g., "light_on" for a fan light, or "ledpotkepton" for a night light on some devices
    pydreo_light_attr: Optional[str] = None
    # Optional: function to get the current value from pydreo device
    value_fn: Optional[Callable[[Any], bool]] = None
    # Optional: function to set the value on pydreo device
    set_fn: Optional[Callable[[Any, bool], Coroutine[Any, Any, None]]] = None
    # For brightness control
    pydreo_brightness_cmd: Optional[str] = None
    pydreo_brightness_range: Optional[tuple[int, int]] = None  # Min/max values pydreo expects
    # For color temperature control
    pydreo_colortemp_cmd: Optional[str] = None
    pydreo_colortemp_range: Optional[tuple[int, int]] = None  # Min/max values pydreo expects
    ha_min_color_temp_kelvin: Optional[int] = None # HA frontend min color temp in Kelvin
    ha_max_color_temp_kelvin: Optional[int] = None # HA frontend max color temp in Kelvin


# List of light features that might be supported by Dreo devices
# We will check for these attributes on the pydreo_device
# For now, we only support on/off. Brightness, color temp, etc., are future enhancements.
SUPPORTED_LIGHT_FEATURES = [
    DreoLightEntityDescription(
        key="light_on", # Main light, typically for fans
        name="Light",
        pydreo_light_attr="light_on", # Assumes pydreo device has a 'light_on' attribute
        icon="hass:lightbulb",
        pydreo_brightness_cmd="brightness",
        pydreo_colortemp_cmd="colortemp",
        pydreo_brightness_range=(1, 100), # Example: Dreo API uses 1-100
        pydreo_colortemp_range=(0, 100),   # Example: Dreo API uses 0-100 for CCT percentage
        ha_min_color_temp_kelvin=2700,     # Typical warm white
        ha_max_color_temp_kelvin=6500,     # Typical cool white / daylight
    ),
    DreoLightEntityDescription(
        key="night_light_on", # Night light or panel light, e.g. on humidifiers/purifiers
        name="Panel Light", # Or "Night Light" - adjust as needed
        pydreo_light_attr="ledpotkepton", # Assumes pydreo device has a 'ledpotkepton' attribute
        icon="hass:lightbulb-outline", # Different icon for distinction
    ),
    # TODO: Add descriptions for brightness, color temp, RGB when pydreo supports them
    # Example for brightness (conceptual):
    # TODO: Add descriptions for brightness, color temp, RGB when pydreo supports them
    # Example for brightness (conceptual):
    # DreoLightEntityDescription(
    #     key="brightness",
    #     name="Brightness",
    #     # pydreo_brightness_attr="lightbrightness", # hypothetical pydreo attribute
    #     # supported_color_modes={ColorMode.BRIGHTNESS}, # Example
    # ),
    # Example for color temp (conceptual):
    # DreoLightEntityDescription(
    #     key="color_temp",
    #     name="Color Temperature",
    #     # pydreo_color_temp_attr="colortemp", # hypothetical pydreo attribute
    #     # supported_color_modes={ColorMode.COLOR_TEMP}, # Example
    # ),
]


def get_light_entries(
    hass: HomeAssistant, pydreo_manager, pydreo_devices: list[DreoBaseDeviceHA]
) -> list['DreoLightHA']:
    """Get Dreo light entities."""
    entities = []
    for pydreo_device in pydreo_devices:
        _LOGGER.debug("Processing device: %s (%s)", pydreo_device.name, pydreo_device.sn)
        for description in SUPPORTED_LIGHT_FEATURES:
            _LOGGER.debug("Checking light feature: %s for device %s", description.key, pydreo_device.name)
            # Check if the pydreo device object has the attribute specified in pydreo_light_attr
            if description.pydreo_light_attr and hasattr(pydreo_device, description.pydreo_light_attr):
                _LOGGER.debug("Device %s HAS light attribute %s", pydreo_device.name, description.pydreo_light_attr)
                entities.append(DreoLightHA(hass, pydreo_manager, description, pydreo_device))
            elif description.value_fn and description.set_fn: # For more complex setups if needed
                 _LOGGER.debug("Device %s using value_fn/set_fn for %s", pydreo_device.name, description.key)
                 entities.append(DreoLightHA(hass, pydreo_manager, description, pydreo_device))
            else:
                _LOGGER.debug("Device %s does NOT have light attribute %s or value_fn/set_fn", pydreo_device.name, description.pydreo_light_attr or description.key)

    _LOGGER.debug("Found %d light entities", len(entities))
    return entities


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Dreo Light platform."""
    _LOGGER.info("Setting up Dreo Light platform.")
    pydreo_manager = hass.data[DOMAIN][PYDREO_MANAGER]

    # Get pydreo devices from the manager that are already wrapped by DreoBaseDeviceHA or similar
    # This part might need adjustment based on how devices are stored and accessed in __init__.py
    # For now, assuming pydreo_manager.devices directly gives us the pydreo device objects
    # and we need to wrap them or ensure they are already wrapped.
    # Let's assume pydreo_manager.devices are the raw pydreo devices.

    # In the main component setup, devices are fetched and stored.
    # We should use those hass.data entries if available, or rely on pydreo_manager.devices.
    # For simplicity, let's assume pydreo_manager.devices are the pydreo SDK device objects.

    # The `get_light_entries` function expects DreoBaseDeviceHA instances,
    # but pydreo_manager.devices are raw pydreo devices.
    # This is a mismatch with how other platforms like fan.py or switch.py might be structured.
    # Typically, the pydreo_device objects are wrapped once and then passed around.

    # Let's adjust to expect raw pydreo devices in get_light_entries for now,
    # or ensure that DreoBaseDeviceHA is instantiated correctly before this point.
    # The current `get_light_entries` expects `DreoBaseDeviceHA` instances.
    # It should ideally work with the raw `pydreo_device` and the `DreoLightHA` will wrap it.

    # Re-thinking: The DreoBaseDeviceHA is the HA-side wrapper.
    # The pydreo_manager.devices are the library-side devices.
    # We need to iterate through pydreo_manager.devices.

    light_entities = []
    for pydreo_device in pydreo_manager.devices: # These are raw pydreo.PyDreoDevice objects
        _LOGGER.debug("Light Setup: Checking device %s (%s) for light features.", pydreo_device.name, pydreo_device.serial_number)
        for description in SUPPORTED_LIGHT_FEATURES:
            # Check if the raw pydreo device has the capability
            if description.pydreo_light_attr and hasattr(pydreo_device, description.pydreo_light_attr):
                _LOGGER.info("Device %s supports light feature '%s' via attribute '%s'. Creating entity.",
                             pydreo_device.name, description.name, description.pydreo_light_attr)
                light_entities.append(DreoLightHA(hass, pydreo_manager, description, pydreo_device))
            elif description.value_fn and description.set_fn and hasattr(pydreo_device, description.key): # Fallback for complex
                 _LOGGER.info("Device %s supports light feature '%s' via value/set functions. Creating entity.",
                             pydreo_device.name, description.name)
                 light_entities.append(DreoLightHA(hass, pydreo_manager, description, pydreo_device))


    if light_entities:
        async_add_entities(light_entities)
    else:
        _LOGGER.info("No Dreo light entities found to add.")


class DreoLightHA(DreoBaseDeviceHA, LightEntity):
    """Representation of a Dreo Light."""

    entity_description: DreoLightEntityDescription

    def __init__(
        self,
        hass: HomeAssistant,
        pydreo_manager, # Type hint: PyDreo
        description: DreoLightEntityDescription,
        pydreo_device, # Type hint: PyDreoDevice from pydreo library
    ):
        """Initialize the Dreo light device."""
        self._hass = hass
        self._pydreo_manager = pydreo_manager
        super().__init__(pydreo_device)
        self.entity_description = description
        self._pydreo_device = pydreo_device # Store the raw pydreo device

        # Set unique ID and name based on the main device and the light feature key
        self._attr_unique_id = f"{self._pydreo_device.serial_number}-{self.entity_description.key}"
        self._attr_name = f"{self._pydreo_device.name} {self.entity_description.name}"

        self._pydreo_light_control_attr = description.pydreo_light_attr
        self._value_fn = description.value_fn
        self._set_fn = description.set_fn

        # Initialize supported color modes
        self._attr_supported_color_modes = {ColorMode.ONOFF}
        current_color_mode = ColorMode.ONOFF

        if self.entity_description.pydreo_brightness_cmd:
            self._attr_supported_color_modes.add(ColorMode.BRIGHTNESS)
            current_color_mode = ColorMode.BRIGHTNESS # Prioritize if available

        if self.entity_description.pydreo_colortemp_cmd:
            self._attr_supported_color_modes.add(ColorMode.COLOR_TEMP)
            current_color_mode = ColorMode.COLOR_TEMP # Prioritize Color Temp if available
            self._attr_min_color_temp_kelvin = self.entity_description.ha_min_color_temp_kelvin
            self._attr_max_color_temp_kelvin = self.entity_description.ha_max_color_temp_kelvin

        self._attr_color_mode = current_color_mode

        _LOGGER.debug("DreoLightHA initialized for %s", self.name)
        _LOGGER.debug("Light control attribute: %s, Supported Color Modes: %s, Current Color Mode: %s",
                      self._pydreo_light_control_attr, self._attr_supported_color_modes, self._attr_color_mode)
        _LOGGER.debug("Unique ID: %s", self.unique_id)


    @property
    def is_on(self) -> bool:
        """Return true if light is on."""
        current_state = self._get_pydreo_state()
        _LOGGER.debug("is_on property for %s: %s", self.name, current_state)
        return current_state

    def _get_pydreo_state(self) -> bool:
        """Get the current state of the light from the pydreo device."""
        if self._value_fn:
            return self._value_fn(self._pydreo_device)
        if self._pydreo_light_control_attr:
            val = getattr(self._pydreo_device, self._pydreo_light_control_attr, False)
            # pydreo might return "on"/"off" or True/False. HA expects boolean.
            if isinstance(val, str):
                return val.lower() == "on" # Or use REPORT_TO_HA_STATE_MAPPING_LIGHT if applicable
            return bool(val)
        return False

    async def _set_pydreo_state(self, state: bool) -> None:
        """Set the state of the light on the pydreo device."""
        _LOGGER.debug("Setting state for %s to %s", self.name, state)
        if self._set_fn:
            await self._set_fn(self._pydreo_device, state)
        elif self._pydreo_light_control_attr:
            # Map boolean HA state to what pydreo expects (e.g., "on"/"off" or True/False)
            # This might need adjustment based on pydreo's exact API for these attributes.
            # For now, assuming pydreo accepts boolean for these attributes directly,
            # or that pydreo's setters handle boolean conversion.
            # If pydreo expects "ON" / "OFF" strings:
            # value_to_set = HA_TO_PYDREO_STATE_MAPPING_LIGHT.get(state, "off")
            # await self._pydreo_manager.update_device_state(self._pydreo_device.serial_number, self._pydreo_light_control_attr, value_to_set)

            # Assuming direct boolean set or pydreo handles it via generic set_state
            # The DreoBaseDeviceHA should have a method to send updates.
            # Let's use a generic method from DreoBaseDeviceHA if it exists,
            # or call pydreo_manager directly.
            # Example: await self.pydreo_manager.update_device_state(self.pydreo_device.serial_number, {self._pydreo_light_control_attr: state})

            # Assuming self._pydreo_light_control_attr holds the correct attribute name like "light_on"
            # The actual command sending is handled by the property setter in the pydreo device class.
            await self._hass.async_add_executor_job(
                setattr, self._pydreo_device, self._pydreo_light_control_attr, state
            )
            _LOGGER.info("Attempted to set %s to %s for %s via property assignment", self._pydreo_light_control_attr, state, self.name)

        else:
            _LOGGER.warning("No control attribute or set function defined for %s", self.name)

        # After sending command, request an update to refresh HA state
        # await self._pydreo_manager.request_update(self._pydreo_device.serial_number) # Removed as per request


    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        _LOGGER.debug("Turning on light: %s", self.name)
        await self._set_pydreo_state(True) # Turn on the physical light switch first

        # Brightness handling
        if self.entity_description.pydreo_brightness_cmd and ATTR_BRIGHTNESS in kwargs:
            ha_brightness = kwargs[ATTR_BRIGHTNESS] # HA brightness is 0-255
            device_min, device_max = self.entity_description.pydreo_brightness_range

            # Scale HA brightness (0-255) to device range (e.g., 1-100)
            # Using percentage_to_ranged_value expects percentage (0-100) as input
            ha_brightness_pct = (ha_brightness / 255) * 100
            device_brightness = round(percentage_to_ranged_value((device_min, device_max), ha_brightness_pct))
            # Clamp value just in case
            device_brightness = max(device_min, min(device_max, device_brightness))

            _LOGGER.debug("Setting brightness for %s: HA value %s -> Device value %s (%s)",
                          self.name, ha_brightness, device_brightness, self.entity_description.pydreo_brightness_cmd)
            await self._hass.async_add_executor_job(
                self._pydreo_device._send_command, self.entity_description.pydreo_brightness_cmd, int(device_brightness)
            )
            # Update HA's internal state for brightness
            self._attr_brightness = ha_brightness # Store the HA value (0-255)

        # Color Temperature handling
        if self.entity_description.pydreo_colortemp_cmd and ATTR_COLOR_TEMP_KELVIN in kwargs:
            ha_kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]

            # Get device's percentage range for color temp (e.g., 0-100)
            device_min_pct, device_max_pct = self.entity_description.pydreo_colortemp_range
            # Get HA's Kelvin range for this light
            ha_min_k = self.entity_description.ha_min_color_temp_kelvin
            ha_max_k = self.entity_description.ha_max_color_temp_kelvin

            # Scale HA Kelvin value to device's percentage range
            # Ensure no division by zero if min_k == max_k
            if ha_max_k == ha_min_k:
                device_colortemp_pct = device_min_pct
            else:
                kelvin_pct_of_range = (ha_kelvin - ha_min_k) / (ha_max_k - ha_min_k)
                device_colortemp_pct = round(
                    kelvin_pct_of_range * (device_max_pct - device_min_pct) + device_min_pct
                )

            # Clamp value to device's percentage range
            device_colortemp_pct = max(device_min_pct, min(device_max_pct, device_colortemp_pct))

            _LOGGER.debug("Setting color temp for %s: HA Kelvin %s -> Device Pct %s (%s)",
                          self.name, ha_kelvin, device_colortemp_pct, self.entity_description.pydreo_colortemp_cmd)
            await self._hass.async_add_executor_job(
                self._pydreo_device._send_command, self.entity_description.pydreo_colortemp_cmd, int(device_colortemp_pct)
            )
            # Update HA's internal state for color temp
            self._attr_color_temp_kelvin = ha_kelvin # Store the HA Kelvin value

        # if ATTR_RGB_COLOR in kwargs: # Placeholder for future RGB support
        #     _LOGGER.debug("Setting RGB color: %s (Not yet implemented)", kwargs[ATTR_RGB_COLOR])


    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        _LOGGER.debug("Turning off light: %s", self.name)
        await self._set_pydreo_state(False)

    @property
    def brightness(self) -> Optional[int]:
        """Return the brightness of this light between 0..255."""
        if ColorMode.BRIGHTNESS not in self._attr_supported_color_modes: # Check internal attr
            return None
        # As per instructions, returning self._attr_brightness managed by LightEntity
        return self._attr_brightness

    @property
    def color_temp_kelvin(self) -> Optional[int]:
        """Return the CT color value in Kelvin."""
        if ColorMode.COLOR_TEMP not in self._attr_supported_color_modes: # Check internal attr
            return None
        # As per instructions, returning self._attr_color_temp_kelvin managed by LightEntity
        return self._attr_color_temp_kelvin

    # Placeholder for rgb_color property (future)
    # @property
    # def rgb_color(self) -> Optional[tuple[int, int, int]]:
    #     """Return the rgb color value."""
    #     # if ColorMode.RGB in self._attr_supported_color_modes:
    #     #    # Logic to get RGB from self._pydreo_device or self._attr_rgb_color
    #     return None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # Use the availability logic from DreoBaseDeviceHA
        return super().available and hasattr(self._pydreo_device, self._pydreo_light_control_attr if self._pydreo_light_control_attr else "")

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # This method is called by the coordinator in DreoBaseDeviceHA
        # Update the entity's state based on the new data in self._pydreo_device
        new_state = self._get_pydreo_state()
        _LOGGER.debug("Coordinator update for %s: new_state=%s, current_ha_state=%s", self.name, new_state, self._attr_is_on)
        if self._attr_is_on != new_state:
            self._attr_is_on = new_state
            self.async_write_ha_state()
        # Update other attributes like brightness, color_temp if they become available from device state.
        # As per instructions, for now, we are not reading brightness/colortemp from the device state here,
        # as pydreo library limitations make it unreliable. HA will use the last set values stored in
        # self._attr_brightness and self._attr_color_temp_kelvin.

        # If pydreo device state provided reliable brightness/colortemp:
        # old_brightness = self._attr_brightness
        # if ColorMode.BRIGHTNESS in self._attr_supported_color_modes and self.entity_description.pydreo_brightness_cmd:
        #     device_val = getattr(self._pydreo_device, self.entity_description.pydreo_brightness_cmd, None)
        #     if device_val is not None:
        #         # Scale device_val (e.g. 1-100) to HA brightness (0-255)
        #         dev_min_b, dev_max_b = self.entity_description.pydreo_brightness_range
        #         self._attr_brightness = round( ((device_val - dev_min_b) / (dev_max_b - dev_min_b)) * 255 ) if dev_max_b != dev_min_b else 0
        #
        # old_color_temp = self._attr_color_temp_kelvin
        # if ColorMode.COLOR_TEMP in self._attr_supported_color_modes and self.entity_description.pydreo_colortemp_cmd:
        #     device_pct_val = getattr(self._pydreo_device, self.entity_description.pydreo_colortemp_cmd, None)
        #     if device_pct_val is not None:
        #         # Scale device_pct_val (e.g. 0-100) to HA Kelvin
        #         dev_min_pct, dev_max_pct = self.entity_description.pydreo_colortemp_range
        #         ha_min_k = self.entity_description.ha_min_color_temp_kelvin
        #         ha_max_k = self.entity_description.ha_max_color_temp_kelvin
        #         if dev_max_pct != dev_min_pct:
        #              pct_of_range = (device_pct_val - dev_min_pct) / (dev_max_pct - dev_min_pct)
        #              self._attr_color_temp_kelvin = round(pct_of_range * (ha_max_k - ha_min_k) + ha_min_k)
        #         else:
        #              self._attr_color_temp_kelvin = ha_min_k


        # Only call async_write_ha_state if a relevant attribute changed.
        # The is_on change is handled above. If brightness/colortemp were updated from device:
        # if self._attr_is_on != new_state or self._attr_brightness != old_brightness or self._attr_color_temp_kelvin != old_color_temp:
        #    self.async_write_ha_state()
        # For now, only is_on change triggers write_ha_state from here.
        # Brightness/ColorTemp changes via turn_on will trigger their own update via LightEntity base.
