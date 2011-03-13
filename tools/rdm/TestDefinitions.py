# !/usr/bin/python
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Library General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
#
# TestDefinitions.py
# Copyright (C) 2010 Simon Newton

'''This defines all the tests for RDM responders.'''

__author__ = 'nomis52@gmail.com (Simon Newton)'

import datetime
import operator
import struct
from ExpectedResults import *
from ResponderTest import ResponderTestFixture, ResponderTestFixture
from ResponderTest import OptionalParameterTestFixture
from TestCategory import TestCategory
from ola import PidStore
from ola import RDMConstants
from ola.OlaClient import RDMNack
from ola.PidStore import ROOT_DEVICE
import TestMixins

MAX_DMX_ADDRESS = 512
MAX_LABEL_SIZE = 32
MAX_PERSONALITY_NUMBER = 255


# Device Info tests
#------------------------------------------------------------------------------
class DeviceInfoTest(object):
  """The base device info test class."""
  PID = 'DEVICE_INFO'

  FIELDS = ['device_model', 'product_category', 'software_version',
            'dmx_footprint', 'current_personality', 'personality_count',
            'dmx_start_address', 'sub_device_count', 'sensor_count']
  FIELD_VALUES = {
      'protocol_major': 1,
      'protocol_minor': 0,
  }


class GetDeviceInfo(ResponderTestFixture, DeviceInfoTest):
  """GET device info & verify."""
  CATEGORY = TestCategory.CORE

  PROVIDES = [
      'current_personality',
      'dmx_footprint',
      'dmx_start_address',
      'personality_count',
      'sensor_count',
      'sub_device_count',
  ]

  def Test(self):
    self.AddExpectedResults(self.AckGetResult(
      field_names=self.FIELDS,
      field_values=self.FIELD_VALUES))
    self.SendGet(ROOT_DEVICE, self.pid)

  def VerifyResult(self, unused_response, fields):
    """Check the footprint, personalities & sub devices."""
    for property in self.PROVIDES:
      self.SetPropertyFromDict(fields, property)

    footprint = fields['dmx_footprint']
    if footprint > MAX_DMX_ADDRESS:
      self.AddWarning('DMX Footprint of %d, was more than 512' % footprint)
    if footprint > 0:
      personality_count = fields['personality_count']
      current_personality = fields['current_personality']
      if personality_count == 0:
        self.AddAdvisory('DMX Footprint non 0, but no personalities listed')
      if current_personality == 0:
        self.AddWarning('Current personality should be >= 1, was %d' %
                        current_personality)
      elif current_personality > personality_count:
        self.AddWarning('Current personality (%d) should be less than the '
                        'personality count (%d)' %
                        (current_personality, personality_count))

    sub_devices = fields['sub_device_count']
    if sub_devices > 512:
      self.AddWarning('Sub device count > 512, was %d' % sub_devices)


class GetDeviceInfoWithData(ResponderTestFixture, DeviceInfoTest):
  """GET device info with param data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS

  def Test(self):
    self.AddExpectedResults([
      self.NackGetResult(RDMNack.NR_FORMAT_ERROR),
      self.AckGetResult(
        field_names=self.FIELDS,
        field_values=self.FIELD_VALUES,
        warning='Get %s with data returned an ack' % self.pid.name)
    ])
    self.SendRawGet(ROOT_DEVICE, self.pid, 'foo')


class SetDeviceInfo(ResponderTestFixture, DeviceInfoTest):
  """SET device info."""
  CATEGORY = TestCategory.ERROR_CONDITIONS

  def Test(self):
    self.AddExpectedResults(TestMixins.UnsupportedSetNacks(self.pid))
    self.SendRawSet(ROOT_DEVICE, self.pid)


class AllSubDevicesDeviceInfo(ResponderTestFixture, DeviceInfoTest):
  """Send a Get Device Info to ALL_SUB_DEVICES."""
  CATEGORY = TestCategory.SUB_DEVICES
  def Test(self):
    self.AddExpectedResults(
        self.NackGetResult(RDMNack.NR_SUB_DEVICE_OUT_OF_RANGE))
    self.SendGet(PidStore.ALL_SUB_DEVICES, self.pid)


# Supported Parameters Tests & Mixin
#------------------------------------------------------------------------------
class GetSupportedParameters(ResponderTestFixture):
  """GET supported parameters."""
  CATEGORY = TestCategory.CORE
  PID = 'SUPPORTED_PARAMETERS'
  PROVIDES = ['manufacturer_parameters', 'supported_parameters']

  # declaring support for any of these is a warning:
  MANDATORY_PIDS = ['SUPPORTED_PARAMETERS',
                    'PARAMETER_DESCRIPTION',
                    'DEVICE_INFO',
                    'SOFTWARE_VERSION_LABEL',
                    'DMX_START_ADDRESS',
                    'IDENTIFY_DEVICE']

  # Banned PIDs, these are pid values that can not appear in the list of
  # supported parameters (these are used for discovery)
  BANNED_PID_VALUES = [1, 2, 3]

  # If responders support any of the pids in these groups, the should really
  # support all of them.
  PID_GROUPS = [
      ('PROXIED_DEVICE_COUNT', 'PROXIED_DEVICES'),
      ('LANGUAGE_CAPABILITIES', 'LANGUAGE'),
      ('DMX_PERSONALITY', 'DMX_PERSONALITY_DESCRIPTION'),
      ('SENSOR_DEFINITION', 'SENSOR_VALUE'),
      ('SELF_TEST_DESCRIPTION', 'PERFORM_SELF_TEST'),
  ]

  # If the first pid in each group is supported, the remainer of the group
  # must be.
  PID_DEPENDENCIES = [
      ('RECORD_SENSORS', 'SENSOR_VALUE'),
      ('DEFAULT_SLOT_VALUE', 'SLOT_DESCRIPTION'),
  ]

  def Test(self):
    self.AddExpectedResults([
      # TODO(simon): We should cross check this against support for anything
      # more than the required set of parameters at the end of all tests.
      self.NackGetResult(RDMNack.NR_UNKNOWN_PID),
      self.AckGetResult(),
    ])
    self.SendGet(ROOT_DEVICE, self.pid)

  def VerifyResult(self, response, fields):
    if not response.WasAcked():
      self.SetProperty('manufacturer_parameters', [])
      self.SetProperty('supported_parameters', [])
      return

    mandatory_pids = {}
    for p in self.MANDATORY_PIDS:
      pid = self.LookupPid(p)
      mandatory_pids[pid.value] = pid

    supported_parameters = []
    manufacturer_parameters = []

    for item in fields['params']:
      param_id = item['param_id']
      if param_id in self.BANNED_PID_VALUES:
        self.AddWarning('%d listed in supported parameters' % param_id)
        continue

      if param_id in mandatory_pids:
        self.AddAdvisory('%s listed in supported parameters' %
                         mandatory_pids[param_id].name)
        continue

      supported_parameters.append(param_id)
      if param_id >= 0x8000 and param_id < 0xffe0:
        manufacturer_parameters.append(param_id)

    self.SetProperty('manufacturer_parameters', manufacturer_parameters)
    self.SetProperty('supported_parameters', supported_parameters)

    pid_store = PidStore.GetStore()

    for pid_names in self.PID_GROUPS:
      supported_pids = []
      unsupported_pids = []
      for pid_name in pid_names:
        pid = self.LookupPid(pid_name)
        if pid.value in supported_parameters:
          supported_pids.append(pid_name)
        else:
          unsupported_pids.append(pid_name)

      if supported_pids and unsupported_pids:
        self.AddAdvisory(
            '%s supported but %s is not' %
            (','.join(supported_pids), ','.join(unsupported_pids)))

    for pid_names in self.PID_DEPENDENCIES:
      if self.LookupPid(pid_names[0]).value not in supported_parameters:
        continue

      unsupported_pids = []
      for pid_name in pid_names[1:]:
        pid = self.LookupPid(pid_name)
        if pid.value not in supported_parameters:
          unsupported_pids.append(pid_name)
      if unsupported_pids:
        self.AddAdvisory('%s supported but %s is not' %
                         (pid_names[0], ','.join(unsupported_pids)))


class GetSupportedParametersWithData(ResponderTestFixture):
  """GET supported parameters with param data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'SUPPORTED_PARAMETERS'

  def Test(self):
    self.AddExpectedResults([
      self.NackGetResult(RDMNack.NR_FORMAT_ERROR),
      self.AckGetResult(
        warning='Get %s with data returned an ack' % self.pid.name)
    ])
    self.SendRawGet(ROOT_DEVICE, self.pid, 'foo')


class SetSupportedParameters(ResponderTestFixture):
  """Attempt to SET supported parameters."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'SUPPORTED_PARAMETERS'

  def Test(self):
    self.AddExpectedResults(TestMixins.UnsupportedSetNacks(self.pid))
    self.SendRawSet(ROOT_DEVICE, self.pid)


# Sub Devices Test
#------------------------------------------------------------------------------
class FindSubDevices(ResponderTestFixture):
  """Locate the sub devices by sending DEVICE_INFO messages."""
  CATEGORY = TestCategory.SUB_DEVICES
  PID = 'DEVICE_INFO'
  PROVIDES = ['sub_device_indices']
  REQUIRES = ['sub_device_count']

  def Test(self):
    self._device_count = self.Property('sub_device_count')
    self._sub_devices = []  # stores the sub device indices
    self._current_index = 0  # the current sub device we're trying to query
    self._CheckForSubDevice()

  def _CheckForSubDevice(self):
    # For each supported param message we should either see a sub device out of
    # range or an ack
    if len(self._sub_devices) == self._device_count:
      if self._device_count == 0:
        self.SetNotRun(' No sub devices declared')
      self.SetProperty('sub_device_indices', self._sub_devices)
      self.Stop()
      return

    if self._current_index >= PidStore.MAX_VALID_SUB_DEVICE:
      self.SetFailed('Only found %d of %d sub devices' %
                     (len(self._sub_devices), self._device_count))
      self.Stop()
      return

    self.AddExpectedResults([
      self.NackGetResult(RDMNack.NR_SUB_DEVICE_OUT_OF_RANGE,
                         action=self._CheckForSubDevice),
      self.AckGetResult(action=self._CheckForSubDevice)
    ])
    self._current_index += 1
    self.SendGet(self._current_index, self.pid)

  def VerifyResult(self, response, fields):
    if response.WasAcked():
      self._sub_devices.append(self._current_index)


# Parameter Description
#------------------------------------------------------------------------------
class GetParamDescription(ResponderTestFixture):
  """Check that GET parameter description works for any manufacturer params."""
  CATEGORY = TestCategory.RDM_INFORMATION
  PID = 'PARAMETER_DESCRIPTION'
  REQUIRES = ['manufacturer_parameters']

  def Test(self):
    self.params = self.Property('manufacturer_parameters')[:]
    if len(self.params) == 0:
      self.SetNotRun(' No manufacturer params found')
      self.Stop()
      return
    self._GetParam()

  def _GetParam(self):
    if len(self.params) == 0:
      self.Stop()
      return

    self.AddExpectedResults(
      self.AckGetResult(action=self._GetParam))
    self.current_param = self.params.pop()
    self.SendGet(ROOT_DEVICE, self.pid, [self.current_param])

  def VerifyResult(self, response, fields):
    #TODO(simon): Hook into this to add new PIDs to the store
    if not response.WasAcked():
      return

    if self.current_param != fields['pid']:
      self.SetFailed('Request for pid 0x%hx returned pid 0x%hx' %
                     (self.current_param, fields['pid']))

    if fields['type'] != 0:
      self.AddWarning('type field in parameter description is not 0, was %d' %
                      fields['type'])

    if fields['command_class'] > 3:
      self.AddWarning(
          'command class field in parameter description should be 1, 2 or 3, '
          'was %d' % fields['command_class'])


class GetParamDescriptionForNonManufacturerPid(ResponderTestFixture):
  """GET parameter description for a non-manufacturer pid."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'PARAMETER_DESCRIPTION'
  REQUIRES = ['manufacturer_parameters']

  def Test(self):
    device_info_pid = self.LookupPid('DEVICE_INFO')
    results = [
        self.NackGetResult(RDMNack.NR_UNKNOWN_PID),
        self.NackGetResult(
            RDMNack.NR_DATA_OUT_OF_RANGE,
            advisory='Parameter Description appears to be supported but no'
                     'manufacturer pids were declared'),
    ]
    if self.Property('manufacturer_parameters'):
      results = self.NackGetResult(RDMNack.NR_DATA_OUT_OF_RANGE)

    self.AddExpectedResults(results)
    self.SendGet(ROOT_DEVICE, self.pid, [device_info_pid.value])


