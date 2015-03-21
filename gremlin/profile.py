# -*- coding: utf-8; -*-

# Copyright (C) 2015 Lionel Ott
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import enum
from xml.etree import ElementTree
from xml.dom import minidom

import action
import gremlin
from gremlin.event_handler import InputType


def tag_to_input_type(tag):
    """Returns the input type enum corresponding to the given XML tag.

    :param tag xml tag for which to return the InputType enum
    :return InputType enum corresponding to the given XML tag
    """
    lookup = {
        "axis": InputType.JoystickAxis,
        "button": InputType.JoystickButton,
        "hat": InputType.JoystickHat,
        "key": InputType.Keyboard,
    }
    if tag.lower() in lookup:
        return lookup[tag.lower()]
    else:
        raise gremlin.error.ProfileError(
            "Invalid input type specified {}".format(tag)
        )


def _parse_bool(value):
    """Returns the boolean representation of the provided value.

    :param value the value as string to parse
    :return representation of value as either True or False
    """
    try:
        int_value = int(value)
        if int_value in [0, 1]:
            return int_value == 1
        else:
            raise gremlin.error.ProfileError(
                "Invalid bool value used: {}".format(value)
            )
    except ValueError:
        if value.lower() in ["true", "false"]:
            return True if value.lower() == "true" else False
        else:
            raise gremlin.error.ProfileError(
                "Invalid bool value used: {}".format(value)
            )
    except TypeError:
        raise gremlin.error.ProfileError(
            "Invalid type provided: {}".format(type(value))
        )


action_lookup = {
    # Input actions
    "macro": action.macro.Macro,
    "remap": action.remap.Remap,
    "response-curve": action.response_curve.ResponseCurve,
    # Control actions
    "cycle-modes": action.mode_control.CycleModes,
    "pause-action": action.pause_resume.PauseAction,
    "resume-action": action.pause_resume.ResumeAction,
    "switch-mode": action.mode_control.SwitchMode,
    "switch-to-previous-mode": action.mode_control.SwitchPreviousMode,
}


class DeviceType(enum.Enum):

    """Enumeration of the different possible input types."""

    Keyboard = 1
    Joystick = 2


class Profile(object):

    """Stores the contents of an entire configuration profile.

    This includes configurations for each device's modes.
    """

    def __init__(self):
        """Constructor creating a new instance."""
        self.devices = {}
        self.imports = []
        self.parent = None

    def from_xml(self, fname):
        """Parses the global XML document into the profile data structure.

        :param fname the path to the XML file to parse
        """
        tree = ElementTree.parse(fname)
        root = tree.getroot()

        # Parse each device into separate DeviceConfiguration objects
        for child in root.iter("device"):
            device = Device(self)
            device.from_xml(child)
            self.devices[device.index] = device

        # Ensure that the profile contains an entry for every existing
        # device even if it was not part of the loaded XML and
        # replicate the modes present in the profile.
        devices = gremlin.util.joystick_devices()
        for dev in devices:
            if not dev.is_virtual and dev.device_id not in self.devices:
                new_device = Device(self)
                new_device.name = dev.name
                new_device.hardware_id = dev.hardware_id
                new_device.windows_id = dev.windows_id
                new_device.type = DeviceType.Joystick
                self.devices[dev.device_id] = new_device

                # Create required modes
                mode_list = gremlin.util.mode_list(new_device)
                for mode in mode_list:
                    if mode not in new_device.modes:
                        new_device.modes[mode] = Mode(new_device)
                        new_device.modes[mode].name = mode

        # Parse list of user modules to import
        for child in root.iter("import"):
            for entry in child:
                self.imports.append(entry.get("name"))

    def to_xml(self, fname):
        """Generates XML code corresponding to this profile.

        :param fname name of the file to save the XML to
        """
        # Generate XML document
        root = ElementTree.Element("devices")
        root.set("version", "1")
        for device in self.devices.values():
            root.append(device.to_xml())
        import_node = ElementTree.Element("import")
        for entry in self.imports:
            node = ElementTree.Element("module")
            node.set("name", entry)
            import_node.append(node)
        root.append(import_node)

        # Serialize XML document
        ugly_xml = ElementTree.tostring(root, encoding="unicode")
        dom_xml = minidom.parseString(ugly_xml)
        with open(fname, "w") as out:
            out.write(dom_xml.toprettyxml(indent="    "))

    def get_device_modes(self, hardware_id, device_name=None):
        """Returns the modes associated with the given device.

        If no entry for the device exists a device entry with an empty
        "global" mode will be generated.

        :param hardware_id the id of the device
        :param device_name the name of the device
        :return all modes for the specified device
        """
        if hardware_id not in self.devices:
            device = Device(self)
            device.name = device_name
            device.hardware_id = hardware_id
            # Ensure we have a valid device type set
            device.type = DeviceType.Joystick
            if device_name == "keyboard":
                device.type = DeviceType.Keyboard
            self.devices[hardware_id] = device
        return self.devices[hardware_id]


