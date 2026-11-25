def parse_line(line):
    """Parse one CSV line into a list of field strings.

    Fields are separated by commas. A field may be wrapped in double quotes, in which case it
    may contain commas and a doubled quote inside it stands for one literal quote. The wrapping
    quotes are removed. Whitespace is preserved exactly. An empty line gives [""]. Raises
    ValueError for a quoted field that is never closed.
    """
    fields = []
    current = []
    in_quotes = False
    index = 0
    length = len(line)
    while index < length:
        char = line[index]
        if in_quotes:
            if char == '"':
                if index + 1 < length and line[index + 1] == '"':
                    current.append('"')
                    index += 1
                else:
                    in_quotes = False
            else:
                current.append(char)
        elif char == '"':
            in_quotes = True
        elif char == ",":
            fields.append("".join(current))
            current = []
        else:
            current.append(char)
        index += 1
    if in_quotes:
        raise ValueError("unterminated quoted field")
    fields.append("".join(current))
    return fields
