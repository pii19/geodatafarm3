__author__ = 'Axel Horteborn'
from qgis.core import QgsTask
from PyQt5 import QtCore
import traceback
from PyQt5.QtWidgets import (QTableWidgetItem, QFileDialog, QAbstractItemView,
                             QMessageBox)
from osgeo import osr
import os
from operator import xor
# Import the code for the dialog
from ..widgets.import_shp_dialog import ImportShpDialog
from ..support_scripts.create_layer import CreateLayer
from ..support_scripts.__init__ import check_text, check_date_format
from ..support_scripts import shapefile as shp
from ..import_data.insert_manual_from_file import ManualFromFile
q_info = QMessageBox.information


class InputShpHandler:
    def __init__(self, parent_widget, schema, spec_columns):
        """A widget that enables the possibility to insert data from a text
        file into a shapefile"""
        self.col_types = None
        self.param_row_count = 0
        self.params_to_evaluate = []
        self.combo = []
        self.col_types = []
        self.col_names = []
        self.sample_data = []
        # Create the dialog (after translation) and keep reference
        self.ISD = ImportShpDialog()
        self.db = parent_widget.db
        self.tr = parent_widget.tr
        self.tsk_mngr = parent_widget.tsk_mngr
        self.dock_widget = parent_widget.dock_widget
        self.populate = parent_widget.populate
        self.mff = ManualFromFile(parent_widget.db, parent_widget.tr, self.ISD,
                                  spec_columns)
        self.CreateLayer = CreateLayer(self.db)
        self._q_replace_db_data = parent_widget._q_replace_db_data
        self.schema = schema
        self.fields_to_db = False
        self.isPolygon = False
        self.input_file_path = ''
        self.file_name_with_path = ''
        self.file_name = ''
        self.field = ''
        self.column_count = 0

    def run(self):
        """Presents the sub widget HandleInput and connects the different
        buttons to their function"""
        self.ISD.show()
        self.ISD.add_input_file.clicked.connect(self.open_input_file)
        self.ISD.pButAdd_Param.clicked.connect(self.add_to_param_list)
        self.ISD.pButRem_Param.clicked.connect(self.remove_from_param_list)
        self.ISD.pButContinue.clicked.connect(self.prepare_data_to_be_inserted)
        self.ISD.pButInsertDataIntoDB.clicked.connect(self.prepare_shp_file)
        self.populate.reload_fields(self.ISD.CBField)
        self.populate.reload_crops(self.ISD.CBCrops)
        self.ISD.exec_()

    def open_input_file(self):
        """Open the file dialog and let the user choose which file that should
        be inserted. In the end of this function the function define_separator,
        set_sep_radio_but and set_column_list are being called."""
        filters = "Text files (*.shp)"
        self.file_name_with_path = QFileDialog.getOpenFileName(None,
                                                               " File dialog ",
                                                               '', filters)[0]
        path = self.file_name_with_path
        if self.file_name_with_path == '':
            return
        temp_var = self.file_name_with_path.split("/")
        self.tbl_name = temp_var[len(temp_var)-1][0:-4]
        self.input_file_path = path[0:path.index(self.tbl_name)]
        self.get_columns_names()

    def get_columns_names(self):
        """A function that retrieves the name of the columns from the .csv file
        and returns a list with name"""
        self.ISD.TWColumnNames.clear()
        shp_file = shp.Reader(self.file_name_with_path)
        try:
            if len(shp_file.shapes()[0].points) > 1:
                self.isPolygon = True
            else:
                self.isPolygon = False
        except Exception as e:
            q_info(None, self.tr("Error:"),
                   self.tr('No shapes was found in the file\n') + str(e))
            return
        _types = []
        for name, type_, length, precision in shp_file.fields:
            if name == 'DeletionFlag':
                continue
            self.col_names.append(name)
            _types.append(type_)
            if type_ == 'N':
                self.col_types.append(0)
            if type_ == 'F':
                self.col_types.append(1)
            if type_ == 'C':
                self.col_types.append(2)
        temp_list = shp_file.iterRecords()
        self.sample_data = []
        sec_row = True
        c_i = 0
        for row in temp_list:
            if sec_row:
                second_row = row
                sec_row = False
            if c_i < 1000:
                c_i += 1
                self.sample_data.append(row)
            else:
                break
        self.ISD.TWColumnNames.setRowCount(len(self.col_names))
        self.ISD.TWColumnNames.setColumnCount(2)
        self.ISD.TWColumnNames.setSelectionBehavior(
            QAbstractItemView.SelectRows)
        for i, row in enumerate(self.col_names):
            item1 = QTableWidgetItem(row)
            item1.setFlags(xor(item1.flags(), QtCore.Qt.ItemIsEditable))
            item2 = QTableWidgetItem(str(second_row[i]))
            item2.setFlags(xor(item2.flags(), QtCore.Qt.ItemIsEditable))
            self.ISD.TWColumnNames.setItem(i, 0, item1)
            self.ISD.TWColumnNames.setItem(i, 1, item2)
        self.column_count = i
        shp_file.close()

    def add_to_param_list(self):
        """Adds the selected columns to the list of fields that should be
        treated as "special" in the database both to work as a parameter that
        could be evaluated and as a layer that is added to the canvas"""
        row_count = self.param_row_count
        self.ISD.TWtoParam.setColumnCount(1)
        items_to_add = []
        existing_values = []
        if row_count != 0:
            for i in range(row_count):
                existing_values.append(self.ISD.TWtoParam.item(i, 0).text())
        for item in self.ISD.TWColumnNames.selectedItems():
            if item.column() == 0 and item.text() not in existing_values:
                items_to_add.append(item.text())
        for i, item in enumerate(items_to_add, self.param_row_count):
            row_count += 1
            self.ISD.TWtoParam.setRowCount(row_count)
            item1 = QTableWidgetItem(item)
            item1.setFlags(xor(item1.flags(), QtCore.Qt.ItemIsEditable))
            self.ISD.TWtoParam.setItem(i, 0, item1)
        self.param_row_count = row_count
        self.ISD.pButContinue.setEnabled(True)

    def remove_from_param_list(self):
        """Removes the selected columns from the list of fields that should be
        treated as "special" in the database"""
        row_count = self.param_row_count
        if self.ISD.TWtoParam.selectedItems() is None:
            q_info(None, self.tr("Error:"), self.tr('No row selected!'))
            return
        for item in self.ISD.TWtoParam.selectedItems():
            self.ISD.TWtoParam.removeRow(item.row())
            row_count -= 1
        self.param_row_count = row_count

    def _find_prj(self):
        """A little function that checks if a prj is in the same folder as the 
        input shp
        :return bool"""
        files_in_path = os.listdir(self.input_file_path)
        if self.tbl_name[:-4] + '.prj' in files_in_path:
            return True
        else:
            return False

    def prepare_data_to_be_inserted(self):
        """A function that prepares the last parts of the widget with the data
        to be inserted into the shapefile, determining date and time columns """
        columns_to_add = []
        self.field = self.ISD.CBField.currentText()
        if self.field == self.tr('--- Select field ---'):
            QMessageBox.information(None, self.tr('Error:'),
                                    self.tr('In order to save the data you must select a field'))
            return
        for i in range(self.column_count + 1):
            columns_to_add.append(self.ISD.TWColumnNames.item(i, 0).text())
        shp_file = shp.Reader(self.file_name_with_path)
        no_prj = self._find_prj()
        if (self.ISD.EPSG.text() == '4326' and not
                -180 < shp_file.shapeRecord(0).shape.points[0][0] < 180):
            q_info(None, self.tr("Error:"),
                   self.tr('The projection is probably wrong, please change from 4326'))
            return
        self.ISD.pButInsertDataIntoDB.setEnabled(True)
        self.ISD.ComBDate.setEnabled(True)
        self.ISD.ComBDate.addItems(columns_to_add)
        self.mff.prepare_data(columns_to_add)

    def prepare_shp_file(self):
        """
        Preparing the data before adding it to a QgsTask. and ensure that the
        coordinates is in EPSG:4326
        :return:
        """
        columns_to_add = {}
        for i in range(self.column_count + 1):
            text = self.ISD.TWColumnNames.item(i,0).text()
            only_char = check_text(text)
            columns_to_add[only_char] = []
        for i in range(self.param_row_count):
            self.params_to_evaluate.append(self.ISD.TWtoParam.item(i,0).text())
        if not self._find_prj():
            srs = osr.SpatialReference()
            srs.ImportFromEPSG(int(self.ISD.EPSG.text()))
            esri_output = srs.ExportToWkt()
            with open(str(self.file_name_with_path)[:-4] + '.prj', 'w') as f:
                f.write(esri_output)
        if self.db.check_table_exists(self.tbl_name, self.schema):
            return
        date_dict = {}
        if self.ISD.RBDateOnly.isChecked():
            is_ok, first_date = check_date_format(self.sample_data, check_text(self.ISD.ComBDate.currentText()),
                                                  self.ISD.ComBDate_2.currentText())
            if not is_ok:
                QMessageBox.information(None, self.tr('Error'),
                                        self.tr("The date format didn't match the selected format, please change"))
                return
            manual_date = 'date_'
            date_dict['date_row'] = check_text(self.ISD.ComBDate.currentText())
            date_dict['date_format'] = self.ISD.ComBDate_2.currentText()
            table_date = first_date

        else:
            date_dict['simple_date'] = self.ISD.DE.text()
            manual_date = 'c_' + self.ISD.DE.text()
            table_date = self.ISD.DE.text()
        self.tbl_name = check_text(self.tbl_name + '_' + table_date)
        self.mff.insert_manual_data(manual_date, self.ISD.CBField.currentText(),
                                    self.tbl_name, self.schema)
        task = QgsTask.fromFunction('Run import text data', self.import_data,
                                    date_dict, on_finished=self.show_data)
        # self.tsk_mngr.addTask(task)

        # Debug
        res = self.import_data('debug', date_dict)
        self.show_data('a', res)

    def create_tbl(self, date_dict):
        """Creates a "temp" table in the database

        Returns
        -------
        If works:
            [True]
        else:
            return [False, e, traceback.format_exc()]
        """
        try:
            sql = "CREATE TABLE {schema}.temp_table (field_row_id integer PRIMARY KEY, ".format(
                schema=self.schema)
            lat_lon_inserted = False
            date_inserted = False
            for i, col_name in enumerate(self.col_names):
                if not lat_lon_inserted:
                    sql += """pos geometry(POINT, 4326), 
                    polygon geometry(POLYGON, 4326), 
                    """
                    lat_lon_inserted = True
                if 'date_row' in date_dict.keys() and col_name == date_dict['date_row']:
                    sql += "Date_ TIMESTAMP, "
                    continue
                elif 'simple_date' in date_dict.keys() and not date_inserted:
                    sql += "Date_ TIMESTAMP, "
                    date_inserted = True
                if self.col_types[i] == 0:
                    sql += str(col_name) + " INT, "
                if self.col_types[i] == 1:
                    sql += str(col_name) + " REAL, "
                if self.col_types[i] == 2:
                    sql += str(col_name) + " TEXT, "
            sql = sql[:-2]
            sql += ")"
            self.db.create_table(sql, '{schema}.temp_table'.format(schema=self.schema))
            return [True]
        except Exception as e:
            return [False, e, traceback.format_exc()]

    def get_shp_data(self):
        """Read data from the shp file

        Returns
        -------
        if works:
            [True, shapes, fields, data_as_points]
        else:
            [False, e, traceback.format_exc()]
        """
        try:
            with shp.Reader(self.file_name_with_path) as shp_file:
                # records = shpfile.records()
                shapes = shp_file.shapeRecords()
                fields = shp_file.fields
                if shapes[0].shape.shapeType == 1:
                    data_as_points = True
                elif shapes[0].shape.shapeType == 5:
                    data_as_points = False
                else:
                    return [False, self.tr('Unkown geometry type of the shape file type'), '']
            return [True, shapes, fields, data_as_points]
        except Exception as e:
            return [False, e, traceback.format_exc()]

    def get_dict_from_shp_data(self, fields, shapes):
        """Creates the dict data_dict and a list field names from the fields,
        shapes.

        Parameters
        ----------
        fields: list
        shapes: list

        Returns
        -------
        if True
            [True, data_dict, field_names]
        else:
            [False, e, traceback.format_exc()]
        """
        try:
            data_dict = {"pos": [], 'field_row_id': []}
            field_names = []
            for name, type, int1, int2 in fields:
                if name == 'DeletionFlag':
                    continue
                field_names.append(name)
                data_dict[name] = []
            for k, row in enumerate(shapes):
                for i, col in enumerate(row.record):
                    if col == b'                    ':
                        col = "' '"
                    elif isinstance(col, str):
                        col = "'" + col + "'"
                    data_dict[field_names[i]].append(col)
                if self.ISD.EPSG.text() == '4326':
                    data_dict['pos'].append(
                        "ST_PointFromText('POINT({p1} {p2})',4326 )".format(
                            p1=shapes[k].shape.points[0][0],
                            p2=shapes[k].shape.points[0][1]))
                else:
                    data_dict['pos'].append(
                        "ST_transform(ST_PointFromText('POINT({p1} {p2})',{epsg}),4326 )".format(
                        p1=shapes[k].shape.points[0][0],
                        p2=shapes[k].shape.points[0][1],
                        epsg=self.ISD.EPSG.text()))
                data_dict['field_row_id'].append(k)
            return [True, data_dict, field_names]
        except Exception as e:
            return [False, e, traceback.format_exc()]

    def import_data(self, task, date_dict):
        failure = False
        res = self.create_tbl(date_dict)
        if res[0] is False:
            failure = True
        if task != 'debug' and not failure:
            task.setProgress(5)
        res = self.get_shp_data()
        if res[0] is False:
            failure = True
        elif res[1] and not failure:
            shapes = res[1]
            fields = res[2]
            data_as_points = res[3]
        if task != 'debug':
            task.setProgress(25)
        if not failure:
            res = self.get_dict_from_shp_data(fields, shapes)
        if res[0] is False:
            failure = True
        elif res[1] and not failure:
            data_dict = res[1]
            field_names = res[2]
        if not failure:
            cols = []
            for key in self.col_names:
                cols.append(key.encode('ascii').decode('utf-8'))
            for j, name in enumerate(field_names):
                found = False
                for col in cols:
                    if col[:10] == name:
                        data_dict[col] = data_dict.pop(name)
                        found = True
                if not found:
                    del data_dict[name]
            key_list = list(data_dict.keys())
            sql_raw = "INSERT INTO {schema}.temp_table ({cols}) VALUES".format(
                schema=self.schema,
                cols=", ".join(str(e).replace("'", "") for e in key_list))
            for i in range(len(data_dict['field_row_id'])):
                value = [data_dict[key][i] for key in key_list]
                sql_raw += "({vals_str}), ".format(
                    vals_str=", ".join(str(e) for e in value))
            sql = sql_raw[:-2]
            self.db.execute_sql(sql)
            if self.ISD.EPSG.text() != '4326':
                sql = """Update {schema}.temp_table set pos=st_transform(pos,
                4326)""".format(schema=self.schema)
                self.db.execute_sql(sql)
            if task != 'debug':
                task.setProgress(50)
            sql = """SELECT * INTO {schema}.{tbl} 
    from {schema}.temp_table
    where st_intersects(pos, (select polygon 
                              from fields 
                              where field_name='{field}')
                        )""".format(
                    schema=self.schema, tbl=self.tbl_name, field=self.field)
            self.db.execute_sql(sql)
            if task != 'debug':
                task.setProgress(70)
            if self.schema != 'harvest' and data_as_points:
                # self.db.execute_sql(
                #    "DROP TABLE {schema}.temp_table".format(schema=self.schema))

                sql = """drop table if exists {schema}.temp_tbl2;
            WITH voronoi_temp2 AS (
              SELECT ST_dump(ST_VoronoiPolygons(ST_Collect(pos))) as vor
              FROM {schema}.{tbl})
            SELECT (vor).path, (vor).geom 
              into {schema}.temp_tbl2
              FROM voronoi_temp2  ;
            create index temp_index on {schema}.temp_tbl2 Using gist(geom);
            update {schema}.{tbl}
              SET polygon = ST_Intersection(geom,(select polygon 
                            from fields where field_name='{field}'))
              FROM {schema}.temp_tbl2
              WHERE st_intersects(pos, geom)""".format(schema=self.schema,
                                                       tbl=self.tbl_name,
                                                       field=self.field)
                self.db.execute_sql(sql)
            if task != 'debug':
                task.setProgress(90)
            redone_param_list = []
            for param in self.params_to_evaluate:
                only_char = check_text(param)
                redone_param_list.append(only_char)
            self.db.execute_sql("drop table if exists {schema}.temp_tbl2;".format(
                    schema=self.schema))
            self.db.create_indexes(self.tbl_name, redone_param_list, self.schema)
            return [True]
        if failure:
            return res

    def show_data(self, result, values):
        """Checks that all data is uploaded to the postgres database and adds
        the data to the canvas and closes the widget

        Parameters
        ----------
        result: object
            The result object
        values: list
            list with [bool, bool, int]
        """
        if values[0] is False:
            QMessageBox.information(None, self.tr('Error'),
                                    self.tr('Following error occurred: {m}\n\n Traceback: {t}'.format(m=values[1],
                                                                                                      t=values[2])))
            return
        tbl = self.tbl_name
        length = self.db.execute_and_return(
            "select field_row_id from {s}.{t} limit 2".format(s=self.schema, t=tbl))
        if len(length) == 0:
            QMessageBox.information(None, self.tr('Error'),
                                    self.tr('No data were found in the field, '
                                            'are you sure that the data is in the correct field?'))
            return
        create_layer = CreateLayer(self.db)
        for param_layer in self.params_to_evaluate:
            param_layer = check_text(param_layer)
            target_field = param_layer
            if self.schema == 'harvest':
                layer = self.db.add_postgis_layer(tbl, 'pos', '{schema}'.format(
                    schema=self.schema),
                                                  check_text(
                                                      param_layer.lower()))
            else:
                layer = self.db.add_postgis_layer(tbl, 'polygon',
                                                  '{schema}'.format(
                                                      schema=self.schema),
                                                  check_text(
                                                      param_layer.lower()))

            create_layer.create_layer_style(layer, check_text(target_field),
                                            tbl, self.schema)
        self.reset_input_handler_widget()

    def reset_input_handler_widget(self):
        """
        Resets the input handler widget
        :return:
        """
        self.ISD.EPSG.setText('4326')
        self.ISD.TWColumnNames.setRowCount(0)
        self.ISD.TWtoParam.setRowCount(0)
        self.ISD.pButContinue.setEnabled(False)
        self.ISD.RBDateOnly.setEnabled(False)
        self.ISD.DE.setDate(QtCore.QDate.fromString('2000-01-01', 'yyyy-MM-dd'))
        self.ISD.ComBDate.clear()
        self.ISD.pButInsertDataIntoDB.setEnabled(False)
        self.ISD.param_row_count = 0
        self.ISD.add_input_file.clicked.disconnect()
        self.ISD.pButAdd_Param.clicked.disconnect()
        self.ISD.pButRem_Param.clicked.disconnect()
        self.ISD.pButInsertDataIntoDB.clicked.disconnect()
        self.ISD.pButContinue.clicked.disconnect()
        self.ISD.done(0)
