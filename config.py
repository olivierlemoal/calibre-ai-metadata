from qt.core import QFormLayout, QLabel, QPlainTextEdit, QPushButton, QTabWidget, QVBoxLayout, QWidget

from calibre.ai import AICapabilities
from calibre.ai.config import ConfigureAI
from calibre.utils.config import JSONConfig
from calibre_plugins.ai_metadata.worker import DEFAULT_INSTRUCTIONS

load_translations()

prefs = JSONConfig('plugins/ai_metadata')
# Empty means DEFAULT_INSTRUCTIONS, so default improvements reach unmodified setups.
prefs.defaults['instructions'] = ''


def instructions():
    return prefs['instructions'] or DEFAULT_INSTRUCTIONS


class ConfigWidget(QWidget):
    validate_before_accept = True

    def __init__(self):
        QWidget.__init__(self)
        tabs = QTabWidget(self)
        QVBoxLayout(self).addWidget(tabs)

        general = QWidget()
        form = QFormLayout(general)
        self.instructions = QPlainTextEdit(instructions())
        self.instructions.setMinimumSize(700, 300)
        form.addRow(_('Instructions for the AI:'), self.instructions)
        reset = QPushButton(_('Restore default instructions'))
        reset.clicked.connect(lambda: self.instructions.setPlainText(DEFAULT_INSTRUCTIONS))
        form.addRow('', reset)
        tabs.addTab(general, _('General'))

        provider = QWidget()
        v = QVBoxLayout(provider)
        note = QLabel(_('Shared with the other AI features of calibre: changes here apply to them too.'))
        note.setWordWrap(True)
        v.addWidget(note)
        self.ai = ConfigureAI(AICapabilities.text_to_text, parent=provider)
        v.addWidget(self.ai)
        tabs.addTab(provider, _('AI provider'))

    def validate(self):
        return self.ai.validate()

    def save_settings(self):
        self.ai.commit()
        text = self.instructions.toPlainText()
        prefs['instructions'] = '' if text.strip() == DEFAULT_INSTRUCTIONS.strip() else text
