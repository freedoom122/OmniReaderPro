"""Sample OmniReader plugin: Document Word Count.

Demonstrates the plugin permission model — declares exactly the permissions
it needs (document.read only), registers a command, and reads document
text exclusively through the facade.
"""


def activate(facade):
    def run_word_count():
        result = facade.open_document("__current__")
        if not result:
            facade.notify("Open a document first, then run Word Count.",
                          "warning")
            return
        engine = result
        try:
            total = 0
            for _, text in engine.iter_text():
                total += len(text.split())
            facade.notify(f"Word count: {total:,} words", "info")
            facade.log(f"counted {total} words")
        except Exception as e:
            facade.notify(f"Could not count words: {e}", "error")

    facade.add_command("Plugin: Word Count", run_word_count)
    facade.log("word-count plugin activated")