import os
import sys
from functools import partial
from itertools import chain
from typing import Dict, List, Union
from time import time

import attr
from isort import SortImports

from ....nsn_logging import info, warning
from .. import api, module_loader, refactor, symbol_context, symbol_index, pobjects, errors
from ..control_flow_graph_nodes import FromImportCfgNode, ImportCfgNode
from . import find_missing_symbols
from .update_history_tracker import UpdateHistoryTracker


def fix_missing_symbols_in_file(filename, index, write=True, remove_extra_imports=True, sort_imports=True):
  with open(filename) as f:
    source = ''.join(f.readlines())
  new_code, changed = fix_missing_symbols_in_source(source,
                                                    filename=filename,
                                                    index=index,
                                                    remove_extra_imports=remove_extra_imports)
  if write and changed:
    with open(filename, 'w') as f:
      f.writelines(new_code)
  return new_code, changed


def fix_missing_symbols_in_source(source, filename, index, remove_extra_imports=True,
                                  sort_imports=True) -> str:
  source_dir = os.path.dirname(filename)
  graph = api.graph_from_source(source, filename, parso_default=True)
  existing_global_imports = list(
      graph.get_descendents_of_types((ImportCfgNode, FromImportCfgNode), recursive=False))
  if remove_extra_imports:
    stripped_graph = graph.strip_descendents_of_types((FromImportCfgNode, ImportCfgNode), recursive=False)
    missing_symbols = find_missing_symbols.scan_missing_symbols_in_graph(stripped_graph,
                                                                         source_dir,
                                                                         skip_wild_cards=True)
  else:
    missing_symbols = find_missing_symbols.scan_missing_symbols_in_graph(graph, source_dir)

  changes = {}

  uht = UpdateHistoryTracker.load(os.path.join(os.getenv('HOME'), 'fix_code_updates.csv'))
  timestamp = time()

  def get_change(node):
    module_key = node.get_module_key()
    if module_key in changes:
      return changes[(module_key, id(node))]
    out = changes[(module_key, id(node))] = refactor.Change(node, [], [])
    return out

  if remove_extra_imports:
    for import_node in existing_global_imports:
      if isinstance(import_node, ImportCfgNode):
        symbol_name = import_node.as_name if import_node.as_name else import_node.module_path
        if symbol_name in missing_symbols:
          continue
        else:
          info(f'module not used: {symbol_name}')
          uht.add_action(timestamp, 'remove', import_node.get_module_key(), filename)
          get_change(import_node).removals.append(symbol_name)
      else:  # FromImportCfgNode
        for from_import_name, as_name in import_node.from_import_name_alias_dict.items():
          if from_import_name == '*':
            get_change(import_node).removals.append(from_import_name)
            continue
          if as_name and as_name in missing_symbols:
            continue
          if not as_name and from_import_name in missing_symbols:
            continue
          info(f'from_import_name not used: {from_import_name}')
          get_change(import_node).removals.append(from_import_name)
          uht.add_action(timestamp, 'remove', (from_import_name, import_node.get_module_key()), filename)
    # Recalculate missing symbols accounting for imports now that we've figured out what to remove
    missing_symbols = find_missing_symbols.scan_missing_symbols_in_graph(graph,
                                                                         source_dir,
                                                                         skip_wild_cards=True)

  if missing_symbols:
    info(f'missing_symbols: {list(missing_symbols.keys())}')
  fixes, still_missing = generate_missing_symbol_fixes(missing_symbols, index, source_dir)
  if still_missing:
    info(f'still_missing: {still_missing.keys()}')

  remaining_fixes = []
  for fix in fixes:
    module_name, value = fix.get_module_name_and_value(source_dir)
    uht.add_action(timestamp, 'add', (value, fix.module_key) if value else fix.module_key, filename)
    if not value:
      remaining_fixes.append(fix)
      continue
    for node in filter(lambda x: isinstance(x, FromImportCfgNode), existing_global_imports):
      # We use module_key instead of module_name directly to handle different import styles - e.g.,
      # relative import v. absolute of the same module.
      if node.get_module_key() == fix.module_key:
        _, value = fix.get_module_name_and_value(source_dir)
        get_change(node).additions.append((value, fix.as_name))
        break
    else:
      remaining_fixes.append(fix)

  uht.save()
  changed = len(fixes) > 0 or len(changes) > 0
  if not changed:
    return source, False

  # Update existing imports.
  new_source = refactor.apply_import_changes(source, changes.values())

  # Apply any remaining fixes.
  new_source = refactor.insert_imports(new_source, filename,
                                                remaining_fixes)
  
  # SortImports seems to have some odd edge-cases in which it's completely broken right now....
  # Disabled.
  # if sort_imports and changed:
  #   out = SortImports(file_contents=new_source).output
  #   return out, True
  return new_source, changed