class GetParamDescriptionWithData(ResponderTestFixture):
  """GET parameter description with param data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'PARAMETER_DESCRIPTION'
  REQUIRES = ['manufacturer_parameters']

  def Test(self):
    results = [
        self.NackGetResult(RDMNack.NR_UNKNOWN_PID),
        self.NackGetResult(RDMNack.NR_FORMAT_ERROR,
                          advisory='Parameter Description appears to be '
                                   'supported but no manufacturer pids were '
                                   'declared'),
    ]
    if self.Property('manufacturer_parameters'):
      results = self.NackGetResult(RDMNack.NR_FORMAT_ERROR)
    self.AddExpectedResults(results)
    self.SendRawGet(ROOT_DEVICE, self.pid, 'foo')


# Proxied Device Count
#------------------------------------------------------------------------------
class GetProxiedDeviceCount(OptionalParameterTestFixture):
  """GET the proxied device count."""
  CATEGORY = TestCategory.NETWORK_MANAGEMENT
  PID = 'PROXIED_DEVICE_COUNT'
  REQUIRES = ['proxied_devices']

  def Test(self):
    self.AddIfGetSupported(self.AckGetResult())
    self.SendGet(PidStore.ROOT_DEVICE, self.pid)

  def VerifyResult(self, response, unpacked_data):
    if not response.WasAcked():
      return

    proxied_devices = self.Property('proxied_devices')
    if proxied_devices is None:
      self.AddWarning(
         'PROXIED_DEVICE_COUNT ack\'ed but PROXIED_DEVICES didn\'t')
      return

    if not unpacked_data['list_changed']:
      # we expect the count to match the length of the list previously returned
      if unpacked_data['device_count'] != len(proxied_devices):
        self.SetFailed(
           'Proxied device count doesn\'t match number of devices returned')


class GetProxiedDeviceCountWithData(TestMixins.GetWithDataMixin,
                                    OptionalParameterTestFixture):
  """GET the proxied device count with extra data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'PROXIED_DEVICE_COUNT'


class SetProxiedDeviceCount(TestMixins.UnsupportedSetMixin,
                            ResponderTestFixture):
  """SET the count of proxied devices."""
  CATEGORY = TestCategory.NETWORK_MANAGEMENT
  PID = 'PROXIED_DEVICE_COUNT'


# Proxied Devices
#------------------------------------------------------------------------------
class GetProxiedDevices(TestMixins.GetMixin, OptionalParameterTestFixture):
  """GET the list of proxied devices."""
  CATEGORY = TestCategory.NETWORK_MANAGEMENT
  PID = 'PROXIED_DEVICES'
  EXPECTED_FIELD = 'uids'
  PROVIDES = ['proxied_devices']


class GetProxiedDevicesWithData(TestMixins.GetWithDataMixin,
                                OptionalParameterTestFixture):
  """GET the list of proxied devices with extra data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'PROXIED_DEVICES'


class SetProxiedDevices(TestMixins.UnsupportedSetMixin, ResponderTestFixture):
  """SET the list of proxied devices."""
  CATEGORY = TestCategory.NETWORK_MANAGEMENT
  PID = 'PROXIED_DEVICES'


# Comms Status
#------------------------------------------------------------------------------
class GetCommsStatus(OptionalParameterTestFixture):
  """GET the comms status."""
  CATEGORY = TestCategory.STATUS_COLLECTION
  PID = 'COMMS_STATUS'

  def Test(self):
    self.AddIfGetSupported(self.AckGetResult())
    self.SendGet(ROOT_DEVICE, self.pid)


class GetCommsStatusWithData(TestMixins.GetWithDataMixin,
                             OptionalParameterTestFixture):
  """GET the comms status with extra data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'COMMS_STATUS'


class ClearCommsStatus(OptionalParameterTestFixture):
  """Clear the comms status."""
  CATEGORY = TestCategory.STATUS_COLLECTION
  PID = 'COMMS_STATUS'

  def Test(self):
    self.AddIfSetSupported(self.AckSetResult(action=self.VerifySet))
    self.SendSet(ROOT_DEVICE, self.pid)

  def VerifySet(self):
    self.AddIfGetSupported(
        self.AckGetResult(field_values={
            'short_message': 0,
            'length_mismatch': 0,
            'checksum_fail': 0
        }))
    self.SendGet(ROOT_DEVICE, self.pid)


class ClearCommsStatusWithData(TestMixins.SetWithDataMixin,
                               OptionalParameterTestFixture):
  """Clear the comms status with data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'COMMS_STATUS'


# Product Detail Id List
#------------------------------------------------------------------------------
class GetProductDetailIdList(OptionalParameterTestFixture):
  """GET the list of product detail ids."""
  CATEGORY = TestCategory.PRODUCT_INFORMATION
  PID = 'PRODUCT_DETAIL_ID_LIST'

  def Test(self):
    self.AddIfGetSupported(self.AckGetResult(field_names=['detail_ids']))
    self.SendGet(ROOT_DEVICE, self.pid)


class GetProductDetailIdListWithData(TestMixins.GetWithDataMixin,
                                     OptionalParameterTestFixture):
  """GET product detail id list with param data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'PRODUCT_DETAIL_ID_LIST'


class SetProductDetailIdList(TestMixins.UnsupportedSetMixin,
                             ResponderTestFixture):
  """SET product detail id list."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'PRODUCT_DETAIL_ID_LIST'


# Device Model Description
#------------------------------------------------------------------------------
class GetDeviceModelDescription(TestMixins.GetMixin,
                                OptionalParameterTestFixture):
  """GET the device model description."""
  CATEGORY = TestCategory.PRODUCT_INFORMATION
  PID = 'DEVICE_MODEL_DESCRIPTION'
  EXPECTED_FIELD = 'description'


class GetDeviceModelDescriptionWithData(TestMixins.GetWithDataMixin,
                                        OptionalParameterTestFixture):
  """Get device model description with param data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DEVICE_MODEL_DESCRIPTION'


class SetDeviceModelDescription(TestMixins.UnsupportedSetMixin,
                                OptionalParameterTestFixture):
  """Attempt to SET the device model description with no data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DEVICE_MODEL_DESCRIPTION'


class SetDeviceModelDescriptionWithData(TestMixins.UnsupportedSetMixin,
                                        OptionalParameterTestFixture):
  """SET the device model description with data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DEVICE_MODEL_DESCRIPTION'
  DATA = 'FOO BAR'


# Manufacturer Label
#------------------------------------------------------------------------------
class GetManufacturerLabel(TestMixins.GetMixin,
                           OptionalParameterTestFixture):
  """GET the manufacturer label."""
  CATEGORY = TestCategory.PRODUCT_INFORMATION
  PID = 'MANUFACTURER_LABEL'
  EXPECTED_FIELD = 'label'


class GetManufacturerLabelWithData(TestMixins.GetWithDataMixin,
                                   OptionalParameterTestFixture):
  """Get manufacturer label with param data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'MANUFACTURER_LABEL'


class SetManufacturerLabel(TestMixins.UnsupportedSetMixin,
                           OptionalParameterTestFixture):
  """Attempt to SET the manufacturer label with no data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'MANUFACTURER_LABEL'


class SetManufacturerLabelWithData(TestMixins.UnsupportedSetMixin,
                                   OptionalParameterTestFixture):
  """SET the manufacturer label with data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'MANUFACTURER_LABEL'
  DATA = 'FOO BAR'


# Device Label
#------------------------------------------------------------------------------
class GetDeviceLabel(TestMixins.GetMixin,
                     OptionalParameterTestFixture):
  """GET the device label."""
  CATEGORY = TestCategory.PRODUCT_INFORMATION
  PID = 'DEVICE_LABEL'
  PROVIDES = ['device_label']
  EXPECTED_FIELD = 'label'


class GetDeviceLabelWithData(TestMixins.GetWithDataMixin,
                             OptionalParameterTestFixture):
  """GET the device label with param data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DEVICE_LABEL'


class SetDeviceLabel(TestMixins.SetLabelMixin,
                     OptionalParameterTestFixture):
  """SET the device label."""
  CATEGORY = TestCategory.PRODUCT_INFORMATION
  PID = 'DEVICE_LABEL'
  REQUIRES = ['device_label']

  def OldValue(self):
    self.Property('device_label')


class SetFullSizeDeviceLabel(TestMixins.SetLabelMixin,
                             OptionalParameterTestFixture):
  """SET the device label."""
  CATEGORY = TestCategory.PRODUCT_INFORMATION
  PID = 'DEVICE_LABEL'
  REQUIRES = ['device_label']
  TEST_LABEL = 'this is a string with 32 charact'

  def OldValue(self):
    self.Property('device_label')


class SetNonAsciiDeviceLabel(TestMixins.SetLabelMixin,
                             OptionalParameterTestFixture):
  """SET the device label to something that contains non-ascii data."""
  CATEGORY = TestCategory.PRODUCT_INFORMATION
  PID = 'DEVICE_LABEL'
  REQUIRES = ['device_label']
  TEST_LABEL = 'string with\x0d non ascii\xc0'

  def ExpectedResults(self):
    return [
      self.NackSetResult(RDMNack.NR_UNSUPPORTED_COMMAND_CLASS),
      self.NackSetResult(RDMNack.NR_FORMAT_ERROR),
      self.AckSetResult(action=self.VerifySet)
    ]

  def OldValue(self):
    self.Property('device_label')


