# Run with: calibre-debug -e tests/run.py
import builtins
import os
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Import the plugin modules from the source tree, never from an installed plugin zip.
sys.meta_path[:] = [f for f in sys.meta_path if type(f).__name__ != 'CalibrePluginFinder']
for name in [n for n in sys.modules if n == 'calibre_plugins' or n.startswith('calibre_plugins.')]:
    del sys.modules[name]
sys.modules['calibre_plugins'] = types.ModuleType('calibre_plugins')
sys.modules['calibre_plugins'].__path__ = []
package = types.ModuleType('calibre_plugins.ai_metadata')
package.__path__ = [ROOT]
sys.modules['calibre_plugins.ai_metadata'] = package
# Injected per module by calibre's plugin loader; the builtin _ is enough for tests.
builtins.load_translations = lambda: None

suite = unittest.defaultTestLoader.discover(os.path.join(ROOT, 'tests'), top_level_dir=ROOT)
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
