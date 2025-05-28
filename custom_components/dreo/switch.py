"""Support additional switches for some Dreo devices"""
# Suppress warnings about DataClass constructors
# pylint: disable=E1123

# Suppress warnings about unused function arguments
# pylint: disable=W0613
from __future__ import annotations

from typing import Any
from dataclasses import dataclass
import logging

from .haimports import *  # pylint: disable=W0401,W0614
from .dreobasedevice import DreoBaseDeviceHA
from .dreochefmaker import DreoChefMakerHA
from .pydreo import PyDreo, PyDreoBaseDevice
from .pydreo.constant import DreoDeviceType

from .const import LOGGER, DOMAIN, PYDREO_MANAGER

_LOGGER = logging.getLogger(LOGGER)


@dataclass
class DreoSwitchEntityDescription(SwitchEntityDescription):
    """Describe Dreo Switch entity."""

    attr_name: str = None
    icon: str = None


SWITCHES: tuple[DreoSwitchEntityDescription, ...] = (
    DreoSwitchEntityDescription(
        key="Horizontally Oscillating",
        translation_key="horizontally_oscillating",
        attr_name="horizontally_oscillating",
        icon="mdi:rotate-360",
    ),
    DreoSwitchEntityDescription(
        key="Vertically Oscillating",
        translation_key="vertically_oscillating",
        attr_name="vertically_oscillating",
        icon="mdi:rotate-360",
    ),
    DreoSwitchEntityDescription(
        key="Display Auto Off",
        translation_key="display_auto_off",
        attr_name="display_auto_off",
        icon="mdi:monitor",
    ),
    DreoSwitchEntityDescription(
        key="Panel Sound",
        translation_key="panel_sound",
        attr_name="panel_sound",
        icon="mdi:volume-high",
    ),
    DreoSwitchEntityDescription(
        key="Adaptive Brightness",
        translation_key="adaptive_brightness",
        attr_name="adaptive_brightness",
        icon="mdi:monitor",
    ),
    DreoSwitchEntityDescription(
        key="Panel Mute",
        translation_key="mute_on",
        attr_name="mute_on",
        icon="mdi:volume-high",
    ),  
    DreoSwitchEntityDescription(
        key="Oscillating",
        translation_key="oscon",
        attr_name="oscon",
        icon="mdi:rotate-360",
    ),
    DreoSwitchEntityDescription(
        key="PTC", translation_key="ptcon", attr_name="ptcon", icon="mdi:help"
    ),
    DreoSwitchEntityDescription(
        key="Child Lock",
        translation_key="childlockon",
        attr_name="childlockon",
        icon="mdi:lock",
    ),
    DreoSwitchEntityDescription(    
        key="Light",
        translation_key="light",
        attr_name="ledpotkepton",
        icon="mdi:led-on",
    ),
    DreoSwitchEntityDescription(    
        key="Light",
        translation_key="light",
        attr_name="light_on",
        icon="mdi:lightbulb",
    ),
    DreoSwitchEntityDescription(    
        key="Humidify",
        translation_key="humidify",
        attr_name="humidify",
        icon="mdi:air-humidifier",
    )
)

