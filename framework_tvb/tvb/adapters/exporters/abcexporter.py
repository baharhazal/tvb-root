# -*- coding: utf-8 -*-
#
#
# TheVirtualBrain-Framework Package. This package holds all Data Management, and 
# Web-UI helpful to run brain-simulations. To use it, you also need do download
# TheVirtualBrain-Scientific Package (for simulators). See content of the
# documentation-folder for more details. See also http://www.thevirtualbrain.org
#
# (c) 2012-2020, Baycrest Centre for Geriatric Care ("Baycrest") and others
#
# This program is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software Foundation,
# either version 3 of the License, or (at your option) any later version.
# This program is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
# PARTICULAR PURPOSE.  See the GNU General Public License for more details.
# You should have received a copy of the GNU General Public License along with this
# program.  If not, see <http://www.gnu.org/licenses/>.
#
#
#   CITATION:
# When using The Virtual Brain for scientific publications, please cite it as follows:
#
#   Paula Sanz Leon, Stuart A. Knock, M. Marmaduke Woodman, Lia Domide,
#   Jochen Mersmann, Anthony R. McIntosh, Viktor Jirsa (2013)
#       The Virtual Brain: a simulator of primate brain network dynamics.
#   Frontiers in Neuroinformatics (7:10. doi: 10.3389/fninf.2013.00010)
#
#

"""
Root class for export functionality.

.. moduleauthor:: Lia Domide <lia.domide@codemart.ro>
"""
import os
from datetime import datetime
from abc import ABCMeta, abstractmethod
from distutils.dir_util import copy_tree

from tvb.adapters.exporters.exceptions import ExportException
from tvb.core.entities.file.files_helper import FilesHelper
from tvb.core.entities.load import load_entity_by_gid
from tvb.core.entities.model.model_datatype import DataTypeGroup
from tvb.core.entities.storage import dao
from tvb.core.neocom import h5
from tvb.core.neotraits._h5core import H5File
from tvb.core.services.project_service import ProjectService

# List of DataTypes to be excluded from export due to not having a valid export mechanism implemented yet.
EXCLUDED_DATATYPES = ['Cortex', 'CortexActivity', 'CapEEGActivity', 'Cap', 'ValueWrapper', 'SpatioTermporalMask']