class SetEmptyDeviceLabel(TestMixins.SetLabelMixin,
                          OptionalParameterTestFixture):
  """SET the device label with no data."""
  CATEGORY = TestCategory.PRODUCT_INFORMATION
  PID = 'DEVICE_LABEL'
  REQUIRES = ['device_label']
  TEST_LABEL = ''

  def OldValue(self):
    self.Property('device_label')


class SetOversizedDeviceLabel(TestMixins.SetOversizedLabelMixin,
                              OptionalParameterTestFixture):
  """SET the device label with more than 32 bytes of data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  REQUIRES = ['device_label']
  PID = 'DEVICE_LABEL'

  def OldValue(self):
    self.Property('device_label')


# Factory Defaults
#------------------------------------------------------------------------------
class GetFactoryDefaults(OptionalParameterTestFixture):
  """GET the factory defaults pid."""
  CATEGORY = TestCategory.PRODUCT_INFORMATION
  PID = 'FACTORY_DEFAULTS'

  def Test(self):
    self.AddIfGetSupported(self.AckGetResult(field_names=['using_defaults']))
    self.SendGet(ROOT_DEVICE, self.pid)


class GetFactoryDefaultsWithData(TestMixins.GetWithDataMixin,
                                 OptionalParameterTestFixture):
  """GET the factory defaults pid with extra data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'FACTORY_DEFAULTS'


class ResetFactoryDefaults(OptionalParameterTestFixture):
  """Reset to factory defaults."""
  CATEGORY = TestCategory.PRODUCT_INFORMATION
  PID = 'FACTORY_DEFAULTS'

  def Test(self):
    self.AddIfSetSupported(self.AckSetResult(action=self.VerifySet))
    self.SendSet(ROOT_DEVICE, self.pid)

  def VerifySet(self):
    self.AddIfGetSupported(
      self.AckGetResult(field_values={'using_defaults': True}))
    self.SendGet(ROOT_DEVICE, self.pid)


class ResetFactoryDefaultsWithData(TestMixins.SetWithDataMixin,
                                   OptionalParameterTestFixture):
  """Reset to factory defaults with extra data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'FACTORY_DEFAULTS'


# Language Capabilities
#------------------------------------------------------------------------------
class GetLanguageCapabilities(OptionalParameterTestFixture):
  """GET the language capabilities pid."""
  CATEGORY = TestCategory.PRODUCT_INFORMATION
  PID = 'LANGUAGE_CAPABILITIES'
  PROVIDES = ['languages_capabilities']

  def Test(self):
    self.languages = []
    self.AddIfGetSupported(self.AckGetResult(field_names=['languages']))
    self.SendGet(ROOT_DEVICE, self.pid)

  def VerifyResult(self, response, fields):
    if not response.WasAcked():
      self.SetProperty('languages_capabilities', [])
      return

    self.languages = [f['language'] for f in fields['languages']]

    if len(self.languages) == 0:
      self.AddWarning('No languages returned for LANGUAGE_CAPABILITIES')

    language_set = set()
    for language in self.languages:
      if language in language_set:
        self.AddAdvisory('%s listed twice in language capabilities' % language)
      language_set.add(language)

    self.SetProperty('languages_capabilities', language_set)


class GetLanguageCapabilitiesWithData(TestMixins.GetWithDataMixin,
                                      OptionalParameterTestFixture):
  """GET the language capabilities pid with extra data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'LANGUAGE_CAPABILITIES'


# Language
#------------------------------------------------------------------------------
class GetLanguage(TestMixins.GetMixin, OptionalParameterTestFixture):
  """GET the language."""
  CATEGORY = TestCategory.PRODUCT_INFORMATION
  PID = 'LANGUAGE'
  PROVIDES = ['language']
  EXPECTED_FIELD = 'language'


class SetLanguage(OptionalParameterTestFixture):
  """SET the language."""
  CATEGORY = TestCategory.PRODUCT_INFORMATION
  PID = 'LANGUAGE'
  REQUIRES = ['language', 'languages_capabilities']

  def Test(self):
    ack = self.AckSetResult(action=self.VerifySet)
    nack = self.NackSetResult(RDMNack.NR_UNSUPPORTED_COMMAND_CLASS)

    available_langugages = list(self.Property('languages_capabilities'))
    if available_langugages:
      if len(available_langugages) > 1:
        # if the responder only supports 1 lang, we may not be able to set it
        self.AddIfSetSupported(ack)
        self.new_language = available_langugages[0]
        if self.new_language == self.Property('language'):
          self.new_language = available_langugages[2]
      else:
        self.new_language = available_langugages[0]
        self.AddIfSetSupported([ack, nack])
    else:
      # Get languages returned no languages so we expect a nack
      self.AddIfSetSupported(nack)
      self.new_language = 'en'

    self.SendSet(ROOT_DEVICE, self.pid, [self.new_language])

  def VerifySet(self):
    self.AddExpectedResults(
      self.AckGetResult(field_values={'language': self.new_language}))
    self.SendGet(ROOT_DEVICE, self.pid)


class SetNonAsciiLanguage(OptionalParameterTestFixture):
  CATEGORY = TestCategory.PRODUCT_INFORMATION
  PID = 'LANGUAGE'

  def Test(self):
    self.AddIfSetSupported(self.NackSetResult(RDMNack.NR_DATA_OUT_OF_RANGE))
    self.SendSet(ROOT_DEVICE, self.pid, ['\x0d\xc0'])


class SetUnsupportedLanguage(OptionalParameterTestFixture):
  """Try to set a language that doesn't exist in Language Capabilities."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'LANGUAGE'
  REQUIRES = ['languages_capabilities']

  def Test(self):
    if 'zz' in self.Property('languages_capabilities'):
      self.SetBroken('zz exists in the list of available languages')
      self.Stop()
      return

    self.AddIfSetSupported([
      self.NackSetResult(RDMNack.NR_UNSUPPORTED_COMMAND_CLASS),
      self.NackSetResult(RDMNack.NR_DATA_OUT_OF_RANGE),
    ])
    self.SendSet(ROOT_DEVICE, self.pid, ['zz'])


# Software Version Label
#------------------------------------------------------------------------------
class GetSoftwareVersionLabel(TestMixins.GetRequiredMixin,
                              ResponderTestFixture):
  """GET the software version label."""
  CATEGORY = TestCategory.PRODUCT_INFORMATION
  PID = 'SOFTWARE_VERSION_LABEL'
  EXPECTED_FIELD = 'label'


class GetSoftwareVersionLabelWithData(ResponderTestFixture):
  """GET the software_version_label with param data."""
  # We don't use the GetLabelMixin here because this PID is mandatory
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'SOFTWARE_VERSION_LABEL'

  def Test(self):
    self.AddExpectedResults([
      self.NackGetResult(RDMNack.NR_FORMAT_ERROR),
      self.AckGetResult(
        warning='Get %s with data returned an ack' % self.pid.name)
    ])
    self.SendRawGet(PidStore.ROOT_DEVICE, self.pid, 'foo')


class SetSoftwareVersionLabel(TestMixins.UnsupportedSetMixin,
                              ResponderTestFixture):
  """Attempt to SET the software version label."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'SOFTWARE_VERSION_LABEL'


# TODO(simon): Add a test for every sub device


# Boot Software Version
#------------------------------------------------------------------------------
class GetBootSoftwareVersion(OptionalParameterTestFixture):
  """GET the boot software version."""
  CATEGORY = TestCategory.PRODUCT_INFORMATION
  PID = 'BOOT_SOFTWARE_VERSION'

  def Test(self):
    self.AddIfGetSupported(self.AckGetResult(field_names=['version']))
    self.SendGet(ROOT_DEVICE, self.pid)


class GetBootSoftwareVersionWithData(TestMixins.GetWithDataMixin,
                                     OptionalParameterTestFixture):
  """GET the boot software version with extra data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'BOOT_SOFTWARE_VERSION'


class SetBootSoftwareVersion(TestMixins.UnsupportedSetMixin,
                             ResponderTestFixture):
  """Attempt to SET the boot software version."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'BOOT_SOFTWARE_VERSION'


# Boot Software Version Label
#------------------------------------------------------------------------------
class GetBootSoftwareLabel(TestMixins.GetMixin, OptionalParameterTestFixture):
  """GET the boot software label."""
  CATEGORY = TestCategory.PRODUCT_INFORMATION
  PID = 'BOOT_SOFTWARE_LABEL'
  EXPECTED_FIELD = 'label'


class GetBootSoftwareLabelWithData(TestMixins.GetWithDataMixin,
                                   OptionalParameterTestFixture):
  """GET the boot software label with param data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'BOOT_SOFTWARE_LABEL'


class SetBootSoftwareLabel(TestMixins.UnsupportedSetMixin,
                           OptionalParameterTestFixture):
  """SET the boot software label."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'BOOT_SOFTWARE_LABEL'


# DMX Personality & DMX Personality Description
#------------------------------------------------------------------------------
class GetZeroPersonalityDescription(OptionalParameterTestFixture):
  """GET the personality description for the 0th personality."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DMX_PERSONALITY_DESCRIPTION'

  def Test(self):
    self.AddIfGetSupported(self.NackGetResult(RDMNack.NR_DATA_OUT_OF_RANGE))
    self.SendGet(ROOT_DEVICE, self.pid, [0])


class GetOutOfRangePersonalityDescription(OptionalParameterTestFixture):
  """GET the personality description for the N + 1 personality."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DMX_PERSONALITY_DESCRIPTION'
  REQUIRES = ['personality_count']

  def Test(self):
    self.AddIfGetSupported(self.NackGetResult(RDMNack.NR_DATA_OUT_OF_RANGE))
    personality_count = self.Property('personality_count')
    self.SendGet(ROOT_DEVICE, self.pid, [personality_count + 1])


class GetPersonalityDescription(OptionalParameterTestFixture):
  """GET the personality description for the current personality."""
  CATEGORY = TestCategory.DMX_SETUP
  PID = 'DMX_PERSONALITY_DESCRIPTION'
  REQUIRES = ['current_personality', 'dmx_footprint']

  def Test(self):
    current_personality = self.Property('current_personality')
    footprint = self.Property('dmx_footprint')
    # cross check against what we got from device info
    self.AddIfGetSupported(self.AckGetResult(field_values={
        'personality': current_personality,
        'slots_required': footprint,
      }))
    self.SendGet(ROOT_DEVICE, self.pid, [current_personality])