def apply_fixes_to_source(source, source_dir, fixes):
  # TODO: Intelligently inject these w/o sorting - e.g. infer style.
  code_insertion = ''.join([fix.to_code(source_dir) for fix in fixes])
  new_source = code_insertion + source
  return SortImports(file_contents=new_source).output


def _relative_from_path(filename, directory, relative_prefix: bool):
  filename = os.path.relpath(os.path.abspath(filename), directory)
  # Guaranteed all relative-pathing will be at the beginning, if any.
  prefix = ''
  if filename[0] == '.':
    # filename is downward from directory - need to convert ../ to dots.
    down_count = filename.count(f'..{os.sep}')
    if down_count:
      filename = filename[3 * down_count:]
      prefix = "." * (down_count + 1)
  elif relative_prefix:
    # filename is contained in directory - make it explicit with '.' prefix.
    prefix = '.'

  return f'{prefix}{module_loader.module_name_from_filename(filename)}'
  # basename
  # if filename[-(len('__init__.py')):] == '__init__.py':
  #   # filename = filename[:-len('__init__.py') - 1]
  #   return filename.replace(os.sep, '.')
  # elif filename[-(len('__init__.pyi')):] == '__init__.pyi':
  #   # filename = filename[:-len('__init__.pyi') - 1]
  #   return filename.replace(os.sep, '.')
  # return os.path.splitext(filename)[0].replace(os.sep, '.')


def module_name_from_filename_relative_to_dir(filename, source_dir):
  # We prefer relative names to avoid path issues, however, we don't want to go all the way out of
  # the current project to create a relative path.
  relative_distance = file_distance(filename, source_dir)

  for path in sorted(sys.path, key=lambda p: -len(p)):
    # TODO: Broader relative path support.
    if path == '.':
      path = source_dir
    if path == filename[:len(path)]:
      absolute_distance = file_distance(path, filename)
      if absolute_distance > relative_distance:
        return _relative_from_path(filename, source_dir, True)
      return _relative_from_path(filename, path, False)
  assert False


def does_import_match_cfg_node(import_, cfg_node, directory):
  assert isinstance(cfg_node, (ImportCfgNode, FromImportCfgNode))
  module_name, value = import_.get_module_name_and_value(directory)
  if isinstance(cfg_node, ImportCfgNode):
    if value:
      return False
    module_key, _, _ = module_loader.get_module_info_from_name(cfg_node.module_path, directory)
    if module_key != import_.module_key:
      return False
    return True

  # FromImportCfgNode.
  filename = ''
  for from_import_name, as_name in cfg_node.from_import_name_alias_dict.items():
    module_key = module_loader.get_module_info_from_name(
        module_loader.join_module_attribute(cfg_node.module_path, from_import_name), directory)[0]
    # If the from import is importing a module itself, then put it in the module_name
    if module_key.is_bad():
      module_key = module_loader.get_module_info_from_name(cfg_node.module_path, directory)[0]
    if module_key != import_.module_key:
      continue

    if from_import_name == '*':
      return True

    imported_symbol = as_name if as_name else from_import_name
    if not value:
      assert module_key.is_loadable_by_file()
      name = module_name_from_filename_relative_to_dir(import_.module_key.get_filename(), directory)
      return imported_symbol == name[name.rfind('.') + 1:]

    if value == imported_symbol:
      return True
  return False


