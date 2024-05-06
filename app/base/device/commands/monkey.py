from . import command_manager, global_command


@command_manager.CommandManager.register
class MonkeyCommand(global_command.GlobalCommand):
    """
    Use a specific Monkey settings to achieve sth.
    """

    command_name = "monkey"
    prompt_event_description = ""
    perform_on_element = False
    perform_on_global = False

    function_call_properties = {
        "args": {
            "type": "string",
            "description": "The arguments to pass to monkey command",
        },
    }
    # I don't think llm will ever use this command...

    def perform_action(self, element, extra_data):
        self.driver.execute_script(
            "mobile: shell", {"command": "monkey", "args": extra_data["args"]}
        )
        return "Generate a few random events"