class GetPersonality(OptionalParameterTestFixture):
  """Get the current personality settings."""
  CATEGORY = TestCategory.DMX_SETUP
  PID = 'DMX_PERSONALITY'
  REQUIRES = ['current_personality', 'personality_count']

  def Test(self):
    self.AddIfGetSupported(self.AckGetResult(
      field_names=['current_personality', 'personality_count']))
    self.SendGet(ROOT_DEVICE, self.pid)

  def VerifyResult(self, response, fields):
    if not response.WasAcked():
      return

    current_personality = self.Property('current_personality')
    personality_count = self.Property('personality_count')
    warning_str = ("Personality information in device info doesn't match"
      ' that in dmx_personality')

    if current_personality != fields['current_personality']:
      self.SetFailed('%s: current_personality %d != %d' % (
        warning_str, current_personality, fields['current_personality']))

    if personality_count != fields['personality_count']:
      self.SetFailed('%s: personality_count %d != %d' % (
        warning_str, personality_count, fields['personality_count']))


class GetPersonalities(OptionalParameterTestFixture):
  """Get information about all the personalities."""
  CATEGORY = TestCategory.DMX_SETUP
  PID = 'DMX_PERSONALITY_DESCRIPTION'
  REQUIRES = ['personality_count']
  PROVIDES = ['personalities']

  def Test(self):
    self._personalities = []
    self._personality_count = self.Property('personality_count')
    self._current_index = 0
    self._GetPersonality()

  def _GetPersonality(self):
    self._current_index += 1
    if self._current_index > self._personality_count:
      if self._personality_count == 0:
        self.SetNotRun(' No personalities declared')
      self.SetProperty('personalities', self._personalities)
      self.Stop()
      return

    if self._current_index >= MAX_PERSONALITY_NUMBER:
      # This should never happen because personality_count is a uint8
      self.SetFailed('Could not find all personalities')
      self.Stop()
      return

    self.AddIfGetSupported(self.AckGetResult(
        field_names=['slots_required', 'name'],
        field_values={'personality': self._current_index},
        action=self._GetPersonality))
    self.SendGet(ROOT_DEVICE, self.pid, [self._current_index])

  def VerifyResult(self, response, fields):
    """Save the personality for other tests to use."""
    if response.WasAcked():
      self._personalities.append(fields)


class SetPersonality(OptionalParameterTestFixture):
  """Set the personality."""
  CATEGORY = TestCategory.DMX_SETUP
  PID = 'DMX_PERSONALITY'
  # This ensures we don't modify the current personality before GetPersonality
  # and GetPersonalityDescription run
  DEPS = [GetPersonality, GetPersonalityDescription]
  REQUIRES = ['current_personality', 'personality_count', 'personalities']

  def Test(self):
    count = self.Property('personality_count')
    if count is None or count == 0:
      self.AddExpectedResults(self.NackSetResult(RDMNack.NR_UNKNOWN_PID))
      self.new_personality = {'personality': 1}  # can use anything here really
    else:
      personalities = self.Property('personalities')
      current = self.Property('current_personality')

      if len(personalities) == 0:
        self.SetFailed(
          'personality_count was non 0 but failed to fetch all personalities')
        self.Stop()
        return

      self.new_personality = personalities[0]
      for personality in personalities:
        if personality['personality'] != current:
          self.new_personality = personality
          break

      self.AddIfSetSupported(self.AckSetResult(action=self.VerifySet))

    self.SendSet(ROOT_DEVICE,
                 self.pid,
                 [self.new_personality['personality']])

  def VerifySet(self):
    self.AddIfGetSupported(
      self.AckGetResult(
        field_values={
          'current_personality': self.new_personality['personality'],
        },
        action=self.VerifyDeviceInfo))
    self.SendGet(ROOT_DEVICE, self.pid)

  def VerifyDeviceInfo(self):
    device_info_pid = self.LookupPid('DEVICE_INFO')
    self.AddIfGetSupported(
      AckGetResult(
        device_info_pid.value,
        field_values={
          'current_personality': self.new_personality['personality'],
          'dmx_footprint': self.new_personality['slots_required'],
        }))
    self.SendGet(ROOT_DEVICE, device_info_pid)


class SetZeroPersonality(OptionalParameterTestFixture):
  """Try to set the personality to 0."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DMX_PERSONALITY'

  def Test(self):
    self.AddIfSetSupported(self.NackSetResult(RDMNack.NR_DATA_OUT_OF_RANGE))
    self.SendSet(ROOT_DEVICE, self.pid, [0])


class SetOutOfRangePersonality(OptionalParameterTestFixture):
  """Try to set the personality to 0."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DMX_PERSONALITY'
  REQUIRES = ['personality_count']

  def Test(self):
    personality_count = self.Property('personality_count')
    self.AddIfSetSupported(self.NackSetResult(RDMNack.NR_DATA_OUT_OF_RANGE))
    self.SendSet(ROOT_DEVICE, self.pid, [personality_count + 1])


class SetOversizedPersonality(OptionalParameterTestFixture):
  """Send an over-sized SET personality command."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DMX_PERSONALITY'

  def Test(self):
    self.AddIfSetSupported(self.NackSetResult(RDMNack.NR_FORMAT_ERROR))
    self.SendRawSet(ROOT_DEVICE, self.pid, 'foo')


# DMX Start Address tests
#------------------------------------------------------------------------------
class GetStartAddress(ResponderTestFixture):
  """GET the DMX start address."""
  CATEGORY = TestCategory.DMX_SETUP
  PID = 'DMX_START_ADDRESS'
  REQUIRES = ['dmx_footprint', 'dmx_start_address']
  PROVIDES = ['dmx_address']

  def Test(self):
    if self.Property('dmx_footprint') > 0:
      results = self.AckGetResult(field_names=['dmx_address'])
    else:
      results = [
          self.AckGetResult(field_values={'dmx_address': 0xffff}),
          self.NackGetResult(RDMNack.NR_UNKNOWN_PID)
      ]
    self.AddExpectedResults(results)
    self.SendGet(ROOT_DEVICE, self.pid)

  def VerifyResult(self, response, fields):
    if not response.WasAcked():
      self.SetProperty('dmx_address', None)
      return

    if self.Property('dmx_start_address') != fields['dmx_address']:
      self.SetFailed(
          'DMX_START_ADDRESS (%d) doesn\'t match what was in DEVICE_INFO (%d)'
          % (self.Property('dmx_start_address'), fields['dmx_address']))
    self.SetPropertyFromDict(fields, 'dmx_address')


class SetStartAddress(ResponderTestFixture):
  """Set the DMX start address."""
  CATEGORY = TestCategory.DMX_SETUP
  PID = 'DMX_START_ADDRESS'
  REQUIRES = ['dmx_footprint', 'dmx_address']

  def Test(self):
    footprint = self.Property('dmx_footprint')
    self.start_address = 1

    current_address = self.Property('dmx_address')
    if footprint == 0 or current_address == 0xffff:
      result = self.NackSetResult(RDMNack.NR_UNKNOWN_PID)
    else:
      if footprint != MAX_DMX_ADDRESS:
        self.start_address = current_address + 1
        if self.start_address + footprint > MAX_DMX_ADDRESS + 1:
          self.start_address = 1
      result = self.AckSetResult(action=self.VerifySet)
    self.AddExpectedResults(result)
    self.SendSet(ROOT_DEVICE, self.pid, [self.start_address])

  def VerifySet(self):
    self.AddExpectedResults(
      self.AckGetResult(field_values={'dmx_address': self.start_address},
                        action=self.VerifyDeviceInfo))
    self.SendGet(ROOT_DEVICE, self.pid)

  def VerifyDeviceInfo(self):
    device_info_pid = self.LookupPid('DEVICE_INFO')
    self.AddExpectedResults(
      AckGetResult(
        device_info_pid.value,
        field_values={'dmx_start_address': self.start_address}))
    self.SendGet(ROOT_DEVICE, device_info_pid)


class SetOutOfRangeStartAddress(ResponderTestFixture):
  """Check that the DMX address can't be set to > 512."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DMX_START_ADDRESS'
  # we depend on dmx_address to make sure this runs in GetStartAddress
  DEPS = [GetStartAddress]
  REQUIRES = ['dmx_footprint']

  def Test(self):
    if self.Property('dmx_footprint') > 0:
      self.AddExpectedResults(self.NackSetResult(RDMNack.NR_DATA_OUT_OF_RANGE))
    else:
      self.AddExpectedResults(self.NackSetResult(RDMNack.NR_UNKNOWN_PID))
    data = struct.pack('!H', MAX_DMX_ADDRESS + 1)
    self.SendRawSet(ROOT_DEVICE, self.pid, data)


class SetZeroStartAddress(ResponderTestFixture):
  """Check the DMX address can't be set to 0."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DMX_START_ADDRESS'
  # we depend on dmx_address to make sure this runs in GetStartAddress
  DEPS = [GetStartAddress]
  REQUIRES = ['dmx_footprint']

  def Test(self):
    if self.Property('dmx_footprint') > 0:
      self.AddExpectedResults(self.NackSetResult(RDMNack.NR_DATA_OUT_OF_RANGE))
    else:
      self.AddExpectedResults(self.NackSetResult(RDMNack.NR_UNKNOWN_PID))
    data = struct.pack('!H', 0)
    self.SendRawSet(ROOT_DEVICE, self.pid, data)


class SetOversizedStartAddress(ResponderTestFixture):
  """Send an over-sized SET dmx start address."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DMX_START_ADDRESS'
  # we depend on dmx_address to make sure this runs in GetStartAddress
  DEPS = [GetStartAddress]
  REQUIRES = ['dmx_footprint']

  def Test(self):
    if self.Property('dmx_footprint') > 0:
      self.AddExpectedResults(self.NackSetResult(RDMNack.NR_FORMAT_ERROR))
    else:
      self.AddExpectedResults(self.NackSetResult(RDMNack.NR_UNKNOWN_PID))
    self.SendRawSet(ROOT_DEVICE, self.pid, 'foo')


# Slot Info
#------------------------------------------------------------------------------
class GetSlotInfo(OptionalParameterTestFixture):
  """Get SLOT_INFO."""
  CATEGORY = TestCategory.DMX_SETUP
  PID = 'SLOT_INFO'
  PROVIDES = ['slot_info', 'defined_slots']

  def Test(self):
    self.AddIfGetSupported(self.AckGetResult())
    self.SendGet(PidStore.ROOT_DEVICE, self.pid)

  def VerifyResult(self, response, fields):
    if not response.WasAcked():
      self.SetProperty('slot_info', {})
      self.SetProperty('defined_slots', [])
      return

    self.SetProperty('slot_info', fields)
    slots = [d['slot_offset'] for d in fields['slots']]
    self.SetProperty('defined_slots', set(slots))

    for slot in fields['slots']:
      if slot['slot_type'] not in RDMConstants.SLOT_TYPE_TO_NAME:
        self.AddWarning('Unknown slot type %d for slot %d' %
                        (slot['slot_type'], slot['slot_offset']))

      if slot['slot_type'] == RDMConstants.SLOT_TYPES['ST_PRIMARY']:
        # slot_label_id must be valid
        if slot['slot_label_id'] not in RDMConstants.SLOT_DEFINITION_TO_NAME:
          self.AddWarning('Unknown slot id %d for slot %d' %
                          (slot['slot_label_id'], slot['slot_offset']))
      else:
        # slot_label_id must reference a defined slot
        if slot['slot_label_id'] not in slots:
          self.AddWarning(
              'Slot %d is of type secondary and references an unknown slot %d'
              % (slot['slot_offset'], slot['slot_label_id']))


