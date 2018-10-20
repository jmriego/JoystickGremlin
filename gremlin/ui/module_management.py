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

from PyQt5 import QtCore, QtGui, QtWidgets

from gremlin.common import VariableType
import gremlin.profile
import gremlin.custom_module
import gremlin.ui.common


class ModuleManagementController(QtCore.QObject):

    def __init__(self, profile_data, parent=None):
        super().__init__(parent)

        # This is essentially the model
        self.profile_data = profile_data

        # The view managed by the controller
        self.view = ModuleManagementView()

        self.view.add_module.connect(self.new_module)
        self.refresh_module_list()

    def module_list(self):
        return [module.file_name for module in self.profile_data.modules]

    def new_module(self, fname):
        if fname != "":
            # Only add a new entry if the module doesn't exist yet
            if fname not in [v.file_name for v in self.profile_data.modules]:
                # Update the model
                module = gremlin.profile.Module(self.profile_data)
                module.file_name = fname

                # Create new data instance
                instance = self._create_module_instance("Default", module)

                self.profile_data.modules.append(module)

                # Update the view
                self.view.module_list.add_module(
                    self._create_module_widget(self.profile_data.modules[-1])
                )

    def remove_module(self, file_name):
        # Remove the module from the model
        for i, module in enumerate(self.profile_data.modules):
            if module.file_name == file_name:
                del self.profile_data.modules[i]
                break

        # Remove corresponding UI element
        for module_widget in self.view.module_list.widget_list:
            if module_widget.get_module_name() == file_name:
                self.view.module_list.remove_module(module_widget)

    def create_new_module_instance(self, module_widget, module_data):
        # Create new data instance
        instance = self._create_module_instance("New Instance", module_data)

        # Create the UI side of things
        instance_widget = InstanceWidget(instance.name)
        self._connect_instance_signals(instance, instance_widget)
        module_widget.add_instance(instance_widget)

    def refresh_module_list(self):
        # Empty module list and then add one module at a time
        self.view.module_list.clear()
        for module in self.profile_data.modules:
            self.view.module_list.add_module(
                self._create_module_widget(module)
            )

    def remove_instance(self, instance, widget):
        # Remove model
        del instance.parent.instances[instance.parent.instances.index(instance)]
        # Remove view
        widget.parent().remove_instance(widget)

    def rename_instance(self, instance, widget, name):
        instance.name = name
        widget.label_name.setText(name)

    def configure_instance(self, instance, widget):
        # Get data from the custom module itself
        variables = gremlin.custom_module.get_variable_definitions(
            instance.parent.file_name
        )

        layout = self.view.right_panel.layout()
        gremlin.ui.common.clear_layout(layout)
        for var in variables:
            if type(var) in [
                gremlin.custom_module.FloatVariable,
                gremlin.custom_module.IntegerVariable,
                gremlin.custom_module.StringVariable,
                gremlin.custom_module.ModeVariable,
                gremlin.custom_module.VirtualInputVariable,
                gremlin.custom_module.PhysicalInputVariable
            ]:
                # Create profile variable instance if it does not exist
                if not instance.has_variable(var.label):
                    profile_var = gremlin.profile.Variable(instance)
                    profile_var.name = var.label
                    profile_var.type = var.variable_type
                    profile_var.value = var.default_value
                    instance.set_variable(var.label, profile_var)

                profile_var = instance.variables[var.label]
                ui_element = var.create_ui_element(profile_var.value)
                var.value_changed.connect(
                    self._create_value_changed_cb(
                        profile_var,
                        ui_element,
                        self._update_value_variable
                    )
                )
                layout.addLayout(ui_element)
            else:
                layout.addWidget(QtWidgets.QLabel(var.label))
        layout.addStretch()

    def _update_value_variable(self, variable, ui_element):
        if variable.type in [
            VariableType.Float,
            VariableType.Int,
            VariableType.String,
            VariableType.Mode
        ]:
            variable.value = ui_element.itemAtPosition(0, 1).widget().value()
        elif variable.type in [
            VariableType.PhysicalInput,
            VariableType.VirtualInput
        ]:
            variable.value = ui_element.itemAtPosition(0, 1).widget().get_selection()

    def _create_value_changed_cb(self, variable, ui_element, callback):
        return lambda: callback(variable, ui_element)

    def _create_module_widget(self, module_data):
        # Create the module widget
        module_widget = ModuleWidget(module_data.file_name)
        for instance in module_data.instances:
            instance_widget = InstanceWidget(instance.name)
            self._connect_instance_signals(instance, instance_widget)
            module_widget.add_instance(instance_widget)

        module_widget.btn_delete.clicked.connect(
            lambda x: self.remove_module(module_data.file_name)
        )
        module_widget.btn_add_instance.clicked.connect(
            lambda: self.create_new_module_instance(module_widget, module_data)
        )

        return module_widget

    def _connect_instance_signals(self, instance, widget):
        widget.renamed.connect(
            lambda x: self.rename_instance(instance, widget, x)
        )
        widget.btn_delete.clicked.connect(
            lambda x: self.remove_instance(instance, widget)
        )
        widget.btn_configure.clicked.connect(
            lambda x: self.configure_instance(instance, widget)
        )

    def _create_module_instance(self, name, module_data):
        # Create the model data side of things
        instance = gremlin.profile.Instance(module_data)
        instance.name = name

        # Properly populate the new instance with default values for all
        # variables
        variables = gremlin.custom_module.get_variable_definitions(
            instance.parent.file_name
        )
        for var in variables:
            if isinstance(var, gremlin.custom_module.NumericalVariable):
                ivar = instance.get_variable(var.label)
                ivar.name = var.label
                ivar.type = var.variable_type
                ivar.value = var.default_value

        module_data.instances.append(instance)

        return instance


