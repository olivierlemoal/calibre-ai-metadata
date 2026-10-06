from functools import partial

from qt.core import QDialog, QIcon, QMenu

from calibre.ai import AICapabilities
from calibre.ai.prefs import plugin_for_purpose
from calibre.ai.prefs import prefs as ai_prefs
from calibre.gui2 import Dispatcher, error_dialog, info_dialog
from calibre.gui2.actions import InterfaceAction
from calibre.gui2.threaded_jobs import ThreadedJob
from calibre.utils.localization import ui_language_as_english

from calibre_plugins.ai_metadata import config
from calibre_plugins.ai_metadata.library import accepted_values, apply, book_snapshot, diff, library_context, review_pair
from calibre_plugins.ai_metadata.worker import build_prompt, run_calibre_ai

load_translations()

TITLE = _('AI metadata')
# Keeps each answer well below provider output-token limits.
BATCH_SIZE = 10


class AIMetadataAction(InterfaceAction):
    # Not translated: identifies the action in calibre's toolbar/menu layouts.
    name = 'AI metadata'
    action_spec = (TITLE, None, _('Rework metadata and tags of the selected books with AI'), None)
    action_type = 'current'
    dont_add_to = frozenset(['context-menu-device', 'toolbar-device', 'menubar-device'])

    def genesis(self):
        self.qaction.setIcon(QIcon.ic('ai.png'))
        self.qaction.triggered.connect(self.start)
        menu = QMenu(self.gui)
        self.create_menu_action(menu, 'ai-metadata-config', _('Configure…'), triggered=self.show_config)
        self.qaction.setMenu(menu)

    def show_config(self):
        self.interface_action_base_plugin.do_user_config(self.gui)

    def start(self):
        book_ids = list(self.gui.library_view.get_selected_ids())
        if not book_ids:
            return info_dialog(self.gui, TITLE, _('Select the books to rework first.'), show=True)
        plugin = plugin_for_purpose(AICapabilities.text_to_text)
        if plugin is None or not plugin.is_ready_for_use:
            error_dialog(self.gui, TITLE, _('No AI provider is configured: set one up in the "AI provider" tab.'), show=True)
            return self.show_config()

        library_path = self.gui.current_db.library_path
        db = self.gui.current_db.new_api
        context = library_context(db)
        language = ui_language_as_english()
        # Same setting as calibre's own AI features ("respond in the UI language").
        localized_notes = ai_prefs()['llm_localized_results'] == 'always'
        prompts = [build_prompt(config.instructions(), context, [book_snapshot(db, i) for i in book_ids[n:n + BATCH_SIZE]],
                                language, localized_notes)
                   for n in range(0, len(book_ids), BATCH_SIZE)]
        count = len(book_ids)
        job = ThreadedJob(
            'ai_metadata', ngettext('{title}: {count} book via {provider}', '{title}: {count} books via {provider}', count).format(
                title=TITLE, count=count, provider=plugin.name),
            run_calibre_ai, (prompts, plugin.name), {},
            Dispatcher(partial(self.job_done, library_path, book_ids)))
        self.gui.job_manager.run_threaded_job(job)
        self.gui.status_bar.show_message(ngettext(
            '{provider} is reviewing {count} book…', '{provider} is reviewing {count} books…', count).format(provider=plugin.name, count=count), 5000)

    def job_done(self, library_path, book_ids, job):
        if job.failed:
            return self.gui.job_exception(job, dialog_title=_('{title} failed').format(title=TITLE))
        db = self.gui.current_db.new_api
        if self.gui.current_db.library_path != library_path:
            return error_dialog(self.gui, TITLE, _('The library was switched while the AI was running; proposal discarded.'), show=True)

        from calibre_plugins.ai_metadata.review import ReviewDialog
        answers = {}
        for entry in job.result['books']:
            try:
                answers[int(entry['id'])] = entry
            except (KeyError, TypeError, ValueError):
                continue
        pairs, notes, unchanged = {}, {}, []
        for book_id in book_ids:
            if not db.has_id(book_id):
                continue
            entry = answers.get(book_id, {})
            changes = entry.get('changes') or {}
            rows = diff(db, book_id, changes) if isinstance(changes, dict) else []
            note = str(entry.get('notes') or ('' if entry else _('The AI returned nothing for this book')))
            if rows:
                pairs[book_id] = review_pair(db, book_id, rows)
                notes[book_id] = note
            else:
                unchanged.append(f"{db.field_for('title', book_id)}: {note}")

        if not pairs:
            return info_dialog(self.gui, TITLE, _('The AI proposes no change.'), det_msg='\n'.join(unchanged), show=True)
        d = ReviewDialog(self.gui, pairs, notes)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        updated = []
        for book_id, (_changed, mi) in d.accepted_map.items():
            values = accepted_values(db, book_id, mi) if mi is not None else None
            if values:
                apply(db, book_id, values)
                updated.append(book_id)
        if d.mark_rejected and d.rejected_ids:
            self.gui.current_db.data.set_marked_ids(d.rejected_ids)
        if updated:
            self.gui.iactions['Edit Metadata'].refresh_gui(updated, covers_changed=False)
            self.gui.status_bar.show_message(ngettext(
                '{title}: updated {count} book', '{title}: updated {count} books', len(updated)).format(title=TITLE, count=len(updated)), 5000)
