"""
Furigana Ruby Plugin for Calibre
=================================
Adds automatic furigana (ruby annotations) to Japanese EPUBs.

Features:
  - Preserves existing publisher-added ruby (never overwrites)
  - Auto-generates furigana for remaining kanji using pykakasi
  - Marks auto ruby with class="auto" for CSS distinction
  - 3-state toggle in viewer: All / Publisher only / Off
  - JLPT N5/N4 filter: skips common kanji learners already know
  - Keyboard shortcut: Cmd+Shift+R (Mac) / Ctrl+Shift+R

Installation:
  Calibre > Preferences > Plugins > Load plugin from file > select this zip

Requirements:
  pykakasi (installed automatically on first use)
"""

from calibre.customize import InterfaceActionBase

__license__   = 'MIT'
__copyright__ = '2025, Furigana Ruby Plugin'
__docformat__ = 'restructuredtext en'


class FuriganaPluginBase(InterfaceActionBase):
    name                    = 'Furigana Ruby'
    description             = 'Add/remove furigana ruby annotations to Japanese EPUBs'
    supported_platforms     = ['windows', 'osx', 'linux']
    author                  = 'Furigana Ruby Plugin'
    version                 = (1, 2, 1)
    minimum_calibre_version = (6, 0, 0)
    actual_plugin           = 'calibre_plugins.furigana_ruby.action:FuriganaAction'

    def is_customizable(self):
        return True

    def config_widget(self):
        from calibre_plugins.furigana_ruby.config import ConfigWidget
        return ConfigWidget()

    def save_settings(self, config_widget):
        config_widget.save_settings()
