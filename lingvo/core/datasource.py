# Lint as: python2, python3
# Copyright 2018 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""DataSources describe how files should be used to provide data."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import lingvo.compat as tf
from lingvo.core import hyperparams
from lingvo.core import py_utils

import six


class DataSource(object):
  """A base class for file based Data Sources."""

  @classmethod
  def Params(cls):
    p = hyperparams.InstantiableParams(cls)
    return p

  def __init__(self, params):
    self.params = params.Copy()

  def BuildDataSource(self, data_source_from_file_pattern_fn):
    """Builds a data source.

    Subclasses implement this.

    Args:
      data_source_from_file_pattern_fn: a function that takes file_pattern and
        input_source_weights as arguments and returns an input batch from a
        string file_pattern.

    Returns:
      A NestedMap containing: data: a tuple of tf.Tensor or `.NestedMap` of
      tf.Tensor same as `BaseInputGeneratorFromFiles._DataSourceFromFilePattern(
      file_pattern, input_source_weights=None)`, source_selected: a
      tensor of size [batch_size, number of data sources], selected_bprop: a
      tensor of size [number of data sources] bprop_variable_filters: containing
      a list of bprop_variable filters for each source
    """
    raise NotImplementedError()


class SimpleDataSource(DataSource):
  """A simple file based data source."""

  @classmethod
  def Params(cls):
    p = super(SimpleDataSource, cls).Params()
    p.Define(
        'file_pattern', '', 'A single file pattern string which can '
        'contain a single file pattern, or a comma separated list of patterns.'
        'Samples from each file with unspecified likelihood, though in practice'
        ' this will be roughly equal per file.  To explicitly '
        'describe the mixture weights of different file patterns use '
        'WithinBatchMixingDataSource or CrossBatchMixingDataSource')
    return p

  def BuildDataSource(self, data_source_from_file_pattern_fn):
    """Builds a simple, unweighted Data Source.

    Args:
      data_source_from_file_pattern_fn: a function that takes file_pattern as an
        argument and returns an input batch.

    Returns:
      A NestedMap containing: data: a tuple of tf.Tensor or `.NestedMap` of
      tf.Tensor.
    """
    p = self.params
    if not isinstance(p.file_pattern, six.string_types):
      raise ValueError(
          'SimpleDataSource expects p.file_pattern to be a string.'
          ' To use multiple files use a comma separated string, '
          'e.g. ', '.join(list_of_file_patterns)')
    ret = py_utils.NestedMap()
    ret.data = data_source_from_file_pattern_fn(p.file_pattern)
    return ret


class ChainingDataSource(DataSource):
  """A data source that reads each file_pattern in sequence."""

  @classmethod
  def Params(cls):
    p = super(ChainingDataSource, cls).Params()
    p.Define(
        'file_patterns', [], 'A list of file pattern strings which are read '
        'from in sequence. Commas cannot be used in individual file_patterns.')
    return p

  def BuildDataSource(self, data_source_from_file_pattern_fn):
    """Builds a Chaining Data Source.

    Args:
      data_source_from_file_pattern_fn: a function that takes file_pattern as an
        argument and returns an input batch.

    Returns:
      A NestedMap containing data: a tuple of tf.Tensor or `.NestedMap` of
      tf.Tensor

    Raises:
      ValueError: If unknown token type.
    """
    p = self.params
    if not isinstance(p.file_patterns, list):
      raise ValueError('Expected a list, got %s' % (p.file_patterns,))
    if not all(isinstance(x, six.string_types) for x in p.file_patterns):
      # Chaining doesn't work with weights or backprop filters, i.e. when
      # file_pattern param contains a list of
      # <file_pattern, weight, [bprop_variable_filter]> tuples.
      raise ValueError('Expected a list of strings, got %s' %
                       (p.file_patterns,))

    for file_pattern in p.file_patterns:
      if ',' in file_pattern:
        raise ValueError('Can not use commas in file_pattern when chaining '
                         'is used. file_pattern: %s' % (file_pattern,))
    ret = py_utils.NestedMap()
    ret.data = data_source_from_file_pattern_fn(','.join(p.file_patterns))
    ret.bprop_variable_filters = [''] * len(p.file_patterns)
    return ret


