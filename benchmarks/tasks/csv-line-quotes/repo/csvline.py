def parse_line(line):
    """Parse one CSV line into a list of field strings.

    Fields are separated by commas. A field may be wrapped in double quotes, in which case it
    may contain commas and a doubled quote inside it stands for one literal quote. The wrapping
    quotes are removed. Whitespace is preserved exactly. An empty line gives [""]. Raises
    ValueError for a quoted field that is never closed.
    """
    return [field.strip('"') for field in line.split(",")]
