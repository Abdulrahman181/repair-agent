import re


def slugify(text):
    """Convert text to a URL slug.

    Lowercase ASCII letters and digits are kept. Every run of any other characters becomes a
    single hyphen. The result never starts or ends with a hyphen. Text with no letters or
    digits gives an empty string.
    """
    lowered = text.lower()
    return re.sub(r"[^a-z0-9]", "-", lowered)
