import os
import sys
import types
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, 'src'), os.path.join(ROOT, 'tests')]

# GUIを使わずにテストできるよう、tkinterをスタブに差し替える
if 'tkinter' not in sys.modules:
    tkinter = types.ModuleType('tkinter')
    tkinter.filedialog = mock.MagicMock()
    tkinter.messagebox = mock.MagicMock()
    sys.modules['tkinter'] = tkinter
    sys.modules['tkinter.filedialog'] = tkinter.filedialog
    sys.modules['tkinter.messagebox'] = tkinter.messagebox