class GetSlotInfoWithData(TestMixins.GetWithDataMixin,
                          OptionalParameterTestFixture):
  """Get SLOT_INFO with invalid data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'SLOT_INFO'


class SetSlotInfo(TestMixins.UnsupportedSetMixin,
                  OptionalParameterTestFixture):
  """Set SLOT_INFO."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'SLOT_INFO'


# Slot Description
#------------------------------------------------------------------------------
class GetSlotDescriptions(OptionalParameterTestFixture):
  """Get the slot descriptions for all defined slots."""
  CATEGORY = TestCategory.DMX_SETUP
  PID = 'SLOT_DESCRIPTION'
  REQUIRES = ['defined_slots']

  def Test(self):
    self._slots = list(self.Property('defined_slots'))

    if self._slots:
      self._GetSlotDescription()
    else:
      self.AddIfGetSupported(self.NackGetResult(RDMNack.NR_DATA_OUT_OF_RANGE))
      self.SendGet(PidStore.ROOT_DEVICE, self.pid, [0])

  def _GetSlotDescription(self):
    if not self._slots:
      self.Stop()
      return

    self.AddIfGetSupported(self.AckGetResult(action=self._GetNextSlot))
    self.SendGet(PidStore.ROOT_DEVICE, self.pid, [self._slots[0]])

  def _GetNextSlot(self):
    self._slots.pop(0)
    self._GetSlotDescription()

  def VerifyResult(self, response, fields):
    if not response.WasAcked():
      return

    if self._slots[0] != fields['slot_number']:
      self.AddWarning(
          'Requested descriptionfor slot %d, message returned slot %d' %
          (self._current_index, fields['slot_number']))
      return


class GetSlotDescriptionWithNoData(TestMixins.GetWithNoDataMixin,
                                   OptionalParameterTestFixture):
  """Get the slot description with no slot number specified."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'SLOT_DESCRIPTION'


class GetSlotDescriptionWithTooMuchData(OptionalParameterTestFixture):
  """Get the slot description with more than 2 bytes of data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'SLOT_DESCRIPTION'

  def Test(self):
    self.AddIfGetSupported(self.NackGetResult(RDMNack.NR_FORMAT_ERROR))
    self.SendRawGet(PidStore.ROOT_DEVICE, self.pid, 'foo')


class SetSlotDescription(TestMixins.UnsupportedSetMixin,
                         OptionalParameterTestFixture):
  """Set SLOT_DESCRIPTION."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'SLOT_DESCRIPTION'


# Default Slot Value
#------------------------------------------------------------------------------
class GetDefaultSlotValues(OptionalParameterTestFixture):
  """Get DEFAULT_SLOT_VALUE."""
  CATEGORY = TestCategory.DMX_SETUP
  PID = 'DEFAULT_SLOT_VALUE'
  REQUIRES = ['defined_slots']

  def Test(self):
    self.AddIfGetSupported(self.AckGetResult())
    self.SendGet(PidStore.ROOT_DEVICE, self.pid)

  def VerifyResult(self, response, fields):
    if not response.WasAcked():
      return

    defined_slots = self.Property('defined_slots')
    default_slots = set()

    for slot in fields['slot_values']:
      if slot['slot_offset'] not in defined_slots:
        self.AddAdvisory(
          "DEFAULT_SLOT_VALUE contained slot %d, which wasn't in SLOT_INFO" %
          slot['slot_offset'])
      default_slots.add(slot['slot_offset'])

    for slot_offset in defined_slots:
      if slot_offset not in default_slots:
        self.AddAdvisory(
          "SLOT_INFO contained slot %d, which wasn't in DEFAULT_SLOT_VALUE" %
          slot_offset)


class GetDefaultSlotInfoWithData(TestMixins.GetWithDataMixin,
                                 OptionalParameterTestFixture):
  """Get DEFAULT_SLOT_VALUE with invalid data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DEFAULT_SLOT_VALUE'


class SetDefaultSlotInfo(TestMixins.UnsupportedSetMixin,
                         OptionalParameterTestFixture):
  """Set DEFAULT_SLOT_VALUE."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DEFAULT_SLOT_VALUE'


# Sensor Definition
#------------------------------------------------------------------------------
class GetSensorDefinition(OptionalParameterTestFixture):
  """Fetch all the sensor definitions."""
  CATEGORY = TestCategory.SENSORS
  PID = 'SENSOR_DEFINITION'
  REQUIRES = ['sensor_count']
  PROVIDES = ['sensor_definitions']
  MAX_SENSOR_INDEX = 0xfe

  PREDICATE_DICT = {
      '==': operator.eq,
      '<': operator.lt,
      '>': operator.gt,
  }

  def Test(self):
    self._sensors = {}  # stores the discovered sensors
    self._current_index = -1  # the current sensor we're trying to query
    self._sensor_holes = []  # indices of sensors that are missing
    self._CheckForSensor()

  def _MissingSensorWarning(self):
    max_sensor = max(self._sensors.keys())
    missing_sensors = [i for i in self._sensor_holes if i < max_sensor]
    if missing_sensors:
      self.AddWarning('Sensors missing in positions %s' % missing_sensors)

  def _CheckForSensor(self):
    if self.PidSupported():
      # If this pid is supported we attempt to locate all sensors
      if self._current_index == self.MAX_SENSOR_INDEX:
        if len(self._sensors) < self.Property('sensor_count'):
          self.AddWarning('Only found %d/%d sensors' %
                          (len(self._sensors), self.Property('sensor_count')))
        elif len(self._sensors) > self.Property('sensor_count'):
          self.AddWarning('Found too many %d/%d sensors' %
                          (len(self._sensors), self.Property('sensor_count')))

        self.SetProperty('sensor_definitions', self._sensors)
        self._MissingSensorWarning()
        self.Stop()
        return

      # For each message we should either see a NR_DATA_OUT_OF_RANGE or an ack
      self.AddExpectedResults([
        self.NackGetResult(RDMNack.NR_DATA_OUT_OF_RANGE,
                           action=self._AddToHoles),
        self.AckGetResult(action=self._CheckForSensor)
      ])
    else:
      # not supported, just check we get a NR_UNKNOWN_PID
      self.AddExpectedResults(self.NackGetResult(RDMNack.NR_UNKNOWN_PID))
      self.SetProperty('sensor_definitions', {})

    self._current_index += 1
    self.SendGet(ROOT_DEVICE, self.pid, [self._current_index])

  def _AddToHoles(self):
    self._sensor_holes.append(self._current_index)
    self._CheckForSensor()

  def VerifyResult(self, response, fields):
    if not response.WasAcked():
      return

    sensor_number = fields['sensor_number']
    if self._current_index != sensor_number:
      self.AddWarning(
          'Requested sensor %d, message returned sensor %d' %
          (self._current_index, fields['sensor_number']))
      return

    self._sensors[self._current_index] = fields

    # perform sanity checks on the sensor infomation
    if fields['type'] not in RDMConstants.SENSOR_TYPE_TO_NAME:
      self.AddWarning('Unknown type %d for sensor %d' %
                      (fields['type'], sensor_number))

    if fields['unit'] not in RDMConstants.UNIT_TO_NAME:
      self.AddWarning('Unknown unit %d for sensor %d' %
                      (fields['unit'], sensor_number))

    if fields['prefix'] not in RDMConstants.PREFIX_TO_NAME:
      self.AddWarning('Unknown prefix %d for sensor %d' %
                      (fields['prefix'], sensor_number))

    self.CheckCondition(sensor_number, fields, 'range_min', '>', 'range_max')
    self.CheckCondition(sensor_number, fields, 'range_min', '==', 'range_max')

    self.CheckCondition(sensor_number, fields, 'normal_min', '>', 'normal_max')
    self.CheckCondition(sensor_number, fields, 'normal_min', '==',
                        'normal_max')

    self.CheckCondition(sensor_number, fields, 'normal_min', '<', 'range_min')
    self.CheckCondition(sensor_number, fields, 'normal_max', '>', 'range_max')

    if fields['supports_recording'] & 0xfc:
      self.AddWarning('bits 7-2 in the recorded message support fields are set'
                      ' for sensor %d' % sensor_number)

  def CheckCondition(self, sensor_number, fields, lhs, predicate_str, rhs):
    """Check for a condition and add a warning if it isn't true."""
    predicate = self.PREDICATE_DICT[predicate_str]
    if predicate(fields[lhs], fields[rhs]):
      self.AddAdvisory(
          'Sensor %d, %s (%d) %s %s (%d)' %
          (sensor_number, lhs, fields[lhs], predicate_str, rhs, fields[rhs]))


class GetSensorDefinitionWithNoData(TestMixins.GetWithNoDataMixin,
                                    OptionalParameterTestFixture):
  """Get the sensor definition with no data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'SENSOR_DEFINITION'


class GetSensorDefinitionWithTooMuchData(OptionalParameterTestFixture):
  """Get the sensor definition with more than 1 byte of data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'SENSOR_DEFINITION'

  def Test(self):
    self.AddIfGetSupported(self.NackGetResult(RDMNack.NR_FORMAT_ERROR))
    self.SendRawGet(PidStore.ROOT_DEVICE, self.pid, 'foo')


class GetInvalidSensorDefinition(OptionalParameterTestFixture):
  """Get the sensor definition with the all sensor value (0xff)."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'SENSOR_DEFINITION'

  def Test(self):
    self.AddIfGetSupported(self.NackGetResult(RDMNack.NR_FORMAT_ERROR))
    data = struct.pack('!B', 0xff)
    self.SendRawGet(PidStore.ROOT_DEVICE, self.pid, data)


class SetSensorDefinition(TestMixins.UnsupportedSetMixin,
                          OptionalParameterTestFixture):
  """SET the sensor definition."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'SENSOR_DEFINITION'


