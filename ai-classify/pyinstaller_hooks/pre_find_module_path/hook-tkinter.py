"""Keep Tkinter when Tcl's build-time probe fails in a restricted environment.

The build command explicitly supplies the matching Tcl/Tk runtime data.
"""


def pre_find_module_path(hook_api):
    pass
