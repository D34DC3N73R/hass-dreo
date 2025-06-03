"""Support for Dreo Lights (fan lights, night lights)."""

import logging
from typing import Any, Callable, List, Optional, Coroutine

from .haimports import * # pylint: disable=W0401,W0614
from homeassistant.components.light import (
    ATTR_BRIGHTNESS, # For future use
    # ATTR_COLOR_TEMP, # For future use - Replaced by ATTR_COLOR_TEMP_KELVIN
    ATTR_RGB_COLOR,  # For future use
    ATTR_COLOR_TEMP_KELVIN, # For future use
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


# List of light features that might be supported by Dreo devices
# We will check for these attributes on the pydreo_device
# For now, we only support on/off. Brightness, color temp, etc., are future enhancements.
SUPPORTED_LIGHT_FEATURES = [
    DreoLightEntityDescription(
        key="light_on", # Main light, typically for fans
        name="Light",
        pydreo_light_attr="light_on", # Assumes pydreo device has a 'light_on' attribute
        icon="hass:lightbulb",
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
) -> list[DreoLightHA]:
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
        _LOGGER.debug("Light Setup: Checking device %s (%s) for light features.", pydreo_device.name, pydreo_device.sn)
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
        super().__init__(hass, pydreo_manager, pydreo_device)
        self.entity_description = description
        self._pydreo_device = pydreo_device # Store the raw pydreo device

        # Set unique ID and name based on the main device and the light feature key
        self._attr_unique_id = f"{self._pydreo_device.sn}-{self.entity_description.key}"
        self._attr_name = f"{self._pydreo_device.name} {self.entity_description.name}"

        self._pydreo_light_control_attr = description.pydreo_light_attr
        self._value_fn = description.value_fn
        self._set_fn = description.set_fn

        # Set supported color modes - only On/Off for now
        self._attr_supported_color_modes = {ColorMode.ONOFF}
        self._attr_color_mode = ColorMode.ONOFF # Current color mode

        _LOGGER.debug("DreoLightHA initialized for %s", self.name)
        _LOGGER.debug("Light control attribute: %s", self._pydreo_light_control_attr)
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
            # await self._pydreo_manager.update_device_state(self._pydreo_device.sn, self._pydreo_light_control_attr, value_to_set)

            # Assuming direct boolean set or pydreo handles it via generic set_state
            # The DreoBaseDeviceHA should have a method to send updates.
            # Let's use a generic method from DreoBaseDeviceHA if it exists,
            # or call pydreo_manager directly.
            # Example: await self.pydreo_manager.update_device_state(self.pydreo_device.sn, {self._pydreo_light_control_attr: state})

            # Using the set_state method from the PyDreoDevice object itself
            if hasattr(self._pydreo_device, 'set_state'):
                 # This is a generic method, need to check how it works for specific light attrs
                 # It might be self._pydreo_device.set_state({self._pydreo_light_control_attr: state})
                 # Or, pydreo might have specific methods like `set_light_on(True)`
                 # For now, let's assume a generic `set_state` or direct attribute setting if simpler.
                 # The PyDreo library seems to use `device.set_state(capability_name, value)`
                 await self._hass.async_add_executor_job(
                     self._pydreo_device.set_state, self._pydreo_light_control_attr, state
                 )
                 _LOGGER.info("Successfully set %s to %s for %s", self._pydreo_light_control_attr, state, self.name)
            else:
                _LOGGER.warning("Device %s does not have a 'set_state' method. Cannot control light %s.", self._pydreo_device.name, self.name)

        else:
            _LOGGER.warning("No control attribute or set function defined for %s", self.name)

        # After sending command, request an update to refresh HA state
        await self._pydreo_manager.request_update(self._pydreo_device.sn)


    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        _LOGGER.debug("Turning on light: %s", self.name)
        await self._set_pydreo_state(True)
        # Brightness, color temp, RGB handling would go here
        # if ATTR_BRIGHTNESS in kwargs:
        #     _LOGGER.debug("Setting brightness: %s (Not yet implemented)", kwargs[ATTR_BRIGHTNESS])
        #     # await self._pydreo_device.set_brightness(kwargs[ATTR_BRIGHTNESS]) # Future
        # if ATTR_COLOR_TEMP_KELVIN in kwargs: # Updated constant
        #     _LOGGER.debug("Setting color temp: %s (Not yet implemented)", kwargs[ATTR_COLOR_TEMP_KELVIN])
        #     # await self._pydreo_device.set_color_temp(kwargs[ATTR_COLOR_TEMP_KELVIN]) # Future
        # if ATTR_RGB_COLOR in kwargs:
        #     _LOGGER.debug("Setting RGB color: %s (Not yet implemented)", kwargs[ATTR_RGB_COLOR])
        #     # await self._pydreo_device.set_rgb_color(kwargs[ATTR_RGB_COLOR]) # Future


    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        _LOGGER.debug("Turning off light: %s", self.name)
        await self._set_pydreo_state(False)

    # Placeholder for brightness property (future)
    # @property
    # def brightness(self) -> Optional[int]:
    #     """Return the brightness of this light between 0..255."""
    #     # if self.entity_description.pydreo_brightness_attr:
    #     #    return getattr(self._pydreo_device, self.entity_description.pydreo_brightness_attr, None)
    #     return None

    # Placeholder for color_temp property (future)
    # @property
    # def color_temp(self) -> Optional[int]:
    #     """Return the CT color value in mireds."""
    #     # if self.entity_description.pydreo_color_temp_attr:
    #     #    return getattr(self._pydreo_device, self.entity_description.pydreo_color_temp_attr, None)
    #     return None

    # Placeholder for rgb_color property (future)
    # @property
    # def rgb_color(self) -> Optional[tuple[int, int, int]]:
    #     """Return the rgb color value."""
    #     # if self.entity_description.pydreo_rgb_attr:
    #     #    return getattr(self._pydreo_device, self.entity_description.pydreo_rgb_attr, None)
    #     return None

    # Ensure supported_color_modes is updated if brightness/color_temp/rgb are added
    # For example, if brightness is supported:
    # self._attr_supported_color_modes = {ColorMode.ONOFF, ColorMode.BRIGHTNESS}
    # self._attr_color_mode = ColorMode.BRIGHTNESS
    # If color temp is supported:
    # self._attr_supported_color_modes = {ColorMode.ONOFF, ColorMode.COLOR_TEMP}
    # self._attr_color_mode = ColorMode.COLOR_TEMP
    # If RGB is supported:
    # self._attr_supported_color_modes = {ColorMode.ONOFF, ColorMode.RGB} # Or {ColorMode.RGB} if it implies on/off
    # self._attr_color_mode = ColorMode.RGB

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
        # Update other attributes like brightness, color_temp if they become available
        # For example:
        # if self.entity_description.pydreo_brightness_attr:
        #     self._attr_brightness = getattr(self._pydreo_device, self.entity_description.pydreo_brightness_attr, self._attr_brightness)

        # If you need to call async_write_ha_state(), do it here.
        # self.async_write_ha_state() -> This is now handled by DreoBaseDeviceHA's _handle_coordinator_update or by state change above.
        # No, DreoBaseDeviceHA's _handle_coordinator_update calls this. This method needs to update its own state.
        # The async_write_ha_state() should be called if any attribute that HA tracks changes.
        # The self._attr_is_on is the primary one for LightEntity's basic state.
        # DreoBaseDeviceHA likely calls self.async_write_ha_state() after this method returns,
        # or this method should ensure it's called if internal HA-tracked state changes.
        # Let's rely on the base class to call async_write_ha_state() if its update logic is generic enough,
        # otherwise, call it here explicitly if _attr_is_on (or other _attr_*) changes.
        # Added explicit call above.