class Rename:
  ...


@attr.s
class Import:
  module_key = attr.ib()
  as_name = attr.ib()
  _value = attr.ib()

  # TODO @instance_memoize
  def get_module_name_and_value(self, source_dir):
    if self.module_key.is_loadable_by_file():
      module_name = module_name_from_filename_relative_to_dir(self.module_key.get_filename(prefer_stub=False), source_dir)
    else:
      module_name = self.module_key.get_module_basename()

    value = self._value
    if not self._value:
      if '.' in module_name:
        i = module_name.rfind('.')
        value = module_name[i + 1:]
        if i > 0:
          pure_relative = '.' * (i + 1)
          if pure_relative == module_name[:(i + 1)]:
            module_name = pure_relative
          else:
            # Don't include final '.'.
            module_name = module_name[:i]

        else:
          module_name = '.'

    return module_name, value

  def to_code(self, source_dir):
    module_name, value = self.get_module_name_and_value(source_dir)
    if value:
      return f'from {module_name} import {value}\n'
    return f'import {module_name}\n'


def pobject_from_symbol_entry(symbol_entry):
  # We force the *real* module to be retrieved here instead of potentially a type-stub to ensure the
  # entire API is available.
  module = module_loader.get_module_from_key(symbol_entry.get_module_key(), force_real=True)
  if symbol_entry.is_module_itself():
    return module
  try:
    return module[symbol_entry.get_real_name()]
  except errors.SourceAttributeError as e:
    warning(
        f'Could not get {symbol_entry.get_real_name()} from module {symbol_entry.get_module_key()}. Code likely changed since index was created.'
    )
    return pobjects.UnknownObject(symbol_entry.get_real_name())


def matches_context(context, symbol_entry):
  # TODO: Refine all of this.
  # If we don't know what the symbol is, assume it matches by default.
  if symbol_entry.get_symbol_type() == symbol_index.SymbolType.AMBIGUOUS or symbol_entry.get_symbol_type(
  ) == symbol_index.SymbolType.UNKNOWN:
    return True

  if isinstance(context, symbol_context.MultipleSymbolContext):
    return all(matches_context(c, symbol_entry) for c in context.contexts)

  if isinstance(context, symbol_context.CallSymbolContext):
    # TODO: param check.
    return symbol_entry.get_symbol_type() == symbol_index.SymbolType.FUNCTION or symbol_entry.get_symbol_type(
    ) == symbol_index.SymbolType.TYPE

  if isinstance(context, symbol_context.SubscriptSymbolContext):
    return symbol_entry.get_symbol_type() != symbol_index.SymbolType.FUNCTION

  if isinstance(context, symbol_context.AttributeSymbolContext):
    pobject = pobject_from_symbol_entry(symbol_entry)
    if isinstance(pobject, pobjects.UnknownObject):
      return False
    return pobject.has_attribute(context.attribute)
    # return symbol_entry.get_symbol_type() != symbol_index.SymbolType.FUNCTION

  return True


def symbol_entry_preference_key(symbol_entry):
  return (symbol_entry.get_import_count(), not symbol_entry.is_imported(), symbol_entry.is_module_itself())


def symbol_entry_file_distance(symbol_entry, directory):
  module_key = symbol_entry.get_module_key()
  if not module_key.is_loadable_by_file():
    return 4  # No filename is probably a builtin - fallback to some reasonable default score.
  return file_distance(module_key.get_filename(), directory)


