#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Apr  22 09:20:10 2020

@author: sebastien@gardoll.fr
"""
from typing import Dict, Set, NewType, Tuple, Callable, Mapping, Union, Sequence

import pandas as pd
import xarray as xr

from nxtensor.exceptions import ConfigurationError
from nxtensor.utils.coordinate_utils import Coordinate
from nxtensor.utils.time_utils import TimeResolution
from nxtensor.utils.db_utils import CsvOptNames, DBMetadataMapping, create_db_metadata_mapping

from multiprocessing import Pool
import os.path as path
import os

import nxtensor.utils.file_utils as fu

from nxtensor.utils.file_utils import FileExtension


# [Types]


# A block of extraction metadata (lat, lon, year, month, etc.).
Block = NewType('Block', pd.DataFrame)

# A Period is a tuple composed of values that correspond to the values of TimeResolution::KEYS (same order).
Period = NewType('Period', Tuple[Union[float, int], ...])

# Constants
DEFAULT_CSV_SAVE_OPTIONS: Mapping[CsvOptNames, str] = {CsvOptNames.SEPARATOR: ',', CsvOptNames.ENCODING: 'utf8',
                                                       CsvOptNames.SAVE_LINE_TERMINATOR: '\\n'}
INDEX_NAME = 'index'


__extraction_metadata_block_processing_function: Callable[[Period, Mapping[str, Block]],
                                                          Tuple[str, Dict[str, xr.DataArray]]]
__extraction_metadata_block_csv_save_options: Mapping[CsvOptNames, str]


def convert_block_to_dict(extraction_metadata_block: Block) -> Sequence[Mapping[Union[TimeResolution, Coordinate],
                                                                                Union[int, float, str]]]:
    result = extraction_metadata_block.to_dict('records')
    for dictionary in result:
        dictionary[TimeResolution.MONTH2D] = f"{dictionary[TimeResolution.MONTH]:02d}"
        dictionary[TimeResolution.DAY2D] = f"{dictionary[TimeResolution.DAY]:02d}"
        dictionary[TimeResolution.HOUR2D] = f"{dictionary[TimeResolution.HOUR]:02d}"
    return result


def extract(extraction_metadata_block_processing_function: Callable[[Period, Mapping[str, Block]],
                                                                    Tuple[str, Dict[str, xr.DataArray]]],
            extraction_metadata_blocks: Mapping[str, pd.DataFrame],
            db_metadata_mappings: Mapping[str, DBMetadataMapping],
            netcdf_file_time_period: TimeResolution,
            nb_workers: int = 0,
            inplace=False,
            extraction_metadata_block_csv_save_options: Mapping[CsvOptNames, str] = DEFAULT_CSV_SAVE_OPTIONS)\
            -> Dict[Period, Dict[str, Dict[str, str]]]:
    # Returns the data extraction_metadata_blocks and the extraction data extraction_metadata_blocks according to
    # the label for all the period of time.
    structures = dict()
    for label_id, dataframe in extraction_metadata_blocks.items():
        db_metadata_mapping = db_metadata_mappings[label_id]
        structure = __build_blocks_structure(dataframe, db_metadata_mapping, netcdf_file_time_period, inplace)
        structures[label_id] = structure

    merged_structures: Dict[Period, Dict[str, Block]] = __merge_block_structures(structures)
    del structures
    if CsvOptNames.SAVE_LINE_TERMINATOR in extraction_metadata_block_csv_save_options:
        if extraction_metadata_block_csv_save_options[CsvOptNames.SAVE_LINE_TERMINATOR] == \
                DEFAULT_CSV_SAVE_OPTIONS[CsvOptNames.SAVE_LINE_TERMINATOR]:
            extraction_metadata_block_csv_save_options = \
                {k: v for k, v in extraction_metadata_block_csv_save_options.items()}
            extraction_metadata_block_csv_save_options[CsvOptNames.SAVE_LINE_TERMINATOR] = '\n'

    global __extraction_metadata_block_csv_save_options
    __extraction_metadata_block_csv_save_options = extraction_metadata_block_csv_save_options
    global __extraction_metadata_block_processing_function
    __extraction_metadata_block_processing_function = extraction_metadata_block_processing_function

    if nb_workers:
        with Pool(processes=nb_workers) as pool:
            tmp_result = pool.map(func=__core_extraction, iterable=merged_structures.items(), chunksize=1)
    else:
        for item in merged_structures.items():
            tmp_result = __core_extraction(item)

    result = dict(tmp_result)
    return result


def __core_extraction(merged_structures_item) -> Tuple[Period, Dict[str, Dict[str, str]]]:
    period, extraction_metadata_blocks = merged_structures_item
    result: Dict[str, Dict[str, str]] = dict()
    file_prefix_path, extracted_data_blocks = \
        __extraction_metadata_block_processing_function(period, extraction_metadata_blocks)

    for label_id, data_block in extracted_data_blocks:
        specific_label_file_prefix_path = path.join(file_prefix_path, label_id, f"{period}{fu.NAME_SEPARATOR}")
        os.makedirs(path.dirname(file_prefix_path), exist_ok=True)

        extraction_metadata_block_file_path = f"{specific_label_file_prefix_path}.{FileExtension.CSV_FILE_EXTENSION}"
        extraction_metadata_blocks[label_id].to_csv(path_or_buf=extraction_metadata_block_file_path,
                                                    **__extraction_metadata_block_csv_save_options)

        data_block_file_path = f"{specific_label_file_prefix_path}.{FileExtension.HDF5_FILE_EXTENSION}"
        fu.write_ndarray_to_hdf5(specific_label_file_prefix_path, data_block.values)

        result[label_id] = dict()
        result[label_id]['data_block'] = data_block_file_path
        result[label_id]['metadata_block'] = extraction_metadata_block_file_path
    return period, result


# Enable processing of extractions period by period so as to open a netcdf file only one time.
def __merge_block_structures(structures: Mapping[str, Dict[Period, Block]]) -> Dict[Period, Dict[str, Block]]:
    # str for label_id.
    # Build a set of periods.
    # (like (year, month), e.g. (2000, 10)).
    periods: Set[Period] = set()
    for structure in structures.values():
        periods.update(structure.keys())

    result: Dict[Period, Dict[str, Block]] = dict()
    for period in periods:
        for label_id, structure in structures.items():
            if period in structure:
                if period not in result:
                    result[period] = dict()
                blocks = result[period]
                blocks[label_id] = structure[period]

    return result


def __build_blocks_structure(dataframe: pd.DataFrame, db_metadata_mapping: DBMetadataMapping,
                             netcdf_file_time_period: TimeResolution, inplace=False) \
                             -> Dict[Period, Block]:
    # Return the dataframe grouped by the given period covered by the netcdf file.
    # The result is a dictionary of extraction_metadata_blocks (rows of the given dataframe) mapped with a
    # period (a tuple of time attributes).
    # It also renames (inplace or not) the name of the columns of the dataframe, according
    # to the given db_metadata_mapping which has to be generate by the time_utils.create_db_metadata_mapping function.
    # Example :
    # if the netcdf file covers a month of data, the period is the month.
    # This function returns the dataframe grouped by period of (year, month).
    # (2000, 1)
    #     - dataframe row at index 6
    #     - dataframe row at index 19
    #     - dataframe row at index 21
    #     ...
    # (2000, 2)
    #     - dataframe row at index 2
    #     - dataframe row at index 7
    #     ...
    #  ...
    try:
        resolution_degree = TimeResolution.KEYS.index(netcdf_file_time_period)
    except ValueError as e:
        msg = f"'{netcdf_file_time_period}' is not a known time resolution"
        raise ConfigurationError(msg, e)

    list_keys = TimeResolution.KEYS[0:(resolution_degree+1)]
    list_column_names = [db_metadata_mapping[key] for key in list_keys]
    indices = dataframe.groupby(list_column_names).indices

    # Rename the columns of the dataframe.
    reverse_metadata_mapping = {v: k for k, v in db_metadata_mapping.items()}
    if inplace:
        dataframe.rename(reverse_metadata_mapping, axis='columns', inplace=True)
        renamed_df = dataframe
    else:
        renamed_df = dataframe.rename(reverse_metadata_mapping, axis='columns', inplace=False)

    renamed_df.index.name = INDEX_NAME
    # Select only the columns of interest (lat, lon, year, etc.).
    restricted_renamed_df = renamed_df[db_metadata_mapping.keys()]

    # Compute the extraction_metadata_blocks.
    result: Dict[Period, Block] = dict()
    for index in indices.keys():
        result[index] = restricted_renamed_df.loc[indices[index]]

    return result


def __unit_test_build_blocks_from_csv(csv_file_path: str, period_resolution: TimeResolution) -> Dict[Period, Block]:
    dataframe = pd.read_csv(filepath_or_buffer=csv_file_path, sep=',', header=0)
    db_metadata_mapping = create_db_metadata_mapping(year='year', month='month', day='day', hour='hour',
                                                     lat='lat', lon='lon')
    return __build_blocks_structure(dataframe, db_metadata_mapping, period_resolution, True)


def __unit_test1():
    cyclone_csv_file_path = '/Users/seb/tmp/extraction_config/2000_10_cyclone_dataset.csv'
    no_cyclone_csv_file_path = '/Users/seb/tmp/extraction_config/2000_10_no_cyclone_dataset.csv'
    period_resolution = TimeResolution.MONTH

    structures = dict()
    structures['cyclone'] = __unit_test_build_blocks_from_csv(cyclone_csv_file_path, period_resolution)
    structures['no_cyclone'] = __unit_test_build_blocks_from_csv(no_cyclone_csv_file_path, period_resolution)

    merged_structures = __merge_block_structures(structures)
    assert str(merged_structures.keys()) == 'dict_keys([(2000, 9), (2000, 10)])'
    period1 = list(merged_structures.keys())[0]
    period2 = list(merged_structures.keys())[1]
    assert len(merged_structures[period2]['cyclone']) == 49
    assert len(merged_structures[period2]['no_cyclone']) == 51
    assert 'cyclone' not in merged_structures[period1]
    assert len(merged_structures[period1]['no_cyclone']) == 47
    converted_block = convert_block_to_dict(structures['cyclone'][period2])
    print(converted_block[0:2])


def __unit_test2():
    # TODO: test extraction.
    cyclone_csv_file_path = '/Users/seb/tmp/extraction_config/2000_10_cyclone_dataset.csv'
    no_cyclone_csv_file_path = '/Users/seb/tmp/extraction_config/2000_10_no_cyclone_dataset.csv'
    extraction_metadata = dict()
    extraction_metadata['cyclone'] = pd.read_csv(filepath_or_buffer=cyclone_csv_file_path, sep=',', header=0)
    extraction_metadata['no_cyclone'] = pd.read_csv(filepath_or_buffer=no_cyclone_csv_file_path, sep=',', header=0)
