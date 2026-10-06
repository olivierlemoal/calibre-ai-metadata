from calibre.customize import InterfaceActionBase

load_translations()


class AIMetadataPlugin(InterfaceActionBase):
    name = 'AI metadata'
    description = _("Rework metadata and tags of books with calibre's AI provider")
    supported_platforms = ['linux', 'osx', 'windows']
    author = 'olivierlemoal'
    version = (1, 0, 0)
    minimum_calibre_version = (9, 0, 0)
    actual_plugin = 'calibre_plugins.ai_metadata.action:AIMetadataAction'

    def is_customizable(self):
        return True

    def config_widget(self):
        from calibre_plugins.ai_metadata.config import ConfigWidget
        return ConfigWidget()

    def save_settings(self, config_widget):
        config_widget.save_settings()
