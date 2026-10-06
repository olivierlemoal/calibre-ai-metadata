import json
import re

load_translations()

DEFAULT_INSTRUCTIONS = '''\
You curate metadata in the user's calibre library. Conventions:
- Tags: a controlled vocabulary. Reuse existing tags exactly as spelled (see the vocabulary below) and follow its style (granularity, hierarchy such as "Fiction.Fantasy" if used). 1 to 3 tags per book, combinable (e.g. Economics + Politics). Create a new tag only when no existing one fits, and justify it in notes. Never use vendor/BISAC categories, dates or sentences as tags.
- Authors: "Firstname Lastname", one entry per person, no commas, proper capitalization and diacritics. Reuse the spelling already used in the library for the same person. Organizations stay as is. Drop placeholders such as "Unknown", "Various" or "Collectif" when the real authors are known.
- author_sort: "Lastname, Firstname", with particles placed per the author's language conventions ("Beauvoir, Simone de", "De Decker, Kris"); organizations unchanged.
- Title: the real title of this edition, without series name, volume number, author name, edition suffixes such as "(French Edition)" or file-name junk.
- title_sort: leading article moved to the end, according to the book language ("Photographer's Eye, The", "bruit et la fureur, Le").
- Series: only real series. Reuse existing series names exactly. series_index is the volume number (decimal sub-indices like 2.1 are fine when the series already uses them).
- Languages: ISO 639-2 codes of the actual text (eng, fra, deu...). Editions of the same work in different languages are distinct books, each with its own language and publisher.
- Publisher, pubdate (this edition, YYYY-MM-DD) and ISBN of this edition: verify them, leave them unchanged when unsure.
'''

FIELDS = ('title', 'title_sort', 'authors', 'author_sort', 'tags', 'series', 'series_index',
          'publisher', 'pubdate', 'languages', 'identifiers')

CONTRACT = '''\
# Task
Review the books below and propose metadata corrections.
The calibre GUI applies your proposal after the user reviews it.
If you can search the web, use it to verify facts. Never guess an ISBN, publisher or date: leave the field unchanged when unsure.

# Library context
Tags in use (name: book count):
{tags}
New tags use the language of these tags, or {language} if there are none.

Series in use (name: book count):
{series}

Authors in the library:
{authors}

# Books
```json
{books}
```

# Answer format
Your final answer MUST be ONE fenced ```json block and nothing else, shaped like:
{{"books": [{{"id": 209, "changes": {{"tags": ["Science Fiction", "Politics"], "publisher": "Tor Books"}}, "notes": "short justification"}}]}}
Allowed keys in "changes": title, title_sort, authors (list), author_sort, tags (complete list), series ("" removes it), series_index (number), publisher, pubdate (YYYY-MM-DD), languages (list of ISO 639-2 codes), identifiers (object of identifiers to add or replace, e.g. {{"isbn": "978..."}}; "" removes one).
Only include fields whose value must change. Include every book, with empty "changes" when it is already correct.
'''


def build_prompt(instructions, context, books, language, localized_notes):
    '''language: calibre UI language in English ("French"), for new tags in an untagged library and for notes.'''
    def counts(d):
        return '\n'.join(f'- {k}: {v}' for k, v in sorted(d.items(), key=lambda kv: (-kv[1], kv[0].lower()))) or '(none)'
    ans = instructions.strip() + '\n\n' + CONTRACT.format(
        tags=counts(context['tags']),
        language=language,
        series=counts(context['series']),
        authors=', '.join(sorted(context['authors'], key=str.lower)),
        books=json.dumps(books, ensure_ascii=False, indent=1),
    )
    if localized_notes:
        ans += f'Write "notes" in {language}.\n'
    return ans


def run_calibre_ai(prompts, plugin_name, log=None, abort=None, notifications=None):
    '''Send each prompt to the AI provider configured in calibre and merge the parsed {"books": [...]} answers.'''
    from calibre.ai import ChatMessage
    from calibre.customize.ui import available_ai_provider_plugins

    plugin = next((p for p in available_ai_provider_plugins() if p.name == plugin_name), None)
    if plugin is None:
        raise RuntimeError(_('AI provider {} is not available').format(plugin_name))
    books = []
    for n, prompt in enumerate(prompts):
        if notifications is not None:
            notifications.put((n / len(prompts), _('Batch {0}/{1}').format(n + 1, len(prompts))))
        content = ''
        for r in plugin.text_chat((ChatMessage(prompt),)):
            if abort is not None and abort.is_set():
                raise RuntimeError(_('Aborted'))
            if r.exception is not None:
                raise RuntimeError(f'{plugin_name}: {r.exception}\n{r.error_details}')
            if r.has_metadata and log is not None:
                log(f'Model: {r.model} ({r.provider}), cost: {r.cost} {r.currency}')
            content += r.content
        if log is not None:
            log(f'AI output, batch {n + 1}/{len(prompts)}:\n' + content)
        books += parse_answer(content)['books']
    return {'books': books}


def parse_answer(text):
    candidates = [m.group(1) for m in re.finditer(r'```json\s*\n(.*?)\n```', text, re.S)]
    decoder = json.JSONDecoder()
    for i in (m.start() for m in re.finditer(r'\{', text)):
        try:
            candidates.append(text[i:i + decoder.raw_decode(text[i:])[1]])
        except ValueError:
            pass
    for raw in reversed(candidates):
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        if isinstance(data, dict) and isinstance(data.get('books'), list):
            return data
    raise ValueError(_('No valid answer found in the AI output:') + '\n' + text[-2000:])
