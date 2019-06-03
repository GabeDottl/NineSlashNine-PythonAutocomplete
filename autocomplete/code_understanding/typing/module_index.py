'''This module is used for caching modules.'''

import attr
import h5py

from . import module_loader
from .errors import AmbiguousFuzzyValueError
from .language_objects import Function, Instance, Klass, ModuleImpl
from .pobjects import FuzzyObject, pobject_from_object


@attr.s
class ModuleIndex:
  filename = attr.ib()

  def __attrs_post_init__(self):
    self.file = h5py.File(self.filename, 'w')

  def store_module(self, module):
    module_store = self.file.create_group(path_from_dot_name(module.name))
    for key, value in module.get_members().items():
      self.add_hdf_value_from_pobject(module_store, key, value)

    module_store.attrs['filename'] = module.filename
    module_store.attrs['_is_package'] = module._is_package

  def add_hdf_value_from_pobject(self, group, name, pobject):
    try:
      value = pobject.value()
    except AmbiguousFuzzyValueError:
      pass
    # FuzzyObject is ambiguous - just YOLO and make empty.
    if isinstance(value, FuzzyObject):
      ds = group.self.file.create_dataset(name, data=h5py.Empty('f'))
      ds.attrs['type'] = 'Unknown'
      return ds
    if isinstance(value, Klass):
      return self.add_hdf_value_from_klass(group, name, value)
    if isinstance(value, Instance):
      return self.add_hdf_value_from_instance(group, name, value)
    if isinstance(value, Function):
      return self.add_hdf_value_from_function(group, name, value)
    return self.add_hdf_value_from_native_object(group, name, value)

  def add_hdf_value_from_klass(self, group, name, klass):
    klass_group = group.create_group(basename(klass.name))
    for key, member in klass_group.items():
      self.add_hdf_value_from_pobject(key, member)

  def add_hdf_value_from_instance(self, group, name, value):
    pass

  def add_hdf_value_from_function(self, group, name, value):
    pass

  def add_hdf_value_from_native_object(self, group, name, value):
    pass

  def has_module(self, name):
    return path_from_dot_name(name) in self.file

  def retrieve_module(self, name):
    module_store = self.file[path_from_dot_name(name)]
    members = members_from_group(module_store)

    return ModuleImpl(name,
                      filename=module_store.attrs['filename'],
                      is_package=module_store.attrs['_is_package'],
                      members=members,
                      module_loader=module_loader)


def members_from_group(group):
  out = {}
  for key, value in group.items():
    out[key] = pobject_from_value(value)

  for key, value in group.attrs.items():
    out[key] = pobject_from_attr(value)

  return out


def pobject_from_attr(value):
  return pobject_from_object(value)


def pobject_from_value(value):
  # if value.attrs['type'] == 'Unknown':
  #   return UnknownObject('')
  # if value.attrs['type'] == 'Klass':
  #   return Klass(dot_name_from_path(value.name), members_from_group(value))
  # if value.attrs['type'] == 'Instance':
  #   return Instance(dot_name_from_path(value.name), members_from_group(value))

  raise ValueError(value)


# module_store = h5py.File('module_store.hdf5', 'w')
# module_group = module.name.replace('.', '/'))

#     value_dataset = module_group[key] =
#     value_dataset.attrs['type'] = str(type(value))


def dot_name_from_path(path):
  return path[1:].replace('/', '.')


def path_from_dot_name(name):
  return name.replace('.', '/')


def basename(name):
  try:
    return name[name.rindex('.') + 1:]
  except:
    return name
