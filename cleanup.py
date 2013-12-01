import sys
import re


class Quit(Exception):
    pass


def all_indices_of(needle, haystack):
    index = 0
    while True:
        new_index = haystack.find(needle)
        if new_index == -1:
            break
        shifted_index = new_index + len(needle)
        yield index + new_index

        haystack = haystack[shifted_index:]
        index += shifted_index


def format_sequence(line):
    return line.strip().replace(" ", "")


def attribute_import(module, attribute):
    return "{}.{}".format(module, attribute)


def get_modules(data):
    return [x.strip() for x in data.split(",") if x.strip()]


def parser(iterable, mode=0, data=None, key=None, relative=False,
           conversions=None, removed=None, imports=None):
    if conversions is None:
        conversions = {}
        removed = {}
        imports = {}

    try:
        line = next(iterable)

    except StopIteration:
        return conversions, removed, imports

    except TypeError:
        return parser(iter(iterable))

    # Ensure we have valid imports
    if (not ("from" in line or "import" in line)
        and key is None and line.strip()):
        return conversions, removed, imports

    if line.strip() and not "*" in line:
        if key is None:
            if "as" in line:
                print("Warning, import rename not handled: '{}'".format(line))
            if "." in line:
                shifted = line[line.find(".") + 1:]
                name = shifted[:shifted.find(' ')]
                relative = True

            else:
                shifted = line[line.find("from") + len("from") + 1:]
                name = shifted[:shifted.find(' ')]
                relative = False

            removed[line] = name
            imports[name] = relative

            following = line[line.find("import") + len("import") + 1:]

            if "(" in following:
                following = following[1:]
                key = name
                if ")" in following:
                    key = None
                    following = following[:following.find(")")]
                    conversions[name] = get_modules(following)
                else:
                    data = [format_sequence(following)]
            else:
                conversions[name] = get_modules(following)

        else:
            if ")" in line:
                until = line[:line.find(")")]
                data.append(format_sequence(until))
                import_list = get_modules(''.join(data))
                conversions[key] = import_list
                removed[line] = key
                key = None

            else:
                data.append(format_sequence(line))
                removed[line] = key

    return parser(iterable, mode, data, key,
        relative, conversions, removed, imports)


def finder(line, module):
    fmt = "{0}{1}{0}|(?<=\(){1}\)|{1}\(\)".format("\\b", module)
    finder = re.compile(fmt, flags=re.DOTALL)
    return [match.span() for match in finder.finditer(line)]


def create_newlines(data):
    conversions, removed, imports = parser(data)
    imported = []
    for line in data:
        if line in removed:
            module = removed[line]
            if not module in imported:
                relative = imports[module]
                imported.append(module)
                yield ("from . " if relative else "") + "import {}\n".format(module)
            continue

        for key, key_data in conversions.items():
            for module in key_data:
                found = finder(line, module)
                for index in range(len(found)):
                    change = attribute_import(key, module)
                    start, end = found[index]
                    line = line[:start] + change + line[end:]
                    # Recalculate matches (as we have modified line)
                    found = finder(line, module)

        yield line


def test(filepath):
    sys.setrecursionlimit(10000)
    with open(filepath, "r+") as file:
        file.write(''.join(create_newlines(file.readlines())))