class ABCExporter(metaclass=ABCMeta):
    """
    Base class for all data type exporters
    This should provide common functionality for all TVB exporters.
    """
    OPERATION_FOLDER_PREFIX = "Operation_"
    LINKS = "Links"

    @abstractmethod
    def get_supported_types(self):
        """
        This method specify what types are accepted by this exporter.
        Method should be implemented by each subclass and return
        an array with the supported types.

        :returns: an array with the supported data types.
        """
        pass

    def get_label(self):
        """
        This method returns a string to be used on the UI controls to initiate export

        :returns: string to be used on UI for starting this export.
                  By default class name is returned
        """
        return self.__class__.__name__

    def accepts(self, data):
        """
        This method specify if the current exporter can export provided data.
        :param data: data to be checked
        :returns: true if this data can be exported by current exporter, false otherwise.
        """
        effective_data_type = self._get_effective_data_type(data)

        # If no data present for export, makes no sense to show exporters
        if effective_data_type is None:
            return False

        # Now we should check if any data type is accepted by current exporter
        # Check if the data type is one of the global exclusions
        if hasattr(effective_data_type, "type") and effective_data_type.type in EXCLUDED_DATATYPES:
            return False

        for supported_type in self.get_supported_types():
            if isinstance(effective_data_type, supported_type):
                return True

        return False

    def _get_effective_data_type(self, data):
        """
        This method returns the data type for the provided data.
        - If current data is a simple data type is returned.
        - If it is an data type group, we return the first element. Only one element is
        necessary since all group elements are the same type.
        """
        # first check if current data is a DataTypeGroup
        if self.is_data_a_group(data):
            if self.skip_group_datatypes():
                return None

            data_types = ProjectService.get_datatypes_from_datatype_group(data.id)

            if data_types is not None and len(data_types) > 0:
                # Since all objects in a group are the same type it's enough
                return load_entity_by_gid(data_types[0].gid)
            else:
                return None
        else:
            return data

    def skip_group_datatypes(self):
        return False

    def _get_all_data_types_arr(self, data):
        """
        This method builds an array with all data types to be processed later.
        - If current data is a simple data type is added to an array.
        - If it is an data type group all its children are loaded and added to array.
        """
        # first check if current data is a DataTypeGroup
        if self.is_data_a_group(data):
            data_types = ProjectService.get_datatypes_from_datatype_group(data.id)

            result = []
            if data_types is not None and len(data_types) > 0:
                for data_type in data_types:
                    entity = load_entity_by_gid(data_type.gid)
                    result.append(entity)

            return result

        else:
            return [data]

    def is_data_a_group(self, data):
        """
        Checks if the provided data, ready for export is a DataTypeGroup or not
        """
        return isinstance(data, DataTypeGroup)

    def group_export(self, data, export_folder, project, download_file_name, is_linked_export=False):
        all_datatypes = self._get_all_data_types_arr(data)

        if all_datatypes is None or len(all_datatypes) == 0:
            raise ExportException("Could not export a data type group with no data")

        # Now process each data type from group and add it to ZIP file
        operation_folders = []
        sub_dt_refs = None
        references_folder_path = None
        temp_export_folders = []

        for data_type in all_datatypes:
            if is_linked_export and not sub_dt_refs:
                references_folder_path = self.copy_ref_files_to_temp_dir(data_type, export_folder, temp_export_folders, references_folder_path)

            operation_folder = FilesHelper().get_operation_folder(project.name, data_type.fk_from_operation)
            operation_folders.append(operation_folder)

        for operation_folder in operation_folders:
            tmp_op_folder_path = os.path.join(export_folder, os.path.basename(operation_folder))
            copy_tree(operation_folder, tmp_op_folder_path, preserve_mode=None)
            temp_export_folders.append(tmp_op_folder_path)

        if is_linked_export:
            operation_folders = temp_export_folders

        # Create ZIP archive
        zip_file = os.path.join(export_folder, download_file_name)
        FilesHelper().zip_folders(zip_file, operation_folders, self.OPERATION_FOLDER_PREFIX)

        return download_file_name, zip_file, True

    def copy_ref_files_to_temp_dir(self, data_type, export_folder, temp_export_folders, references_folder_path):
        data_path = h5.path_for_stored_index(data_type)
        with H5File.from_file(data_path) as f:
            sub_dt_refs = f.gather_references()

            for reference in sub_dt_refs:
                if reference[1]:
                    dt = dao.get_datatype_by_gid(reference[1].hex)
                    ref_data_path = h5.path_for_stored_index(dt)

                    # Create folder for references if it's not created already
                    if not references_folder_path:
                        references_folder_path = os.path.join(export_folder, self.LINKS)
                        if not os.path.exists(references_folder_path):
                            os.makedirs(references_folder_path)
                            temp_export_folders.append(references_folder_path)

                    ref_file_path = os.path.join(references_folder_path, os.path.basename(ref_data_path))
                    if not os.path.exists(ref_file_path):
                        FilesHelper().copy_file(ref_data_path, ref_file_path)
                    self.copy_ref_files_to_temp_dir(dt, export_folder, temp_export_folders, references_folder_path)
        return references_folder_path

    @abstractmethod
    def export(self, data, export_folder, project):
        """
        Actual export method, to be implemented in each sub-class.

        :param data: data type to be exported

        :param export_folder: folder where to write results of the export if needed.
                              This is necessary in case new files are generated.

        :param project: project that contains data to be exported

        :returns: a tuple with the following elements:

                        1. name of the file to be shown to user
                        2. full path of the export file (available for download)
                        3. boolean which specify if file can be deleted after download
        """
        pass

    def get_export_file_name(self, data):
        """
        This method computes the name used to save exported data on user computer
        """
        file_ext = self.get_export_file_extension(data)
        data_type_name = data.__class__.__name__
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d_%H-%M")

        return "%s_%s.%s" % (date_str, data_type_name, file_ext)

    @abstractmethod
    def get_export_file_extension(self, data):
        """
        This method computes the extension of the export file
        :param data: data type to be exported
        :returns: the extension of the file to be exported (e.g zip or h5)
        """
        pass