# Sensor Value
#------------------------------------------------------------------------------
class GetSensorValues(OptionalParameterTestFixture):
  """Get values for all defined sensors."""
  CATEGORY = TestCategory.SENSORS
  PID = 'SENSOR_VALUE'
  REQUIRES = ['sensor_definitions']
  PROVIDES = ['sensor_values']

  HIGHEST_LOWEST_MASK = 0x02
  RECORDED_VALUE_MASK = 0x01

  def Test(self):
    # the head of the list is the current sensor we're querying
    self._sensors = self.Property('sensor_definitions').values()
    self._sensor_values = []

    if self._sensors:
      # loop and get all values
      self._GetSensorValue()
    else:
      # no sensors found, make sure we get a NR_DATA_OUT_OF_RANGE
      self.AddIfGetSupported(self.NackGetResult(RDMNack.NR_DATA_OUT_OF_RANGE))
      self.SendGet(ROOT_DEVICE, self.pid, [0])

  def _GetSensorValue(self):
    if not self._sensors:
      # finished
      self.SetProperty('sensor_values', self._sensor_values)
      self.Stop()
      return

    self.AddExpectedResults(self.AckGetResult(action=self._GetNextSensor))
    self.SendGet(ROOT_DEVICE, self.pid, [self._sensors[0]['sensor_number']])

  def _GetNextSensor(self):
    self._sensors.pop(0)
    self._GetSensorValue()

  def VerifyResult(self, response, fields):
    if not response.WasAcked():
      return

    sensor_def = self._sensors[0]
    sensor_number = fields['sensor_number']
    if sensor_def['sensor_number'] != sensor_number:
      self.AddWarning(
          'Requested sensor value for %d, message returned sensor %d' %
          (sensor_def['sensor_number'], fields['sensor_number']))
      return

    self._sensor_values.append(fields)
    range_min = sensor_def['range_min']
    range_max = sensor_def['range_max']

    # perform sanity checks on the sensor infomation
    self._CheckValueWithinRange(sensor_number, fields, 'present_value',
                                range_min, range_max)

    if sensor_def['supports_recording'] & self.HIGHEST_LOWEST_MASK:
      self._CheckValueWithinRange(sensor_number, fields, 'lowest',
                                  range_min, range_max)
      self._CheckValueWithinRange(sensor_number, fields, 'highest',
                                  range_min, range_max)
    else:
      self._CheckForZeroField(sensor_number, fields, 'lowest')
      self._CheckForZeroField(sensor_number, fields, 'highest')

    if sensor_def['supports_recording'] & self.RECORDED_VALUE_MASK:
      self._CheckValueWithinRange(sensor_number, fields, 'recorded',
                                  range_min, range_max)
    else:
      self._CheckForZeroField(sensor_number, fields, 'recorded')

  def _CheckValueWithinRange(self, sensor_number, fields, name, min, max):
    if fields[name] < min or fields[name] > max:
      self.AddWarning(
        '%s for sensor %d not within range %d - %d, was %d' %
        (name, sensor_number, min, max, fields[name]))

  def _CheckForZeroField(self, sensor_number, fields, name):
    if fields[name]:
      self.AddWarning(
        '%s value for sensor %d non-0, but support not declared, was %d' %
        (name, sensor_number, fields[name]))


class GetUndefinedSensorValues(OptionalParameterTestFixture):
  """Attempt to get sensor values for all sensors that weren't defined."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'SENSOR_VALUE'
  REQUIRES = ['sensor_definitions']

  def Test(self):
    sensors = self.Property('sensor_definitions')
    self._missing_sensors = []
    for i in xrange(0, 0xff):
      if i not in sensors:
        self._missing_sensors.append(i)

    if self._missing_sensors:
      # loop and get all values
      self._GetSensorValue()
    else:
      self.SetNotRun(' All sensors declared')
      self.Stop()
      return

  def _GetSensorValue(self):
    if not self._missing_sensors:
      self.Stop()
      return

    self.AddIfGetSupported(
        self.NackGetResult(RDMNack.NR_DATA_OUT_OF_RANGE,
                           action=self._GetSensorValue))
    self.SendGet(ROOT_DEVICE, self.pid, [self._missing_sensors.pop(0)])


class GetInvalidSensorValue(OptionalParameterTestFixture):
  """Get the sensor value with the all sensor value (0xff)."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'SENSOR_VALUE'

  def Test(self):
    self.AddIfGetSupported(self.NackGetResult(RDMNack.NR_FORMAT_ERROR))
    data = struct.pack('!B', 0xff)
    self.SendRawGet(PidStore.ROOT_DEVICE, self.pid, data)


class GetSensorValueWithNoData(TestMixins.GetWithNoDataMixin,
                               OptionalParameterTestFixture):
  """GET sensor value without any sensor number."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'SENSOR_VALUE'


class ResetSensorValue(OptionalParameterTestFixture):
  """Reset sensor values for all defined sensors."""
  CATEGORY = TestCategory.SENSORS
  PID = 'SENSOR_VALUE'
  REQUIRES = ['sensor_definitions']

  def Test(self):
    # the head of the list is the current sensor we're querying
    self._sensors = self.Property('sensor_definitions').values()
    self._sensor_values = []

    if self._sensors:
      # loop and get all values
      self._ResetSensor()
    else:
      # no sensors found, make sure we get a NR_DATA_OUT_OF_RANGE
      self.AddIfSetSupported(self.NackSetResult(RDMNack.NR_DATA_OUT_OF_RANGE))
      self.SendSet(ROOT_DEVICE, self.pid, [0])

  def _ResetSensor(self):
    if not self._sensors:
      # finished
      self.Stop()
      return

    self.AddExpectedResults(self.AckSetResult(action=self._ResetNextSensor))
    self.SendSet(ROOT_DEVICE, self.pid, [self._sensors[0]['sensor_number']])

  def _ResetNextSensor(self):
    self._sensors.pop(0)
    self._ResetSensor()

  def VerifyResult(self, response, fields):
    # It's not clear at all what to expect in this case.
    # See http://www.rdmprotocol.org/showthread.php?p=2160
    # TODO(simonn, e1.20 task group): figure this out
    pass


class ResetAllSensorValues(OptionalParameterTestFixture):
  """Set SENSOR_VALUE with sensor number set to 0xff."""
  CATEGORY = TestCategory.SENSORS
  PID = 'SENSOR_VALUE'
  REQUIRES = ['sensor_definitions']

  RECORDED_VALUE_MASK = 0x01
  ALL_SENSORS = 0xff

  def Test(self):
    supports_recording = False
    for sensor_def in self.Property('sensor_definitions').values():
      supports_recording |= (
          sensor_def['supports_recording'] & self.RECORDED_VALUE_MASK)

    if supports_recording:
      self.AddIfSetSupported(self.AckSetResult())
    else:
      self.AddIfSetSupported(self.NackSetResult(RDMNack.NR_DATA_OUT_OF_RANGE))
    self.SendSet(ROOT_DEVICE, self.pid, [self.ALL_SENSORS])


class ResetUndefinedSensorValues(TestMixins.SetUndefinedSensorValues,
                                 OptionalParameterTestFixture):
  """Attempt to reset sensor values for all sensors that weren't defined."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'SENSOR_VALUE'
  REQUIRES = ['sensor_definitions']


class ResetSensorValueWithNoData(TestMixins.SetWithNoDataMixin,
                                 OptionalParameterTestFixture):
  """SET sensor value without any sensor number."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'SENSOR_VALUE'


# Record Sensors
#------------------------------------------------------------------------------
class RecordSensorValues(OptionalParameterTestFixture):
  """Record values for all defined sensors."""
  CATEGORY = TestCategory.SENSORS
  PID = 'RECORD_SENSORS'
  REQUIRES = ['sensor_definitions']

  RECORDED_VALUE_MASK = 0x01

  def Test(self):
    # the head of the list is the current sensor we're querying
    self._sensors = self.Property('sensor_definitions').values()
    self._sensor_values = []

    if self._sensors:
      # loop and get all values
      self._RecordSensor()
    else:
      # no sensors found, make sure we get a NR_DATA_OUT_OF_RANGE
      self.AddIfSetSupported(self.NackSetResult(RDMNack.NR_DATA_OUT_OF_RANGE))
      self.SendSet(ROOT_DEVICE, self.pid, [0])

  def _RecordSensor(self):
    if not self._sensors:
      # finished
      self.Stop()
      return

    sensor_def = self._sensors[0]
    if sensor_def['supports_recording'] & self.RECORDED_VALUE_MASK:
      self.AddExpectedResults(self.AckSetResult(action=self._RecordNextSensor))
    else:
      self.AddIfSetSupported(
          self.NackSetResult(RDMNack.NR_DATA_OUT_OF_RANGE,
                             action=self._RecordNextSensor))
    self.SendSet(ROOT_DEVICE, self.pid, [self._sensors[0]['sensor_number']])

  def _RecordNextSensor(self):
    self._sensors.pop(0)
    self._RecordSensor()


class RecordAllSensorValues(OptionalParameterTestFixture):
  """Set RECORD_SENSORS with sensor number set to 0xff."""
  CATEGORY = TestCategory.SENSORS
  PID = 'RECORD_SENSORS'
  REQUIRES = ['sensor_definitions']

  RECORDED_VALUE_MASK = 0x01
  ALL_SENSORS = 0xff

  def Test(self):
    supports_recording = False
    for sensor_def in self.Property('sensor_definitions').values():
      supports_recording |= (
          sensor_def['supports_recording'] & self.RECORDED_VALUE_MASK)

    if supports_recording:
      self.AddIfSetSupported(self.AckSetResult())
    else:
      self.AddIfSetSupported(self.NackSetResult(RDMNack.NR_DATA_OUT_OF_RANGE))
    self.SendSet(ROOT_DEVICE, self.pid, [self.ALL_SENSORS])


class RecordUndefinedSensorValues(TestMixins.SetUndefinedSensorValues,
                                  OptionalParameterTestFixture):
  """Attempt to reset sensor values for all sensors that weren't defined."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'RECORD_SENSORS'
  REQUIRES = ['sensor_definitions']


class RecordSensorValueWithNoData(TestMixins.SetWithNoDataMixin,
                                  OptionalParameterTestFixture):
  """SET record sensors without any sensor number."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'RECORD_SENSORS'


# Device Hours
#------------------------------------------------------------------------------
class GetDeviceHours(TestMixins.GetMixin, OptionalParameterTestFixture):
  """GET the device hours."""
  CATEGORY = TestCategory.POWER_LAMP_SETTINGS
  PID = 'DEVICE_HOURS'
  EXPECTED_FIELD = 'hours'
  PROVIDES = ['device_hours']


class GetDeviceHoursWithData(TestMixins.GetWithDataMixin,
                             OptionalParameterTestFixture):
  """GET the device hours with extra data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DEVICE_HOURS'


class SetDeviceHours(TestMixins.SetUInt32Mixin,
                     OptionalParameterTestFixture):
  """Attempt to SET the device hours."""
  CATEGORY = TestCategory.POWER_LAMP_SETTINGS
  PID = 'DEVICE_HOURS'
  EXPECTED_FIELD = 'hours'
  REQUIRES = ['device_hours']

  def OldValue(self):
    return self.Property('device_hours')


