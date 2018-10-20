# -*- coding: utf-8; -*-

# Copyright (C) 2015 - 2018 Lionel Ott
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
import importlib
import inspect
import logging
import os
import random
import string

from PyQt5 import QtCore, QtGui, QtWidgets

from gremlin import common, profile, shared_state
import gremlin.ui.common


def get_variable_definitions(fname):
    """Returns all variable definitions contained in the provided module.

    :param fname module file to process
    :return collection of user configurable variables contained within the
        provided module
    """
    if not os.path.isfile(fname):
        return {}

    spec = importlib.util.spec_from_file_location(
        "".join(random.choices(string.ascii_lowercase, k=16)),
        fname
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    variables = {}
    for key, value in module.__dict__.items():
        if isinstance(value, AbstractVariable):
            if value.label in variables:
                logging.get_logger("system").error(
                    "Duplicate label present: {}".format(value.label)
                )
            variables[value.label] = value
    return variables.values()


def clamp_value(value, min_val, max_val):
    """Returns the value clamped to the provided range.

    :param value the input value
    :param min_val minimum value
    :param max_val maximum value
    :return the input value clamped to the provided range
    """
    if min_val > max_val:
        min_val, max_val = max_val, min_val
    return min(max_val, max(min_val, value))


class VariableRegistry:

    """Stores variables of custom module instances."""

    def __init__(self):
        self._registry = {}

    def clear(self):
        self._registry = {}

    def set(self, module, name, key, value):
        self._get_instance(module, name)[key] = value

    def get(self, module, name, key):
        return self._get_instance(module, name).get(key, None)

    def _get_instance(self, module, name):
        if module not in self._registry:
            self._registry[module] = {}
        if name not in self._registry[module]:
            self._registry[module][name] = {}

        return self._registry[module][name]


# Global registry for custom module variable values
variable_registry = VariableRegistry()




_cast_variable = {
    common.VariableType.Int: int,
    common.VariableType.Float: float,
    common.VariableType.String: str,
}


def _init_numerical(var, default_value, min_value, max_value):
    var.default_value = default_value if var.default_value is None else var.default_value
    var.min_value = min_value if var.min_value is None else var.min_value
    var.max_value = max_value if var.max_value is None else var.max_value


class AbstractVariable(QtCore.QObject):

    """Represents the base class of all variables in custom modules."""

    # Signal emitted when the value of the variable changes
    value_changed = QtCore.pyqtSignal()

    def __init__(self, label, description, variable_type):
        """Creates a new instance.

        :param label the user facing name given to the variable
        :param description description of the variable's function
        :param variable_type data type represented by the variable
        """
        super().__init__(None)
        self.label = label
        self.variable_type = variable_type
        self.description = description

    def create_ui_element(self):
        """Returns a UI element to configure this variable.

        :return UI element to configure this variable
        """
        pass


class NumericalVariable(AbstractVariable):

    """Base class for numerical variable types."""

    def __init__(
            self,
            label,
            description,
            variable_type,
            default_value=None,
            min_value=None,
            max_value=None
    ):
        super().__init__(label, description, variable_type)

        self.value = None
        self.default_value = default_value
        self.min_value = min_value
        self.max_value = max_value

        # Black magic to get the globals of the calling custom module, this
        # might be super brittle and might not handle include trees
        # FIXME: This most likely is brittle
        identifier = dict(
            inspect.getmembers(inspect.stack()[2].frame)
        )["f_globals"].get("identifier", None)

        self._initialize_variable()
        self._load_from_registry(identifier)

    def create_ui_element(self, value):
        layout = QtWidgets.QGridLayout()
        label = QtWidgets.QLabel(self.label)
        label.setToolTip(self.description)
        layout.addWidget(label, 0, 0)

        value_widget = None
        if self.variable_type == common.VariableType.Int:
            value_widget = QtWidgets.QSpinBox()
            value_widget.setRange(self.min_value, self.max_value)
            value_widget.setValue(clamp_value(
                int(value),
                self.min_value,
                self.max_value
            ))
            value_widget.valueChanged.connect(
                lambda x: self.value_changed.emit()
            )
        elif self.variable_type == common.VariableType.Float:
            value_widget = QtWidgets.QDoubleSpinBox()
            value_widget.setValue(float(value))
            value_widget.valueChanged.connect(lambda x: self.value_changed.emit())
        elif self.variable_type == common.VariableType.String:
            value_widget = QtWidgets.QLineEdit()
            value_widget.setText(str(value))
            value_widget.textChanged.connect(lambda x: self.value_changed.emit())
        elif self.variable_type == common.VariableType.Bool:
            value_widget = QtWidgets.QCheckBox()
            # value_widget.setChecked(value == True)

        if value_widget is not None:
            layout.addWidget(value_widget, 0, 1)
            layout.setColumnStretch(1, 1)

        layout.setColumnMinimumWidth(0, 150)

        return layout

    def _initialize_variable(self):
        logging.get_logger("system").error(
            "NumericalVariable instance being used"
        )

    def _load_from_registry(self, identifier):
        if identifier is not None:
            val = variable_registry.get(identifier[0], identifier[1], self.label)
            if val is None:
                self.value = self.default_value
            else:
                self.value = _cast_variable[self.variable_type](val)
            # print("VV: {}".format(self.value), type(self.value))
        else:
            self.value = self.default_value
            # print("VV: not set")

        self.value = clamp_value(
            self.value,
            self.min_value,
            self.max_value
        )

        print(self.value, identifier)


class IntegerVariable(NumericalVariable):

    """Variable representing an integer value."""

    def __init__(
            self,
            label,
            description,
            default_value=None,
            min_value=None,
            max_value=None
    ):
        super().__init__(
            label,
            description,
            common.VariableType.Int,
            default_value,
            min_value,
            max_value
        )

    def _initialize_variable(self):
        _init_numerical(self, 0, 0, 10)


class FloatVariable(NumericalVariable):

    """Variable representing an float value."""

    def __init__(
            self,
            label,
            description,
            default_value=None,
            min_value=None,
            max_value=None
    ):
        super().__init__(
            label,
            description,
            common.VariableType.Float,
            default_value,
            min_value,
            max_value
        )

    def _initialize_variable(self):
        _init_numerical(self, 0, -1.0, 1.0)


class StringVariable(AbstractVariable):

    def __init__(
            self,
            label,
            description,
            default_value=None,
    ):
        super().__init__(label, description, common.VariableType.String)

        self.value = None
        self.default_value = default_value

        # Black magic to get the globals of the calling custom module, this
        # might be super brittle and might not handle include trees
        # FIXME: This most likely is brittle
        identifier = dict(
            inspect.getmembers(inspect.stack()[2].frame)
        )["f_globals"].get("identifier", None)

        self._load_from_registry(identifier)

    def create_ui_element(self, value):
        layout = QtWidgets.QGridLayout()
        label = QtWidgets.QLabel(self.label)
        label.setToolTip(self.description)
        layout.addWidget(label, 0, 0)

        value_widget = QtWidgets.QLineEdit()
        value_widget.setText(str(value))
        value_widget.textChanged.connect(lambda x: self.value_changed.emit())

        if value_widget is not None:
            layout.addWidget(value_widget, 0, 1)
            layout.setColumnStretch(1, 1)

        layout.setColumnMinimumWidth(0, 150)

        return layout

    def _load_from_registry(self, identifier):
        if identifier is not None:
            self.value = _cast_variable[self.variable_type](
                variable_registry.get(
                    identifier[0],
                    identifier[1],
                    self.label
            ))
        else:
            self.value = self.default_value


class ModeVariable(AbstractVariable):

    def __init__(
            self,
            label,
            description
    ):
        super().__init__(label, description, common.VariableType.Mode)

        self.default_value = profile.mode_list(shared_state.current_profile)[0]
        self.value = None

        # Black magic to get the globals of the calling custom module, this
        # might be super brittle and might not handle include trees
        # FIXME: This most likely is brittle
        identifier = dict(
            inspect.getmembers(inspect.stack()[2].frame)
        )["f_globals"].get("identifier", None)

        self._load_from_registry(identifier)

    def create_ui_element(self, value):
        layout = QtWidgets.QGridLayout()
        label = QtWidgets.QLabel(self.label)
        label.setToolTip(self.description)
        layout.addWidget(label, 0, 0)

        value_widget = gremlin.ui.common.ModeWidget()
        value_widget.populate_selector(shared_state.current_profile, value)
        # value_widget.textChanged.connect(lambda x: self.value_changed.emit())

        layout.addWidget(value_widget, 0, 1)
        layout.setColumnStretch(1, 1)

        layout.setColumnMinimumWidth(0, 150)

        return layout

    def _load_from_registry(self, identifier):
        if identifier is not None:
            self.value = _cast_variable[self.variable_type](
                variable_registry.get(
                    identifier[0],
                    identifier[1],
                    self.label
            ))
        else:
            self.value = self.default_value


class VirtualInputVariable(AbstractVariable):

    def __init__(self, label, description):
        super().__init__(label, description, common.VariableType.VirtualInput)

        self.value = None
        self.default_value = None

    def create_ui_element(self, value):
        layout = QtWidgets.QGridLayout()
        label = QtWidgets.QLabel(self.label)
        label.setToolTip(self.description)
        layout.addWidget(label, 0, 0)

        value_widget = gremlin.ui.common.VJoySelector(
            lambda: self.value_changed.emit(),
            [
                common.InputType.JoystickAxis,
                common.InputType.JoystickButton,
                common.InputType.JoystickHat
            ]
        )
        value_widget.set_selection(
            value["input_type"],
            value["device_id"],
            value["input_id"]
        )
        #value_widget.populate_selector(shared_state.current_profile, value)
        #value_widget.textChanged.connect(lambda x: self.value_changed.emit())

        layout.addWidget(value_widget, 0, 1)
        layout.setColumnStretch(1, 1)

        layout.setColumnMinimumWidth(0, 150)

        return layout


class PhysicalInputVariable(AbstractVariable):

    def __init__(self, label, description, valid_types=[]):
        super().__init__(label, description, common.VariableType.PhysicalInput)

        self.value = None
        self.default_value = None

        # Black magic to get the globals of the calling custom module, this
        # might be super brittle and might not handle include trees
        # FIXME: This most likely is brittle
        identifier = dict(
            inspect.getmembers(inspect.stack()[1].frame)
        )["f_globals"].get("identifier", None)

        self._load_from_registry(identifier)

    @property
    def input_id(self):
        if isinstance(self.value, dict):
            return self.value.get("input_id", 0)
        else:
            return 0

    @property
    def windows_id(self):
        if isinstance(self.value, dict):
            return self.value.get("windows_id", 0)
        else:
            return 0

    @property
    def hardware_id(self):
        if isinstance(self.value, dict):
            return self.value.get("hardware_id", 0)
        else:
            return 0

    def create_ui_element(self, value):
        layout = QtWidgets.QGridLayout()
        label = QtWidgets.QLabel(self.label)
        label.setToolTip(self.description)
        layout.addWidget(label, 0, 0)

        value_widget = gremlin.ui.common.JoystickSelector(
            lambda: self.value_changed.emit(),
            [
                common.InputType.JoystickAxis,
                common.InputType.JoystickButton,
                common.InputType.JoystickHat
            ]
        )
        value_widget.set_selection(
            value["input_type"],
            gremlin.util.get_device_id(
                value["hardware_id"],
                value["windows_id"]
            ),
            value["input_id"]
        )

        layout.addWidget(value_widget, 0, 1)
        layout.setColumnStretch(1, 1)

        layout.setColumnMinimumWidth(0, 150)

        return layout

    def _load_from_registry(self, identifier):
        if identifier is not None:
            self.value = variable_registry.get(
                    identifier[0],
                    identifier[1],
                    self.label
            )
        else:
            self.value = self.default_value

        print(self.value, identifier)