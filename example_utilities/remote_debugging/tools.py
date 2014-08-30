import sys

from io import StringIO
from contextlib import contextmanager
from codeop import CommandCompiler

@contextmanager
def stdout_io(stdout=None):
    old = sys.stdout
    if stdout is None:
        stdout = StringIO()
        
    sys.stdout = stdout
    yield stdout
    sys.stdout = old

_compile = CommandCompiler()


def multiline_input(single_prompt=">>> ", additional_prompt="... "):
    header = single_prompt
    commands = []

    while True:
        source = input(header)
        commands.append(source)

        try:
            all_commands = "\n".join(commands)
            code = _compile(all_commands, "<dummy>", "single")

        except (OverflowError, SyntaxError, ValueError):
            import traceback
            traceback.print_exc()
            break

        else:
            if code is not None:
                break

            header = additional_prompt

    return "\n".join(commands)