class SetDeviceHoursWithNoData(TestMixins.SetWithNoDataMixin,
                               OptionalParameterTestFixture):
  """Set the device hours with no param data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DEVICE_HOURS'


# Lamp Hours
#------------------------------------------------------------------------------
class GetLampHours(TestMixins.GetMixin, OptionalParameterTestFixture):
  """GET the device hours."""
  CATEGORY = TestCategory.POWER_LAMP_SETTINGS
  PID = 'LAMP_HOURS'
  EXPECTED_FIELD = 'hours'
  PROVIDES = ['lamp_hours']


class GetLampHoursWithData(TestMixins.GetWithDataMixin,
                           OptionalParameterTestFixture):
  """GET the device hours with extra data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'LAMP_HOURS'


class SetLampHours(TestMixins.SetUInt32Mixin,
                   OptionalParameterTestFixture):
  """Attempt to SET the device hours."""
  CATEGORY = TestCategory.POWER_LAMP_SETTINGS
  PID = 'LAMP_HOURS'
  EXPECTED_FIELD = 'hours'
  REQUIRES = ['lamp_hours']

  def OldValue(self):
    return self.Property('lamp_hours')


class SetLampHoursWithNoData(TestMixins.SetWithNoDataMixin,
                             OptionalParameterTestFixture):
  """Set the device hours with no param data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'LAMP_HOURS'


# Lamp Strikes
#------------------------------------------------------------------------------
class GetLampStrikes(TestMixins.GetMixin, OptionalParameterTestFixture):
  """GET the lamp strikes."""
  CATEGORY = TestCategory.POWER_LAMP_SETTINGS
  PID = 'LAMP_STRIKES'
  EXPECTED_FIELD = 'strikes'
  PROVIDES = ['lamp_strikes']


class GetLampStrikesWithData(TestMixins.GetWithDataMixin,
                             OptionalParameterTestFixture):
  """GET the lamp strikes with extra data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'LAMP_STRIKES'


class SetLampStrikes(TestMixins.SetUInt32Mixin, OptionalParameterTestFixture):
  """Attempt to SET the lamp strikes."""
  CATEGORY = TestCategory.POWER_LAMP_SETTINGS
  PID = 'LAMP_STRIKES'
  EXPECTED_FIELD = 'strikes'
  REQUIRES = ['lamp_strikes']

  def OldValue(self):
    return self.Property('lamp_strikes')


class SetLampStrikesWithNoData(TestMixins.SetWithNoDataMixin,
                               OptionalParameterTestFixture):
  """Set the lamp strikes with no param data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'LAMP_STRIKES'


# Lamp State
#------------------------------------------------------------------------------
class GetLampState(TestMixins.GetMixin, OptionalParameterTestFixture):
  """GET the lamp state."""
  CATEGORY = TestCategory.POWER_LAMP_SETTINGS
  PID = 'LAMP_STATE'
  EXPECTED_FIELD = 'state'
  PROVIDES = ['lamp_state']


class GetLampStateWithData(TestMixins.GetWithDataMixin,
                           OptionalParameterTestFixture):
  """GET the lamp state with extra data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'LAMP_STATE'


class SetLampState(TestMixins.SetBoolMixin, OptionalParameterTestFixture):
  """Attempt to SET the lamp state."""
  CATEGORY = TestCategory.POWER_LAMP_SETTINGS
  PID = 'LAMP_STATE'
  EXPECTED_FIELD = 'state'
  REQUIRES = ['lamp_state']

  def OldValue(self):
    # We use a bool here so we toggle between off and on
    # Some responders may not support standby & strike
    return bool(self.Property('lamp_state'))


class SetLampStateWithNoData(TestMixins.SetWithNoDataMixin,
                               OptionalParameterTestFixture):
  """Set the device state with no param data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'LAMP_STATE'


# Lamp On Mode
#------------------------------------------------------------------------------
class GetLampOnMode(TestMixins.GetMixin, OptionalParameterTestFixture):
  """GET the lamp on mode."""
  CATEGORY = TestCategory.POWER_LAMP_SETTINGS
  PID = 'LAMP_ON_MODE'
  EXPECTED_FIELD = 'mode'
  PROVIDES = ['lamp_on_mode']


class GetLampOnModeWithData(TestMixins.GetWithDataMixin,
                            OptionalParameterTestFixture):
  """GET the lamp on mode with extra data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'LAMP_ON_MODE'


class SetLampOnMode(TestMixins.SetUInt8Mixin, OptionalParameterTestFixture):
  """Attempt to SET the lamp on mode."""
  CATEGORY = TestCategory.POWER_LAMP_SETTINGS
  PID = 'LAMP_ON_MODE'
  EXPECTED_FIELD = 'mode'
  REQUIRES = ['lamp_on_mode']
  ALLOWED_MODES = [0, 1, 2]

  def OldValue(self):
    return self.Property('lamp_on_mode')

  def NewValue(self):
    old_value = self.OldValue()
    try:
      index = self.ALLOWED_MODES.index(old_value)
    except ValueError:
      return self.ALLOWED_MODES[0]
    return self.ALLOWED_MODES[(old_value + 1) % len(self.ALLOWED_MODES)]


class SetLampOnModeWithNoData(TestMixins.SetWithNoDataMixin,
                              OptionalParameterTestFixture):
  """Set the device on mode with no param data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'LAMP_ON_MODE'


# Device Hours
#------------------------------------------------------------------------------
class GetDevicePowerCycles(TestMixins.GetMixin, OptionalParameterTestFixture):
  """GET the device power_cycles."""
  CATEGORY = TestCategory.POWER_LAMP_SETTINGS
  PID = 'DEVICE_POWER_CYCLES'
  EXPECTED_FIELD = 'power_cycles'
  PROVIDES = ['power_cycles']


class GetDevicePowerCyclesWithData(TestMixins.GetWithDataMixin,
                                   OptionalParameterTestFixture):
  """GET the device power_cycles with extra data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DEVICE_POWER_CYCLES'


class SetDevicePowerCycles(TestMixins.SetUInt32Mixin,
                           OptionalParameterTestFixture):
  """Attempt to SET the device power_cycles."""
  CATEGORY = TestCategory.POWER_LAMP_SETTINGS
  PID = 'DEVICE_POWER_CYCLES'
  EXPECTED_FIELD = 'power_cycles'
  REQUIRES = ['power_cycles']

  def OldValue(self):
    return self.Property('power_cycles')


class SetDevicePowerCyclesWithNoData(TestMixins.SetWithNoDataMixin,
                                     OptionalParameterTestFixture):
  """Set the device power_cycles with no param data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DEVICE_POWER_CYCLES'


# Display Invert
#------------------------------------------------------------------------------
class GetDisplayInvert(TestMixins.GetMixin,
                       OptionalParameterTestFixture):
  """GET the display invert setting."""
  CATEGORY = TestCategory.DISPLAY_SETTINGS
  PID = 'DISPLAY_INVERT'
  EXPECTED_FIELD = 'invert_status'
  PROVIDES = ['display_invert']


class GetDisplayInvertWithData(TestMixins.GetWithDataMixin,
                               OptionalParameterTestFixture):
  """GET the pan invert setting with extra data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DISPLAY_INVERT'


class SetDisplayInvert(TestMixins.SetUInt8Mixin,
                       OptionalParameterTestFixture):
  """Attempt to SET the display invert setting."""
  CATEGORY = TestCategory.DISPLAY_SETTINGS
  PID = 'DISPLAY_INVERT'
  EXPECTED_FIELD = 'invert'
  REQUIRES = ['display_invert']
  ALLOWED_MODES = [0, 1, 2]

  def OldValue(self):
    return self.Property('display_invert')

  def NewValue(self):
    old_value = self.OldValue()
    try:
      index = self.ALLOWED_MODES.index(old_value)
    except ValueError:
      return self.ALLOWED_MODES[0]
    return self.ALLOWED_MODES[(old_value + 1) % len(self.ALLOWED_MODES)]


class SetDisplayInvertWithNoData(TestMixins.SetWithNoDataMixin,
                                 OptionalParameterTestFixture):
  """Set the display invert with no param data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DISPLAY_INVERT'


# Display Level
#------------------------------------------------------------------------------
class GetDisplayLevel(TestMixins.GetMixin,
                      OptionalParameterTestFixture):
  """GET the display level setting."""
  CATEGORY = TestCategory.DISPLAY_SETTINGS
  PID = 'DISPLAY_LEVEL'
  EXPECTED_FIELD = 'level'
  PROVIDES = ['display_level']


class GetDisplayLevelWithData(TestMixins.GetWithDataMixin,
                              OptionalParameterTestFixture):
  """GET the pan invert setting with extra data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DISPLAY_LEVEL'


class SetDisplayLevel(TestMixins.SetUInt8Mixin,
                      OptionalParameterTestFixture):
  """Attempt to SET the display level setting."""
  CATEGORY = TestCategory.DISPLAY_SETTINGS
  PID = 'DISPLAY_LEVEL'
  EXPECTED_FIELD = 'level'
  REQUIRES = ['display_level']

  def OldValue(self):
    return self.Property('display_level')


class SetDisplayLevelWithNoData(TestMixins.SetWithNoDataMixin,
                                OptionalParameterTestFixture):
  """Set the display level with no param data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DISPLAY_LEVEL'


# Pan Invert
#------------------------------------------------------------------------------
class GetPanInvert(TestMixins.GetMixin, OptionalParameterTestFixture):
  """GET the pan invert setting."""
  CATEGORY = TestCategory.CONFIGURATION
  PID = 'PAN_INVERT'
  EXPECTED_FIELD = 'invert'
  PROVIDES = ['pan_invert']


class GetPanInvertWithData(TestMixins.GetWithDataMixin,
                           OptionalParameterTestFixture):
  """GET the pan invert setting with extra data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'PAN_INVERT'


class SetPanInvert(TestMixins.SetBoolMixin, OptionalParameterTestFixture):
  """Attempt to SET the pan invert setting."""
  CATEGORY = TestCategory.CONFIGURATION
  PID = 'PAN_INVERT'
  EXPECTED_FIELD = 'invert'
  REQUIRES = ['pan_invert']

  def OldValue(self):
    return self.Property('pan_invert')


class SetPanInvertWithNoData(TestMixins.SetWithNoDataMixin,
                             OptionalParameterTestFixture):
  """Set the pan invert with no param data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'PAN_INVERT'


# Tilt Invert
#------------------------------------------------------------------------------
class GetTiltInvert(TestMixins.GetMixin, OptionalParameterTestFixture):
  """GET the tilt invert setting."""
  CATEGORY = TestCategory.CONFIGURATION
  PID = 'TILT_INVERT'
  EXPECTED_FIELD = 'invert'
  PROVIDES = ['tilt_invert']


class GetTiltInvertWithData(TestMixins.GetWithDataMixin,
                            OptionalParameterTestFixture):
  """GET the tilt invert setting with extra data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'TILT_INVERT'