def file_distance(filename1, filename2):
  a_iter = iter(filename1.split(os.sep))
  b_iter = iter(filename2.split(os.sep))

  for a, b in zip(a_iter, b_iter):
    if a != b:
      a_iter = chain([a], a_iter)
      b_iter = chain([b], b_iter)
      break

  a_rem = list(a_iter)
  b_rem = list(b_iter)
  return max(len(a_rem), len(b_rem))


def relative_symbol_entry_preference_key(symbol_entry, directory):
  return tuple(
      list(symbol_entry_preference_key(symbol_entry)) +
      [-symbol_entry_file_distance(symbol_entry, directory)])


def key_list(l, key_fn):
  for x in l:
    yield x, key_fn(x)


def sort_keyed(l):
  return sorted(l, key=lambda kv: kv[1])


def generate_missing_symbol_fixes(missing_symbols: Dict[str, symbol_context.SymbolContext],
                                  index: symbol_index.SymbolIndex, directory) -> List[Union[Rename, Import]]:

  fixes = []
  still_missing = {}
  for symbol, context in missing_symbols.items():
    # Prefer symbols which are imported already very often.
    entries = sorted(filter(partial(matches_context, context), index.find_symbol(symbol)),
                     key=symbol_entry_preference_key)
    if not entries:
      warning(f'Could not find import for {symbol}')
      still_missing[symbol] = context
      continue
    # TODO: Compare symbol_context w/entry.
    if len(entries) > 1 and symbol_entry_preference_key(entries[-1]) == symbol_entry_preference_key(
        entries[-2]):
      keyed_entries = key_list(entries, lambda x: relative_symbol_entry_preference_key(x, directory))
      keyed_entries = sort_keyed(keyed_entries)
      if keyed_entries[-1][1] == keyed_entries[-2][1]:
        warning(
            f'Ambiguous for {symbol} : {keyed_entries[-1][0].get_module_key()}\n{keyed_entries[-2][0].get_module_key()}'
        )
        still_missing[symbol] = context
        continue
      entry = keyed_entries[-1][0]
    else:
      entry = entries[-1]

    module_key = entry.get_module_key()

    as_name = None
    if entry.is_module_itself():
      # Example: import pandas
      value = None
      if entry.is_alias():
        as_name = symbol
    elif entry.is_alias():
      # Example: From a import b as c
      value = entry.get_real_name()
      as_name = symbol
    else:
      # From a import b.
      value = symbol
    fixes.append(Import(module_key, as_name, value))
    # TODO: Renames.
  return fixes, still_missing


def main(index_file, target_file, force):
  assert os.path.exists(index_file)
  assert os.path.exists(target_file)
  index = symbol_index.SymbolIndex.load(index_file)
  index.update()
  if os.path.isdir(target_file):
    from glob import glob
    from . import file_history_tracker
    pattern = f'{target_file}{os.sep}**{os.sep}*py'
    filenames = glob(pattern, recursive=True)
    fht = file_history_tracker.FileHistoryTracker.load(os.path.join(os.getenv('HOME'),
                                                                    'fix_code_updates.msg'))
    updated_a_file = False
    for filename in filenames:
      path = os.path.join(target_file, filename)
      if fht.has_file_changed_since_timestamp(path) or force:
        info(f'Fixing symbols in {path}')
        new_code, changed = fix_missing_symbols_in_file(path, index)
        if changed:
          info(f'Made updates to {path}')
        fht.update_timestamp_for_path(path)
        updated_a_file = True
    if updated_a_file:
      fht.save()
    else:
      info(f'All {len(filenames)} files already up-to-date.')
  else:
    info(f'Fixing in {target_file}')
    fix_missing_symbols_in_file(target_file, index)


if __name__ == "__main__":
  import argparse
  parser = argparse.ArgumentParser()
  parser.add_argument('index_file')
  parser.add_argument('target_file')
  parser.add_argument('-f', '--force', action='store_true', default=False, dest='force')
  args, _ = parser.parse_known_args()
  main(args.index_file, args.target_file, args.force)