class ModuleManagementView(QtWidgets.QSplitter):

    add_module = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.controller = None

        # Create the left panel showing the modules and their instances
        self.left_panel = QtWidgets.QWidget()
        self.left_panel.setLayout(QtWidgets.QVBoxLayout())

        # Displays the various modules and instances associated with them
        self.module_list = ModuleListWidget()

        # Button to add a new module
        self.btn_add_module = QtWidgets.QPushButton(
            QtGui.QIcon("gfx/list_add.svg"), "Add Module"
        )
        self.btn_add_module.clicked.connect(self._prompt_user_for_module)

        self.left_panel.layout().addWidget(self.module_list)
        self.left_panel.layout().addWidget(self.btn_add_module)

        # Create the right panel which will show the parameters of a
        # selected module instance
        self.right_panel = QtWidgets.QWidget()
        self.right_panel.setLayout(QtWidgets.QVBoxLayout())

        self.addWidget(self.left_panel)
        self.addWidget(self.right_panel)

    def refresh_ui(self):
        # TODO: stupid refresh code needs changing
        pass

    def _prompt_user_for_module(self):
        """Asks the user to select the path to the module to add."""

        fname, _ = QtWidgets.QFileDialog.getOpenFileName(
            None,
            "Path to Python module",
            "C:\\",
            "Python (*.py)"
        )
        self.add_module.emit(fname)


class ModuleListWidget(QtWidgets.QScrollArea):

    """Displays a list of loaded modules."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.widget_list = []
        self.setWidgetResizable(True)

        self.content = QtWidgets.QWidget()
        self.content.setLayout(QtWidgets.QVBoxLayout())
        self.content.layout().addStretch()
        self.setWidget(self.content)

    def add_module(self, module_widget):
        # Insert provided widget as the last one in the list above the
        # stretcher item
        self.widget_list.append(module_widget)
        self.content.layout().insertWidget(
            self.content.layout().count() - 1,
            module_widget
        )

    def remove_module(self, module_widget):
        module_widget.hide()
        self.content.layout().removeWidget(module_widget)
        del self.widget_list[self.widget_list.index(module_widget)]
        del module_widget

    def clear(self):
        self.widget_list = []
        gremlin.ui.common.clear_layout(self.content.layout())
        self.content.layout().addStretch()


class ModuleWidget(QtWidgets.QFrame):

    def __init__(self, module_name, parent=None):
        super().__init__(parent)

        layout = QtWidgets.QVBoxLayout(self)

        self.setStyleSheet("QFrame { background-color : '#ffffff'; }")
        self.setFrameShape(QtWidgets.QFrame.Box)

        header_layout = QtWidgets.QHBoxLayout()
        header_layout.addWidget(QtWidgets.QLabel(module_name))

        self.btn_add_instance = QtWidgets.QPushButton(
            QtGui.QIcon("gfx/button_add"),
            ""
        )
        self.btn_delete = QtWidgets.QPushButton(
            QtGui.QIcon("gfx/button_delete"),
            ""
        )

        header_layout.addStretch()
        header_layout.addWidget(self.btn_add_instance)
        header_layout.addWidget(self.btn_delete)

        self.instance_layout = QtWidgets.QVBoxLayout()

        layout.addLayout(header_layout)
        layout.addLayout(self.instance_layout)

    def get_module_name(self):
        header_layout = self.layout().takeAt(0)
        return header_layout.takeAt(0).widget().text()

        return self.layout().takeAt(0).takeAt(0).widget().text()

    def add_instance(self, widget):
        self.instance_layout.addWidget(widget)

    def remove_instance(self, widget):
        widget.hide()
        self.instance_layout.removeWidget(widget)
        del widget


class InstanceWidget(QtWidgets.QWidget):

    """Shows the controls for a particular module instance."""

    renamed = QtCore.pyqtSignal(str)

    def __init__(self, name, parent=None):
        super().__init__(parent)

        self.name = name
        self.main_layout = QtWidgets.QHBoxLayout(self)
        self.main_layout.setContentsMargins(20, 0, 0, 0)
        self._create_ui()

    def _create_ui(self):
        self.label_name = QtWidgets.QLabel(self.name)

        self.btn_rename = QtWidgets.QPushButton(
            QtGui.QIcon("gfx/button_edit"), ""
        )
        self.btn_rename.clicked.connect(self.rename_instance)
        self.btn_configure = QtWidgets.QPushButton(
            QtGui.QIcon("gfx/options"), ""
        )
        self.btn_delete = QtWidgets.QPushButton(
            QtGui.QIcon("gfx/button_delete"), ""
        )

        self.main_layout.addWidget(self.label_name)
        self.main_layout.addStretch()
        self.main_layout.addWidget(self.btn_rename)
        self.main_layout.addWidget(self.btn_configure)
        self.main_layout.addWidget(self.btn_delete)

    def rename_instance(self):
        name, user_input = QtWidgets.QInputDialog.getText(
                self,
                "Instance name",
                "New name for this instance",
                QtWidgets.QLineEdit.Normal,
                self.name
        )

        if user_input:
            self.renamed.emit(name)