class SetTiltInvert(TestMixins.SetBoolMixin, OptionalParameterTestFixture):
  """Attempt to SET the tilt invert setting."""
  CATEGORY = TestCategory.CONFIGURATION
  PID = 'TILT_INVERT'
  EXPECTED_FIELD = 'invert'
  REQUIRES = ['tilt_invert']

  def OldValue(self):
    return self.Property('tilt_invert')


class SetTiltInvertWithNoData(TestMixins.SetWithNoDataMixin,
                              OptionalParameterTestFixture):
  """Set the tilt invert with no param data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'TILT_INVERT'


# Pan Tilt Swap Invert
#------------------------------------------------------------------------------
class GetPanTiltSwap(TestMixins.GetMixin, OptionalParameterTestFixture):
  """GET the pan tilt swap setting."""
  CATEGORY = TestCategory.CONFIGURATION
  PID = 'PAN_TILT_SWAP'
  EXPECTED_FIELD = 'swap'
  PROVIDES = ['pan_tilt_swap']


class GetPanTiltSwapWithData(TestMixins.GetWithDataMixin,
                             OptionalParameterTestFixture):
  """GET the pan tilt swap setting with extra data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'PAN_TILT_SWAP'


class SetPanTiltSwap(TestMixins.SetBoolMixin, OptionalParameterTestFixture):
  """Attempt to SET the pan tilt swap setting."""
  CATEGORY = TestCategory.CONFIGURATION
  PID = 'PAN_TILT_SWAP'
  EXPECTED_FIELD = 'swap'
  REQUIRES = ['pan_tilt_swap']

  def OldValue(self):
    return self.Property('pan_tilt_swap')


class SetPanTiltSwapWithNoData(TestMixins.SetWithNoDataMixin,
                               OptionalParameterTestFixture):
  """Set the pan tilt swap with no param data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'PAN_TILT_SWAP'


# Real time clock
#------------------------------------------------------------------------------
class GetRealTimeClock(OptionalParameterTestFixture):
  """GET the real time clock setting."""
  CATEGORY = TestCategory.CONFIGURATION
  PID = 'REAL_TIME_CLOCK'

  ALLOWED_RANGES = {
      'year': (2003, 65535),
      'month': (1, 12),
      'day': (1, 31),
      'hour': (0, 23),
      'minute': (0, 59),
  }

  def Test(self):
    self.AddIfGetSupported(
      self.AckGetResult(field_names=self.ALLOWED_RANGES.keys() + ['second']))
    self.SendGet(ROOT_DEVICE, self.pid)

  def VerifyResult(self, response, fields):
    if not response.WasAcked():
      return

    for field, range in self.ALLOWED_RANGES.iteritems():
      value = fields[field]
      if value < range[0] or value > range[1]:
        self.AddWarning('%s in GET %s is out of range, was %d, expeced %s' %
                        (field, self.PID, value, range))


class GetRealTimeClockWithData(TestMixins.GetWithDataMixin,
                               OptionalParameterTestFixture):
  """GET the teal time clock with data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'REAL_TIME_CLOCK'


class SetRealTimeClock(OptionalParameterTestFixture):
  """Set the real time clock."""
  CATEGORY = TestCategory.CONFIGURATION
  PID = 'REAL_TIME_CLOCK'

  def Test(self):
    n = datetime.datetime.now()
    self.AddIfSetSupported(self.AckSetResult())
    args = [n.year, n.month, n.day, n.hour, n.minute, n.second]
    self.SendSet(ROOT_DEVICE, self.pid,
                 args)


class SetRealTimeClockWithNoData(TestMixins.SetWithNoDataMixin,
                                 OptionalParameterTestFixture):
  """Set the real time clock without any data."""
  CATEGORY = TestCategory.CONFIGURATION
  PID = 'REAL_TIME_CLOCK'


# Identify Device
#------------------------------------------------------------------------------
class GetIdentifyDevice(TestMixins.GetRequiredMixin, ResponderTestFixture):
  """Get the identify mode."""
  CATEGORY = TestCategory.CONTROL
  PID = 'IDENTIFY_DEVICE'
  PROVIDES = ['identify_state']
  EXPECTED_FIELD = 'identify_state'


class GetIdentifyDeviceWithData(ResponderTestFixture):
  """Get the identify mode with data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'IDENTIFY_DEVICE'

  def Test(self):
    # don't inherit from GetWithDataMixin because this is required
    self.AddExpectedResults(self.NackGetResult(RDMNack.NR_FORMAT_ERROR))
    self.SendRawGet(ROOT_DEVICE, self.pid, 'foo')


class SetIdentifyDevice(ResponderTestFixture):
  """Set the identify mode."""
  CATEGORY = TestCategory.CONTROL
  PID = 'IDENTIFY_DEVICE'
  REQUIRES = ['identify_state']

  def Test(self):
    self.identify_mode = self.Property('identify_state')
    self.new_mode = not self.identify_mode

    self.AddExpectedResults(self.AckSetResult(action=self.VerifyIdentifyMode))
    self.SendSet(ROOT_DEVICE, self.pid, [self.new_mode])

  def VerifyIdentifyMode(self):
    self.AddExpectedResults(self.AckGetResult(
        field_values={'identify_state': self.new_mode},
        action=self.ResetMode))
    self.SendGet(ROOT_DEVICE, self.pid)

  def ResetMode(self):
    self.AddExpectedResults(self.AckSetResult())
    self.SendSet(ROOT_DEVICE, self.pid, [self.identify_mode])


class SetIdentifyDeviceWithNoData(ResponderTestFixture):
  """Set the identify mode with no data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'IDENTIFY_DEVICE'

  def Test(self):
    self.AddExpectedResults(self.NackSetResult(RDMNack.NR_FORMAT_ERROR))
    self.SendRawSet(ROOT_DEVICE, self.pid, '')


# Power State
#------------------------------------------------------------------------------
class GetPowerState(TestMixins.GetMixin, OptionalParameterTestFixture):
  """Get the power state mode."""
  CATEGORY = TestCategory.CONTROL
  PID = 'POWER_STATE'
  PROVIDES = ['power_state']
  EXPECTED_FIELD = 'power_state'

  # The allowed power states
  ALLOWED_STATES = [0, 1, 2, 0xff]

  def VerifyResult(self, response, fields):
    super(GetPowerState, self).VerifyResult(response, fields)
    if response.WasAcked():
      if fields['power_state'] not in self.ALLOWED_STATES:
        self.AddWarning('Power state of 0x%hx is not defined' %
                        fields['power_state'])


class GetPowerStateWithData(TestMixins.GetWithDataMixin,
                            OptionalParameterTestFixture):
  """Get the power state mode with data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'POWER_STATE'


class SetPowerState(TestMixins.SetUInt8Mixin, OptionalParameterTestFixture):
  """Set the power state."""
  CATEGORY = TestCategory.CONTROL
  PID = 'POWER_STATE'
  REQUIRES = ['power_state']
  EXPECTED_FIELD = 'power_state'

  def OldValue(self):
    return self.Property('power_state')

  def NewValue(self):
    old_value = self.Property('power_state')
    try:
      index = GetPowerState.ALLOWED_STATES.index(old_value)
    except ValueError:
      return GetPowerState.ALLOWED_STATES[0]

    length = len(GetPowerState.ALLOWED_STATES)
    return GetPowerState.ALLOWED_STATES[(old_value + 1) % length]

  def ResetState(self):
    if not self.OldValue():
      return

    # reset back to the old value
    self.SendSet(ROOT_DEVICE, self.pid, [self.OldValue()])
    self._wrapper.Run()


class SetPowerStateWithNoData(TestMixins.SetWithNoDataMixin,
                              OptionalParameterTestFixture):
  """Set the power state with no data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'POWER_STATE'


# Self Test
#------------------------------------------------------------------------------
class GetPerformSelfTest(TestMixins.GetMixin, OptionalParameterTestFixture):
  """Get the current self test settings."""
  CATEGORY = TestCategory.CONTROL
  PID = 'PERFORM_SELF_TEST'
  EXPECTED_FIELD = 'tests_active'


class GetPerformSelfTestWithData(TestMixins.GetWithDataMixin,
                                 OptionalParameterTestFixture):
  """Get the current self test settings with extra data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'PERFORM_SELF_TEST'


class SetPerformSelfTest(TestMixins.SetUInt8Mixin,
                         OptionalParameterTestFixture):
  """Turn any running self tests off."""
  CATEGORY = TestCategory.CONTROL
  PID = 'PERFORM_SELF_TEST'
  EXPECTED_FIELD = 'tests_active'

  def NewValue(self):
    return False

class SetPerformSelfTestWithNoData(TestMixins.SetWithNoDataMixin,
                                   OptionalParameterTestFixture):
  """Set the perform self test setting but don't provide any data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'PERFORM_SELF_TEST'


# Self Test Description
#------------------------------------------------------------------------------
class GetSelfTestDescription(OptionalParameterTestFixture):
  """Get the self test description."""
  CATEGORY = TestCategory.CONTROL
  PID = 'SELF_TEST_DESCRIPTION'

  def Test(self):
    self.AddIfGetSupported([
      self.AckGetResult(),
      self.NackGetResult(RDMNack.NR_DATA_OUT_OF_RANGE),
    ])
    # try to get a description for the first self test
    self.SendGet(PidStore.ROOT_DEVICE, self.pid, [1])


class GetSelfTestDescriptionWithNoData(TestMixins.GetWithNoDataMixin,
                                       OptionalParameterTestFixture):
  """Get the self test description with no data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'SELF_TEST_DESCRIPTION'


class FindSelfTests(OptionalParameterTestFixture):
  """Locate the self tests by sending SELF_TEST_DESCRIPTION messages."""
  CATEGORY = TestCategory.CONTROL
  PID = 'SELF_TEST_DESCRIPTION'
  PROVIDES = ['self_test_descriptions']

  def Test(self):
    self._self_tests = {}  # stores the discovered self tests
    self._current_index = 0  # the current self test we're trying to query
    self._CheckForSelfTest()

  def _CheckForSelfTest(self):
    # For each message we should either see a NR_DATA_OUT_OF_RANGE or an ack
    if self._current_index == 255:
      self.SetProperty('self_test_descriptions', self._self_tests)
      self.Stop()
      return

    if self.PidSupported():
      self.AddExpectedResults([
        self.NackGetResult(RDMNack.NR_DATA_OUT_OF_RANGE,
                           action=self._CheckForSelfTest),
        self.AckGetResult(action=self._CheckForSelfTest)
      ])
    else:
      self.AddExpectedResults(self.NackGetResult(RDMNack.NR_UNKNOWN_PID))

    self._current_index += 1
    self.SendGet(ROOT_DEVICE, self.pid, [self._current_index])

  def VerifyResult(self, response, fields):
    if response.WasAcked():
      if self._current_index != fields['test_number']:
        self.AddWarning(
            'Requested self test %d, message returned self test %d' %
            (self._current_index, fields['test_number']))
      else:
        self._self_tests[self._current_index] = fields['description']