def get_entries(pydreo_devices : list[PyDreoBaseDevice]) -> list[DreoSwitchHA]:
    """Get the Dreo Switches for the devices."""
    switch_ha_collection : DreoSwitchHA = []

    for pydreo_device in pydreo_devices:
        _LOGGER.debug("Switch:get_entries: Adding switches for %s", pydreo_device.name)
        switch_keys : list[str] = []

        for switch_definition in SWITCHES:
            _LOGGER.debug("Switch:get_entries: checking attribute: %s on %s", switch_definition.attr_name, pydreo_device.name)

            if pydreo_device.is_feature_supported(switch_definition.attr_name):
                # Check if this is the light switch for a DR-HCF ceiling fan
                if (switch_definition.attr_name == "light_on" and
                        hasattr(pydreo_device, 'type') and 
                        pydreo_device.type == DreoDeviceType.CEILING_FAN and
                        pydreo_device.model and
                        pydreo_device.model.startswith("DR-HCF")):
                    _LOGGER.debug(f"Skipping 'light_on' switch for DR-HCF model {pydreo_device.name} (Model: {pydreo_device.model}) as it will be a dedicated light entity.")
                    continue  # Skip creating this switch

                if (switch_definition.key in switch_keys):
                    # This check for duplicates should ideally be based on a more unique identifier
                    # if multiple switch_definitions can have the same key but different attr_name.
                    # However, given the current structure, we'll keep it as is.
                    # A potential issue if, for example, one device supports 'ledpotkepton' and another 'light_on'
                    # both mapping to key "Light". The first one encountered would be added.
                    # For DR-HCF, we've already skipped "light_on", so "ledpotkepton" (if supported) would still be checked.
                    _LOGGER.warning("Switch:get_entries: Duplicate switch key '%s' for device '%s'. Skipping add for attr_name '%s'. Existing switch uses attr_name for this key: %s", 
                                   switch_definition.key, pydreo_device.name, switch_definition.attr_name, 
                                   next((s.entity_description.attr_name for s in switch_ha_collection if s.entity_description.key == switch_definition.key and s.pydreo_device == pydreo_device), "unknown"))
                    continue
                
                _LOGGER.debug("Switch:get_entries: Adding switch %s (attr: %s) for %s", switch_definition.key, switch_definition.attr_name, pydreo_device.name)
                switch_keys.append(switch_definition.key) # This list helps avoid duplicate entity_description.key for the *same device*
                switch_ha_collection.append(DreoSwitchHA(pydreo_device, switch_definition))

    return switch_ha_collection


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Dreo Switch platform."""
    _LOGGER.info("Starting Dreo Switch Platform")

    pydreo_manager: PyDreo = hass.data[DOMAIN][PYDREO_MANAGER]

    switch_entities_ha : list[SwitchEntity] = []
    for pydreo_device in pydreo_manager.devices:
        if pydreo_device.type == DreoDeviceType.CHEF_MAKER:
            switch_entities_ha.append(DreoChefMakerHA(pydreo_device))
    switch_entities_to_add = get_entries(pydreo_manager.devices)

    switch_entities_ha.extend(switch_entities_to_add)

    async_add_entities(switch_entities_ha)

class DreoSwitchHA(DreoBaseDeviceHA, SwitchEntity):
    """Representation of a Switch describing a read-write property of a Dreo device."""

    def __init__(
        self, 
        pydreo_base_device: PyDreoBaseDevice, 
        description: DreoSwitchEntityDescription
    ) -> None:
        super().__init__(pydreo_base_device)
        self.pydreo_device = pydreo_base_device

        # Note this is a "magic" HA property.  Don't rename
        self.entity_description = description

        self._attr_name = super().name + " " + description.key
        self._attr_unique_id = f"{super().unique_id}-{description.key}"

        _LOGGER.info(
            "new DreoSwitchHA instance(%s), unique ID %s",
            self._attr_name,
            self._attr_unique_id)

    @property
    def is_on(self) -> bool:
        """Return True if device is on."""
        _LOGGER.debug(
            "DreoSwitchHA:is_on for %s %s is %s",
            self.pydreo_device.name,
            self.entity_description.key,
            getattr(self.pydreo_device, self.entity_description.attr_name),
        )
        return getattr(self.pydreo_device, self.entity_description.attr_name)

    def turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn the device on."""
        _LOGGER.debug("Turning on %s %s", self.pydreo_device.name, self.entity_description.key)
        setattr(self.pydreo_device, self.entity_description.attr_name, True)

    def turn_off(self, **kwargs: Any) -> None:
        """Turn the device off."""
        _LOGGER.debug(
            "Turning off %s %s", self.pydreo_device.name, self.entity_description.key
        )
        setattr(self.pydreo_device, self.entity_description.attr_name, False)
