"""Shared console formatting - one banner style and one checklist mark for
every script, so Install.bat and Uninstall.bat read as one product.

ASCII only, on purpose. This prints inside a plain cmd.exe window opened by
double-clicking a .bat, on whatever codepage the player's Windows happens to
be set to. A real Unicode checkmark can come out as a box or a "?" there - or
worse, raise UnicodeEncodeError on some codepages and crash the run outright,
right when the player is watching. Nothing here needs Unicode to read clearly.
"""

WIDTH = 70


def banner(headline):
    """A boxed headline - the one thing on screen a player can't miss."""
    return "\n".join(["=" * WIDTH, headline.center(WIDTH), "=" * WIDTH])


def rule():
    return "=" * WIDTH


def done(text):
    return "  + %s" % text


def field(label, value):
    return "  %-18s%s" % (label + ":", value)
