from . import command_manager, global_command
import time


@command_manager.CommandManager.register
class SleepCommand(global_command.GlobalCommand):
    """
    Sleep for some seconds.
    """

    command_name = "sleep"
    prompt_event_description = ""
    perform_on_element = False
    perform_on_global = False

    function_call_properties = {
        "time": {
            "type": "int",
            "description": "The time to sleep in seconds",
        },
    }

    def perform_action(self, element, extra_data):
        time.sleep(extra_data["time"])
        return "Wait for %s seconds" % (extra_data["time"],)