class WithinBatchMixingDataSource(DataSource):
  """A data source that reads each file_pattern in sequence."""

  @classmethod
  def Params(cls):
    p = super(WithinBatchMixingDataSource, cls).Params()
    p.Define(
        'file_patterns', [], 'A list of file pattern strings which are read '
        'from in sequence. Commas cannot be used in individual file_patterns. ')
    p.Define('weights', [], 'A list of weights for each file pattern')
    return p

  def BuildDataSource(self, data_source_from_file_pattern_fn):
    """Read and return input batch from p.file_patterns list weighted by p.weights.

    Examples in the batch will be mixed together from different file_pattern
    source proportionally to the weights.

    Args:
      data_source_from_file_pattern_fn: a function that takes file_pattern and
        input_source_weights as arguments and returns an input batch from a
        string file_pattern.

    Returns:
      A NestedMap containing: data: a tuple of tf.Tensor or `.NestedMap` of
      tf.Tensor

    Raises:
      ValueError: If unknown token type.
    """
    p = self.params
    if not isinstance(p.file_patterns, list):
      raise ValueError('Expected a list, got %s' % (p.file_patterns,))
    if not isinstance(p.weights, list):
      raise ValueError('Expected a list, got %s' % (p.weights,))
    if len(p.file_patterns) != len(p.weights):
      raise ValueError(
          'Expected p.file_patterns and p.weights to be the same length. '
          'Found %d file_patterns, and %d weights' %
          (len(p.file_patterns), len(p.weights)))
    # TODO(rosenberg) confirm that weights are numeric
    if not all(isinstance(x, six.string_types) for x in p.file_patterns):
      raise ValueError('Expected all elements of p.file_patterns to be strings')

    file_patterns = p.file_patterns
    weights = p.weights
    for file_pattern in file_patterns:
      if ',' in file_pattern:
        raise ValueError('Can not use commas in file_pattern when within-batch '
                         'mixing is used. file_pattern: %s' % (file_pattern,))
    ret = py_utils.NestedMap()
    ret.data = data_source_from_file_pattern_fn(
        ','.join(file_patterns), input_source_weights=weights)
    ret.bprop_variable_filters = [''] * len(file_patterns)
    return ret


class CrossBatchMixingDataSource(DataSource):
  """A data source that reads each file_pattern in sequence."""

  @classmethod
  def Params(cls):
    p = super(CrossBatchMixingDataSource, cls).Params()
    p.Define(
        'file_patterns', [], 'A list of file pattern strings which are read '
        'from in sequence. Commas cannot be used in individual file_patterns. ')
    p.Define('weights', [], 'A list of weights for each file pattern')
    p.Define(
        'bprop_variable_filters', [], 'An optional list of '
        'bprop_variariable_filters for each file_pattern.  If not empty, '
        'expected to have the same length as file_pattern and weights')
    return p

  def BuildDataSource(self, data_source_from_file_pattern_fn):
    """Read and return input batch from a p.file_pattern list.

    `p.file_patterns` is a list of file patterns, `p.weights` contains
    weights for each file pattern.  If provided `p.bprop_variable_filters`
    includes a bprop_variable_filter for each file pattern.

    Args:
      data_source_from_file_pattern_fn: a function that takes file_pattern as an
        argument and returns an input batch.

    Returns:
      A NestedMap containing:
        data: a tuple of tf.Tensor or `.NestedMap` of tf.Tensor
        source_selected: a tensor of size [batch_size, number of data sources]
        selected_bprop: a tensor of size [number of data sources]
        bprop_variable_filters: containing a list of bprop_variable filters for
        each source

    Raises:
      ValueError: If unknown token type.
    """
    p = self.params

    def _MakeDataSourceFromFilePatternFunc(data_source_from_file_pattern_fn,
                                           file_pattern):
      # It's important to invoke self._DataSourceFromFilePattern() inside the
      # lambda to make sure that the record is drawn from data source
      # only if it will be used. Weights are handled by MixByWeight, not the
      # data_source_from_file_pattern_fn.
      return lambda: data_source_from_file_pattern_fn(file_pattern)

    if len(p.weights) != len(p.file_patterns):
      raise ValueError(
          'Expected p.file_patterns and p.weights to be the same length. '
          'Found %d file_patterns, and %d weights' %
          (len(p.file_patterns), len(p.weights)))
    if not all(isinstance(x, six.string_types) for x in p.file_patterns):
      raise ValueError('Expected all elements of p.file_patterns to be strings')

    # TODO(rosenberg) replace this with functools.partial
    inputs = [
        _MakeDataSourceFromFilePatternFunc(data_source_from_file_pattern_fn,
                                           file_pattern)
        for file_pattern in p.file_patterns
    ]
    weights = p.weights
    if not p.bprop_variable_filters:
      bprop_variable_filters = [''] * len(inputs)
    else:
      bprop_variable_filters = p.bprop_variable_filters

    data_source, selected_bprop = py_utils.MixByWeight(inputs, weights)
    # TODO(neerajgaur): Remove _bprop_onehot and change code that uses it to
    # use source_selected from input_batch.
    batch_size = py_utils.GetShape(tf.nest.flatten(data_source)[0])[0]
    ret = py_utils.NestedMap()
    ret.data = data_source
    ret.bprop_variable_filters = bprop_variable_filters
    ret.selected_bprop = selected_bprop
    ret.source_selected = tf.tile(
        tf.expand_dims(selected_bprop, 0), [batch_size, 1])
    return ret
