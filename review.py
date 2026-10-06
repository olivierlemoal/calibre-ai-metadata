from calibre.gui2.metadata.diff import CompareMany

from calibre_plugins.ai_metadata.library import REVIEW_FIELDS

load_translations()


class ReviewDialog(CompareMany):
    '''calibre's "Review downloaded metadata" dialog, with the AI notes for the current book.'''

    def __init__(self, gui, pairs, notes):
        # Read by show_current_item(), which CompareMany.__init__ already calls.
        self.pairs, self.notes = pairs, notes
        self.intro = _('Proposed metadata on the left (editable), current metadata on the right.')
        super().__init__(
            list(pairs), pairs.__getitem__, gui.current_db.field_metadata, parent=gui,
            window_title=_('AI metadata'),
            reject_button_tooltip=_('Discard the AI changes for this book'),
            accept_all_tooltip=_('Accept the AI changes for all remaining books'),
            reject_all_tooltip=_('Discard the AI changes for all remaining books'),
            revert_tooltip=_('Discard the AI value for: %s'),
            intro_msg=self.intro,
            action_button=(_('&View book'), 'view.png', gui.iactions['View'].view_historical),
            db=gui.current_db, fields=REVIEW_FIELDS, blank_as_equal=False, datetime_fmt='d MMMM yyyy',
        )

    def show_current_item(self):
        super().show_current_item()
        note = self.notes.get(self.ids[0])
        self.la.setText(self.intro + '\n\n' + _('AI notes: {}').format(note) if note else self.intro)
