#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Apr  3 13:26:39 2019

@author: sebastien@gardoll.fr
"""

from yaml_class import YamlSerializable
from enum_utils import DbFormat, CoordinateFormat, SelectionShape
from os import path
from variable import Variable
import logging

class ExtractionConfig(YamlSerializable):

  FILE_NAME_POSTFIX = 'extraction_config.yml'

  def compute_filename(self):
    return ClassificationLabel.generate_filename(self.str_id)

  @staticmethod
  def generate_filename(str_id):
    return f"{str_id}_{ExtractionConfig.FILE_NAME_POSTFIX}"

  def __init__(self, str_id=None):
    super().__init__(str_id)

    # x and y size of an image of the tensor.
    self.x_size = None
    self.y_size = None
    # Ordered list of variable file path descriptions.
    self.variable_file_paths = None
    # List of label file path descriptions.
    self.label_file_paths = None
    self.selection_shape = None
    # The path of required directories for an extraction.
    self.tensor_dir_path = None
    self.channel_dir_path = None
    self.tmp_dir_path = None

    # The number of netcdf files extracted per cycle of extractions.
    self.batch_size = None

    # The number of process per cycle of extractions.
    self.nb_process = None

    self._variables = None # Transient for yaml serialization.
    self._labels = None # Transient for yaml serialization.


  def save(self, file_path):
    variables = self._variables
    labels = self._labels
    del self._variables
    del self._labels
    super().save(file_path)
    self._variables = variables
    self._labels = labels

  def get_variables(self):
    variables_value = getattr(self, '_variables', None)
    if variables_value is None:
      logging.debug(f"loading the variables of {self.str_id}:")
      self._variables = list() # Preserve the order.
      for var_file_path in self.variable_file_paths:
        logging.debug(f"loading the variable {var_file_path}")
        var = Variable.load(var_file_path)
        self._variables.append(var)

    return self._variables

  def get_labels(self):
    labels_value = getattr(self, '_labels', None)
    if labels_value is None:
      logging.debug(f"loading the labels of {self.str_id}:")
      self._labels = list() # Preserve the order.
      for label_file_path in self.label_file_paths:
        logging.debug(f"loading the label {label_file_path}")
        label = ClassificationLabel.load(label_file_path)
        self._labels.append(label)

    return self._labels


class ClassificationLabel(YamlSerializable):

  YEAR_KEY  = 'year'
  MONTH_KEY = 'month'
  DAY_KEY   = 'day'
  HOUR_KEY  = 'hour'
  LAT_KEY   = 'lat'
  LON_KEY   = 'lon'

  FILE_NAME_POSTFIX = 'label.yml'

  def compute_filename(self):
    return ClassificationLabel.generate_filename(self.str_id, self.display_name)

  @staticmethod
  def generate_filename(str_id, name):
    return f"{str_id}_{name}_{ClassificationLabel.FILE_NAME_POSTFIX}"

  def __init__(self, str_id=None):
    super().__init__(str_id)

    # Numerical id that encode the label.
    self.num_id          = None
    # The name of the label to be displayed to the user.
    self.display_name    = None
    # The path to the db that contains the information of the labels.
    self.db_file_path    = None
    # The format of the data base of labels (CSV, etc.)
    self.db_format       = None
    # Dictionary that maps required information about the labels (see keys).
    self.db_mapping      = None
    # The format of the latitudes.
    self.lat_format      = None
    # The format of the longitudes.
    self.lon_format      = None

  def __repr__(self):
    return f"{self.__class__.__name__}(str_id={self.str_id}, name={self.display_name}, " \
      f"num_id={self.num_id}, db={self.db_file_path})"

"""
import logging
logger = logging.getLogger()
handler = logging.StreamHandler()
formatter = logging.Formatter('%(levelname)-8s %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

from extraction import bootstrap_cyclone_labels
bootstrap_cyclone_labels()
"""
def bootstrap_cyclone_labels():
  label_parent_dir = '/home/sgardoll/cyclone/extraction_config'
  dataset = ['2ka', '2kb', '2000', '2000_10', 'all']
  data_parent_dir = '/data/sgardoll/cyclone_data/dataset'
  filename_postfix = 'dataset.csv'
  db_filename_template = '{str_id}_{display_name}_{filename_postfix}'
  lat_format = CoordinateFormat.INCREASING_DEGREE_NORTH
  lon_format = CoordinateFormat.EUROPEAN_DEGREE_EAST
  db_format = DbFormat.CSV
  db_mapping = {ClassificationLabel.YEAR_KEY: 'year',
                ClassificationLabel.MONTH_KEY: 'month',
                ClassificationLabel.DAY_KEY: 'day',
                ClassificationLabel.HOUR_KEY: 'hour',
                ClassificationLabel.LAT_KEY: 'lat',
                ClassificationLabel.LON_KEY: 'lon'}

  def create_label(str_id, num_id, display_name):
    label = ClassificationLabel()
    label.str_id = str_id
    label.num_id = num_id
    label.db_file_path = ''
    label.display_name = display_name
    label.db_format = db_format
    label.db_mapping = db_mapping
    label.lat_format = lat_format
    label.lon_format = lon_format
    db_filename = db_filename_template.format(str_id=str_id,
                                              display_name=display_name,
                                              filename_postfix=filename_postfix)
    label.db_file_path = path.join(data_parent_dir, db_filename)
    label_file_path = path.join(label_parent_dir, label.compute_filename())
    label.save(label_file_path)

  for str_id in dataset:
    create_label(str_id, 1.0, 'cyclone')
    create_label(str_id, 0.0, 'no_cyclone')

"""
import logging
logger = logging.getLogger()
handler = logging.StreamHandler()
formatter = logging.Formatter('%(levelname)-8s %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

from extraction import bootstrap_cyclone_extraction_configs
bootstrap_cyclone_extraction_configs()
"""
def bootstrap_cyclone_extraction_configs():
  config_parent_dir = '/home/sgardoll/cyclone/extraction_config'
  output_parent_dir = '/data/sgardoll/cyclone_data'
  dataset = ['2ka', '2kb', '2000', '2000_10', 'all']
  era5_variables = ['msl', 'tcwv','u10', 'v10', 'ta200', 'ta500', 'u850', 'v850']
  x_size = 32
  y_size = 32
  selection_shape = SelectionShape.SQUARE
  tensor_dir_path = path.join(output_parent_dir, 'tensor')
  channel_dir_path = path.join(output_parent_dir, 'channel')
  tmp_dir_path = path.join(output_parent_dir, 'tmp')
  batch_size = 12
  nb_process = 4

  variable_file_paths = list()
  for var_str_id in era5_variables:
    var_filename = Variable.generate_filename(var_str_id)
    variable_file_paths.append(path.join(config_parent_dir, var_filename))

  for str_id in dataset:
    labels = [f"{config_parent_dir}/{ClassificationLabel.generate_filename(str_id, 'cyclone')}",
              f"{config_parent_dir}/{ClassificationLabel.generate_filename(str_id, 'no_cyclone')}"]
    extract_config = ExtractionConfig()
    extract_config.str_id = str_id
    extract_config.x_size = x_size
    extract_config.y_size = y_size
    extract_config.variable_file_paths = variable_file_paths
    extract_config.label_file_paths = labels
    extract_config.selection_shape = selection_shape
    extract_config.tensor_dir_path = tensor_dir_path
    extract_config.channel_dir_path = channel_dir_path
    extract_config.tmp_dir_path = tmp_dir_path
    extract_config.batch_size = batch_size
    extract_config.nb_process = nb_process

    file_path = path.join(config_parent_dir, ExtractionConfig.generate_filename(str_id))
    extract_config.save(file_path)

  """
  import logging
  logger = logging.getLogger()
  handler = logging.StreamHandler()
  formatter = logging.Formatter('%(levelname)-8s %(message)s')
  handler.setFormatter(formatter)
  logger.addHandler(handler)
  logger.setLevel(logging.DEBUG)

  from extraction import test_load
  test_load()
  """
def test_load():
  config_parent_dir = '/home/sgardoll/cyclone/extraction_config'
  dataset = ['2ka', '2kb', '2000', '2000_10', 'all']
  for str_id in dataset:
    filename = ExtractionConfig.generate_filename(str_id)
    conf = ExtractionConfig.load(path.join(config_parent_dir, filename))
    conf.get_variables()
    conf.get_labels()