class Device(object):

    """Stores the information about a single device including it's modes."""

    def __init__(self, parent):
        """Creates a new instance.

        :param parent the parent profile of this device
        """
        self.parent = parent
        self.name = None
        self.hardware_id = None
        self.windows_id = None
        self.modes = {}
        self.type = None

        # Ensure each device has at least an empty "global" mode
        self.modes["global"] = Mode(self)
        self.modes["global"].name = "global"

    def from_xml(self, node):
        """Populates this device based on the xml data.

        :param node the xml node to parse to populate this device
        """
        self.name = node.get("name")
        self.hardware_id = int(node.get("id"))
        self.windows_id = int(node.get("windows_id"))
        if self.name == "keyboard" and self.index == 0:
            self.type = DeviceType.Keyboard
        else:
            self.type = DeviceType.Joystick

        for child in node:
            mode = Mode(self)
            mode.from_xml(child)
            self.modes[mode.name] = mode

    def to_xml(self):
        """Returns a XML node representing this device's contents.

        :return xml node of this device's contents
        """
        node = ElementTree.Element("device")
        node.set("name", self.name)
        node.set("id", str(self.hardware_id))
        node.set("windows_id", str(self.windows_id))
        for mode in self.modes.values():
            node.append(mode.to_xml())
        return node


class Mode(object):

    """Represents the configuration of the mode of a single device."""

    def __init__(self, parent):
        """Creates a new DeviceConfiguration instance.

        :param parent the parent device of this mode
        """
        self.parent = parent
        self.name = None

        self._config = {
            InputType.JoystickAxis: {},
            InputType.JoystickButton: {},
            InputType.JoystickHat: {},
            InputType.Keyboard: {}
        }

    def from_xml(self, node):
        """Parses the XML mode data.

        :param node XML node to parse
        """
        self.name = node.get("name")
        for child in node:
            item = InputItem(self)
            item.from_xml(child)
            self._config[item.input_type][item.input_id] = item

    def to_xml(self):
        """Generates XML code for this DeviceConfiguration.

        :return XML node representing this object's data
        """
        node = ElementTree.Element("mode")
        node.set("name", self.name)
        for input_items in self._config.values():
            for item in input_items.values():
                node.append(item.to_xml())
        return node

    def delete_data(self, input_type, input_id):
        """Deletes the data associated with the provided
        input item entry.

        :param input_type the type of the input
        :param input_id the index of the input
        """
        assert(input_type in self._config)
        del self._config[input_type][input_id]

    def get_data(self, input_type, input_id):
        """Returns the configuration data associated with the provided
        InputItem entry.

        :param input_type the type of input
        :param input_id the id of the given input type
        :return InputItem corresponding to the provided combination of
            type and id
        """
        assert(input_type in self._config)
        if input_id not in self._config[input_type]:
            entry = InputItem(self)
            entry.input_type = input_type
            entry.input_id = input_id
            self._config[input_type][input_id] = entry
        return self._config[input_type][input_id]

    def set_data(self, input_type, input_id, data):
        """Sets the data of an InputItem.

        :param input_type the type of the InputItem
        :param input_id the id of the InputItem
        :param data the data of the InputItem
        """
        assert(input_type in self._config)
        self._config[input_type][input_id] = data


class InputItem(object):

    """Represents a single input item such as a button or axis."""

    def __init__(self, parent):
        """Creates a new InputItem instance.

        :param parent the parent mode of this input item
        """
        self.parent = parent
        self.input_type = None
        self.input_id = None
        self.always_execute = False
        self.actions = []

    def from_xml(self, node):
        """Parses an InputItem node.

        :param node XML node to parse
        """
        self.input_type = tag_to_input_type(node.tag)
        self.input_id = int(node.get("id"))
        self.always_execute = _parse_bool(node.get("always-execute", "False"))
        if self.input_type == InputType.Keyboard:
            self.input_id = (self.input_id, _parse_bool(node.get("extended")))
        for child in node:
            if child.tag not in action_lookup:
                print("Unknown node: ", child.tag)
                continue
            entry = action_lookup[child.tag](self)
            entry.from_xml(child)
            self.actions.append(entry)

    def to_xml(self):
        """Generates a XML node representing this object's data.

        :return XML node representing this object
        """
        node = ElementTree.Element(
            action.common.input_type_to_tag(self.input_type)
        )
        if self.input_type == InputType.Keyboard:
            node.set("id", str(self.input_id[0]))
            node.set("extended", str(self.input_id[1]))
        else:
            node.set("id", str(self.input_id))
        if self.always_execute:
            node.set("always-execute", "True")
        for entry in self.actions:
            node.append(entry.to_xml())
        return node